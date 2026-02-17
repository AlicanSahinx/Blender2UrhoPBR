import os
import re
import subprocess

import bpy

from .core.logging import ExportLogger
from .core.types import ExportSettings, PathConfig
from .mesh.decompose import decompose_mesh, decompose_lod_objects
from .mesh.optimize import optimize_model_indices
from .formats.model_writer import write_model
from .materials.analyzer import PrincipledBSDFAnalyzer
from .materials.technique_map import TechniqueMapper
from .materials.texture_resolver import (
    copy_all_textures,
    pack_metallic_roughness,
    resolve_texture_path,
)
from .formats.material_writer import write_material
from .skeleton.armature import decompose_armature
from .skeleton.animation import decompose_actions
from .formats.animation_writer import write_animation
from .core.name_parser import material_suffix, parse_object_name
from .scene.hierarchy import build_scene_hierarchy, compute_viewer_config
from .formats.scene_writer import write_scene, write_prefab, write_viewer_config
from .mesh.tangents import generate_tangents

# Module-level storage for last export log (used by report dialog)
_last_export_log: ExportLogger | None = None


def get_last_export_log() -> ExportLogger | None:
    return _last_export_log


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _build_settings(scene_settings) -> ExportSettings:
    """Convert Blender PropertyGroup to ExportSettings dataclass."""
    root = bpy.path.abspath(scene_settings.output_path)
    return ExportSettings(
        only_selected=scene_settings.only_selected,
        scale=scene_settings.scale,
        apply_modifiers=scene_settings.apply_modifiers,
        use_local_origin=scene_settings.use_local_origin,
        export_normal=scene_settings.export_normal,
        export_uv=scene_settings.export_uv,
        export_uv2=scene_settings.export_uv2,
        export_tangent=scene_settings.export_tangent,
        export_color=scene_settings.export_color,
        export_skeleton=scene_settings.export_skeleton,
        only_deform_bones=scene_settings.only_deform_bones,
        only_visible_bones=scene_settings.only_visible_bones,
        export_animations=scene_settings.export_animations,
        animation_source=scene_settings.animation_source,
        export_anim_position=scene_settings.export_anim_position,
        export_anim_rotation=scene_settings.export_anim_rotation,
        export_anim_scale=scene_settings.export_anim_scale,
        export_morphs=scene_settings.export_morphs,
        export_morph_normals=scene_settings.export_morph_normals,
        export_morph_tangents=scene_settings.export_morph_tangents,
        export_materials=scene_settings.export_materials,
        prefer_pbr=scene_settings.prefer_pbr,
        copy_textures=scene_settings.copy_textures,
        pack_pbr_textures=scene_settings.pack_pbr_textures,
        optimize_indices=scene_settings.optimize_indices,
        export_prefabs=scene_settings.export_prefabs,
        export_scene=scene_settings.export_scene,
        cast_shadows=scene_settings.cast_shadows,
        overwrite=scene_settings.overwrite,
        use_subdirs=scene_settings.use_subdirs,
        paths=PathConfig(root=root),
    )


def _ensure_dirs(settings: ExportSettings) -> None:
    """Create output directories if they don't exist."""
    root = settings.paths.root
    os.makedirs(root, exist_ok=True)
    if settings.use_subdirs:
        for subdir in [settings.paths.models, settings.paths.materials,
                       settings.paths.textures, settings.paths.animations,
                       settings.paths.objects, settings.paths.scenes]:
            os.makedirs(os.path.join(root, subdir), exist_ok=True)


def _get_mesh_objects(context, settings: ExportSettings) -> list:
    """Get mesh objects to export based on settings."""
    if settings.only_selected:
        return [obj for obj in context.selected_objects if obj.type == 'MESH']
    return [obj for obj in context.scene.objects if obj.type == 'MESH']


_SCENE_TYPES = {'MESH', 'LIGHT', 'CAMERA', 'EMPTY'}


def _get_scene_objects(context, settings: ExportSettings) -> list:
    """Get all exportable objects for scene hierarchy (mesh + light + camera + empty)."""
    if settings.only_selected:
        return [obj for obj in context.selected_objects if obj.type in _SCENE_TYPES]
    return [obj for obj in context.scene.objects if obj.type in _SCENE_TYPES]


def _get_dir(settings: ExportSettings, subdir_name: str) -> str:
    """Get full path for a subdirectory."""
    subdir = getattr(settings.paths, subdir_name, "")
    return os.path.join(
        settings.paths.root,
        subdir if settings.use_subdirs else "",
    )


def _finish_export(operator, log: ExportLogger, summary: str) -> set:
    """Store log and show report if needed. Returns operator result set."""
    global _last_export_log
    _last_export_log = log

    if log.has_errors:
        operator.report({'ERROR'}, f"{summary} with {log.error_count} errors")
    else:
        operator.report({'INFO'}, f"{summary}, {log.warning_count} warnings")

    if log.has_errors or log.warning_count > 0:
        bpy.ops.urho.export_report('INVOKE_DEFAULT')

    return {'FINISHED'}


_URHO3D_DATA = "/usr/local/share/Urho3D/resources/Data"
_URHO3D_CORE = "/usr/local/share/Urho3D/resources/CoreData"

# Track SceneViewer subprocess for hot reload
_viewer_process: subprocess.Popen | None = None


def _find_viewer() -> str:
    """Find SceneViewer binary: prefs > PATH > common locations."""
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
        p = bpy.path.abspath(prefs.viewer_path)
        if p and os.path.isfile(p):
            return p
    except KeyError:
        pass

    # Check PATH
    import shutil
    found = shutil.which("SceneViewer")
    if found:
        return found

    # Common build locations
    for candidate in [
        os.path.expanduser("~/DEV/game/SceneViewer/build/SceneViewer"),
    ]:
        if os.path.isfile(candidate):
            return candidate

    return ""


def _launch_viewer(operator, context) -> None:
    """Launch SceneViewer as subprocess to preview exported scene.

    Hot reload: if a previous SceneViewer is still running, terminate it
    before launching a new instance.
    """
    global _viewer_process

    viewer = _find_viewer()
    if not viewer:
        operator.report({'WARNING'},
                        "SceneViewer not found. Set path in addon preferences.")
        return

    # Hot reload: kill previous instance
    if _viewer_process is not None and _viewer_process.poll() is None:
        _viewer_process.terminate()
        try:
            _viewer_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _viewer_process.kill()
        operator.report({'INFO'}, "Previous SceneViewer closed")

    export_dir = bpy.path.abspath(context.scene.urho_export.output_path)

    resource_paths = export_dir
    if os.path.isdir(_URHO3D_DATA):
        resource_paths += f";{_URHO3D_DATA}"
    if os.path.isdir(_URHO3D_CORE):
        resource_paths += f";{_URHO3D_CORE}"

    env = os.environ.copy()
    env["SDL_VIDEODRIVER"] = "x11"
    env["SDL_AUDIODRIVER"] = "dummy"

    _viewer_process = subprocess.Popen(
        [viewer, "-p", resource_paths, "-w", "-x", "1280", "-y", "720"],
        env=env,
    )
    operator.report({'INFO'}, "SceneViewer launched")


_LOD_PATTERN = re.compile(r'^(.+)_LOD(\d+\.?\d*)$')


def _find_lod_consumed(objects: list, lod_models: dict) -> set:
    """Find which objects were consumed by LOD grouping."""
    consumed = set()
    for base_name in lod_models:
        for obj in objects:
            match = _LOD_PATTERN.match(obj.name)
            if match and match.group(1) == base_name:
                consumed.add(obj.name)
            elif obj.name == base_name:
                consumed.add(obj.name)
    return consumed


def _analyze_object_materials(
    obj,
    analyzer: PrincipledBSDFAnalyzer,
    mapper: TechniqueMapper,
    settings: ExportSettings,
    log: ExportLogger,
) -> list:
    """Analyze all materials on an object. Returns list of (mat_name, pbr_props, urho_mat)."""
    results = []
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue
        pbr_props = analyzer.analyze(mat)
        if pbr_props is None:
            log.warning(f"Material '{mat.name}' has no Principled BSDF, skipping")
            continue
        urho_mat = mapper.map_material(pbr_props)
        results.append((mat.name, pbr_props, urho_mat))
    return results


# ---------------------------------------------------------------------------
# Export All
# ---------------------------------------------------------------------------

class URHO_OT_Export(bpy.types.Operator):
    bl_idname = "urho.export"
    bl_label = "Export All"
    bl_description = "Export all selected objects (models, materials, animations, textures, scene)"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.urho_export.output_path)

    def execute(self, context):
        log = ExportLogger()
        settings = _build_settings(context.scene.urho_export)
        _ensure_dirs(settings)

        depsgraph = context.evaluated_depsgraph_get()
        objects = _get_mesh_objects(context, settings)
        if not objects:
            self.report({'WARNING'}, "No mesh objects to export")
            return {'CANCELLED'}

        analyzer = PrincipledBSDFAnalyzer()
        mapper = TechniqueMapper(
            prefer_pbr=settings.prefer_pbr,
            pack_textures=settings.pack_pbr_textures,
        )
        exported_materials = set()

        models_dir = _get_dir(settings, "models")
        anims_dir = _get_dir(settings, "animations")

        exported_count = 0
        anim_count = 0

        # LOD grouping
        lod_models = decompose_lod_objects(objects, depsgraph, settings, log)
        lod_consumed = _find_lod_consumed(objects, lod_models)

        for base_name, model in lod_models.items():
            if model is None:
                continue

            base_obj = next((o for o in objects if o.name == base_name), None)
            armature_obj = None
            if base_obj and settings.export_skeleton:
                armature_obj = base_obj.find_armature()

            if armature_obj and settings.export_skeleton and base_obj:
                model.bones = decompose_armature(armature_obj, base_obj, settings, log)
            else:
                model.bones = []

            if settings.export_tangent:
                generate_tangents(model)
            if settings.optimize_indices:
                optimize_model_indices(model)

            mdl_path = os.path.join(models_dir, f"{model.name}.mdl")
            if write_model(model, mdl_path, log):
                exported_count += 1

            if armature_obj and settings.export_animations and model.bones:
                bones_map = {b.name: b.index for b in model.bones}
                for anim in decompose_actions(
                        armature_obj, context.scene, bones_map, settings, log):
                    ani_path = os.path.join(anims_dir, f"{anim.name}.ani")
                    if write_animation(anim, ani_path, log):
                        anim_count += 1

            if settings.export_materials and base_obj:
                _export_materials_for_obj(
                    base_obj, analyzer, mapper, settings, exported_materials, log)

        # Non-LOD objects
        for obj in objects:
            if obj.name in lod_consumed:
                continue

            armature_obj = obj.find_armature() if settings.export_skeleton else None
            bones = (decompose_armature(armature_obj, obj, settings, log)
                     if armature_obj and settings.export_skeleton else [])

            model = decompose_mesh(obj, depsgraph, settings, log)
            if model is None:
                continue

            if bones:
                model.bones = bones
            if settings.export_tangent:
                generate_tangents(model)
            if settings.optimize_indices:
                optimize_model_indices(model)

            mdl_path = os.path.join(models_dir, f"{model.name}.mdl")
            if write_model(model, mdl_path, log):
                exported_count += 1

            if armature_obj and settings.export_animations and bones:
                bones_map = {b.name: b.index for b in bones}
                for anim in decompose_actions(
                        armature_obj, context.scene, bones_map, settings, log):
                    ani_path = os.path.join(anims_dir, f"{anim.name}.ani")
                    if write_animation(anim, ani_path, log):
                        anim_count += 1

            if settings.export_materials:
                _export_materials_for_obj(
                    obj, analyzer, mapper, settings, exported_materials, log)

        # Scene / prefab
        if settings.export_scene or settings.export_prefabs:
            all_scene_objs = _get_scene_objects(context, settings)
            scene_nodes = build_scene_hierarchy(all_scene_objs, settings, log)
            if settings.export_scene and scene_nodes:
                scenes_dir = _get_dir(settings, "scenes")
                scene_path = os.path.join(scenes_dir, "Scene.xml")
                write_scene(scene_nodes, scene_path, log)
                # ViewerConfig
                viewer_cfg = compute_viewer_config(
                    scene_nodes, getattr(context.scene, 'world', None))
                write_viewer_config(
                    viewer_cfg, os.path.join(scenes_dir, "ViewerConfig.xml"), log)
            if settings.export_prefabs and scene_nodes:
                objects_dir = _get_dir(settings, "objects")
                for node in scene_nodes:
                    prefab_name = node.original_name or node.name
                    write_prefab(node, os.path.join(objects_dir, f"{prefab_name}.xml"), log)

        result = _finish_export(
            self, log,
            f"Exported {exported_count} model(s), {anim_count} animation(s), "
            f"{len(exported_materials)} material(s)")

        # Launch SceneViewer if preview toggle is on
        if context.scene.urho_export.preview and not log.has_errors:
            _launch_viewer(self, context)

        return result


# ---------------------------------------------------------------------------
# Export Models Only
# ---------------------------------------------------------------------------

class URHO_OT_ExportModels(bpy.types.Operator):
    bl_idname = "urho.export_models"
    bl_label = "Models"
    bl_description = "Export only .mdl model files (with skeleton if enabled)"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.urho_export.output_path)

    def execute(self, context):
        log = ExportLogger()
        settings = _build_settings(context.scene.urho_export)
        _ensure_dirs(settings)

        depsgraph = context.evaluated_depsgraph_get()
        objects = _get_mesh_objects(context, settings)
        if not objects:
            self.report({'WARNING'}, "No mesh objects to export")
            return {'CANCELLED'}

        models_dir = _get_dir(settings, "models")
        exported_count = 0

        # LOD grouping
        lod_models = decompose_lod_objects(objects, depsgraph, settings, log)
        lod_consumed = _find_lod_consumed(objects, lod_models)

        for base_name, model in lod_models.items():
            if model is None:
                continue

            base_obj = next((o for o in objects if o.name == base_name), None)
            if base_obj and settings.export_skeleton:
                armature_obj = base_obj.find_armature()
                if armature_obj:
                    model.bones = decompose_armature(
                        armature_obj, base_obj, settings, log)

            if settings.export_tangent:
                generate_tangents(model)
            if settings.optimize_indices:
                optimize_model_indices(model)

            mdl_path = os.path.join(models_dir, f"{model.name}.mdl")
            if write_model(model, mdl_path, log):
                exported_count += 1

        for obj in objects:
            if obj.name in lod_consumed:
                continue

            armature_obj = obj.find_armature() if settings.export_skeleton else None
            bones = (decompose_armature(armature_obj, obj, settings, log)
                     if armature_obj and settings.export_skeleton else [])

            model = decompose_mesh(obj, depsgraph, settings, log)
            if model is None:
                continue

            if bones:
                model.bones = bones
            if settings.export_tangent:
                generate_tangents(model)
            if settings.optimize_indices:
                optimize_model_indices(model)

            mdl_path = os.path.join(models_dir, f"{model.name}.mdl")
            if write_model(model, mdl_path, log):
                exported_count += 1

        return _finish_export(self, log, f"Exported {exported_count} model(s)")


# ---------------------------------------------------------------------------
# Export Materials Only
# ---------------------------------------------------------------------------

def _export_materials_for_obj(
    obj,
    analyzer: PrincipledBSDFAnalyzer,
    mapper: TechniqueMapper,
    settings: ExportSettings,
    exported_materials: set,
    log: ExportLogger,
) -> None:
    """Export all materials from an object's material slots (XML only, no texture copy).

    If the object has _2side or _alpha suffixes, materials are cloned with
    modified cull/alpha settings and a suffixed filename.
    """
    materials_dir = _get_dir(settings, "materials")
    textures_dir = _get_dir(settings, "textures")
    textures_subdir = settings.paths.textures if settings.use_subdirs else ""

    parsed = parse_object_name(obj.name)
    mat_sfx = material_suffix(parsed)

    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue

        effective_name = mat.name + mat_sfx
        if effective_name in exported_materials:
            continue

        pbr_props = analyzer.analyze(mat)
        if pbr_props is None:
            log.warning(f"Material '{mat.name}' has no Principled BSDF, skipping")
            continue

        urho_mat = mapper.map_material(pbr_props)

        # Apply suffix overrides to cloned material
        if parsed.two_side:
            urho_mat.cull_mode = "none"
            urho_mat.shadow_cull = "none"

        if parsed.alpha:
            if "Alpha" not in urho_mat.technique_name:
                urho_mat.technique_name = urho_mat.technique_name.replace(
                    ".xml", "Alpha.xml")
            if "ALPHAMASK" not in urho_mat.ps_defines:
                urho_mat.ps_defines = (
                    (urho_mat.ps_defines + " ALPHAMASK").strip()
                )

        # PBR texture packing
        if settings.pack_pbr_textures and settings.prefer_pbr:
            if pbr_props.metallic_texture or pbr_props.roughness_texture:
                metallic_name = (pbr_props.metallic_texture.image_name
                                 if pbr_props.metallic_texture else None)
                roughness_name = (pbr_props.roughness_texture.image_name
                                  if pbr_props.roughness_texture else None)
                packed_name = pack_metallic_roughness(
                    metallic_name, roughness_name,
                    f"{mat.name}_MetRough.png", textures_dir, log)
                if packed_name:
                    urho_mat.textures["specular"] = packed_name

        mat_path = os.path.join(materials_dir, f"{effective_name}.xml")
        if write_material(urho_mat, mat_path, textures_subdir, log):
            exported_materials.add(effective_name)

        # Also export the base material if not yet exported (for non-suffixed objects)
        if mat_sfx and mat.name not in exported_materials:
            base_mat = mapper.map_material(pbr_props)
            if settings.pack_pbr_textures and settings.prefer_pbr:
                if pbr_props.metallic_texture or pbr_props.roughness_texture:
                    metallic_name = (pbr_props.metallic_texture.image_name
                                     if pbr_props.metallic_texture else None)
                    roughness_name = (pbr_props.roughness_texture.image_name
                                      if pbr_props.roughness_texture else None)
                    packed_name = pack_metallic_roughness(
                        metallic_name, roughness_name,
                        f"{mat.name}_MetRough.png", textures_dir, log)
                    if packed_name:
                        base_mat.textures["specular"] = packed_name
            base_path = os.path.join(materials_dir, f"{mat.name}.xml")
            if write_material(base_mat, base_path, textures_subdir, log):
                exported_materials.add(mat.name)

        # Copy textures when exporting via "Export All" or "Export Textures"
        if settings.copy_textures:
            copy_all_textures(urho_mat.textures, textures_dir, log)


class URHO_OT_ExportMaterials(bpy.types.Operator):
    bl_idname = "urho.export_materials"
    bl_label = "Materials"
    bl_description = "Export only material XML files"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.urho_export.output_path)

    def execute(self, context):
        log = ExportLogger()
        settings = _build_settings(context.scene.urho_export)
        _ensure_dirs(settings)

        objects = _get_mesh_objects(context, settings)
        if not objects:
            self.report({'WARNING'}, "No mesh objects to export")
            return {'CANCELLED'}

        analyzer = PrincipledBSDFAnalyzer()
        mapper = TechniqueMapper(
            prefer_pbr=settings.prefer_pbr,
            pack_textures=settings.pack_pbr_textures,
        )
        exported_materials = set()

        # Temporarily disable texture copy for materials-only export
        orig_copy = settings.copy_textures
        settings.copy_textures = False

        for obj in objects:
            _export_materials_for_obj(
                obj, analyzer, mapper, settings, exported_materials, log)

        settings.copy_textures = orig_copy

        return _finish_export(
            self, log, f"Exported {len(exported_materials)} material(s)")


# ---------------------------------------------------------------------------
# Export Animations Only
# ---------------------------------------------------------------------------

class URHO_OT_ExportAnimations(bpy.types.Operator):
    bl_idname = "urho.export_animations"
    bl_label = "Animations"
    bl_description = "Export only .ani animation files"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.urho_export.output_path)

    def execute(self, context):
        log = ExportLogger()
        settings = _build_settings(context.scene.urho_export)
        _ensure_dirs(settings)

        objects = _get_mesh_objects(context, settings)
        if not objects:
            self.report({'WARNING'}, "No mesh objects to export")
            return {'CANCELLED'}

        anims_dir = _get_dir(settings, "animations")
        anim_count = 0
        processed_armatures = set()

        for obj in objects:
            armature_obj = obj.find_armature()
            if armature_obj is None:
                continue
            if armature_obj.name in processed_armatures:
                continue
            processed_armatures.add(armature_obj.name)

            # Decompose skeleton to get bones_map
            bones = decompose_armature(armature_obj, obj, settings, log)
            if not bones:
                continue

            bones_map = {b.name: b.index for b in bones}
            animations = decompose_actions(
                armature_obj, context.scene, bones_map, settings, log)

            for anim in animations:
                ani_path = os.path.join(anims_dir, f"{anim.name}.ani")
                if write_animation(anim, ani_path, log):
                    anim_count += 1

        return _finish_export(self, log, f"Exported {anim_count} animation(s)")


# ---------------------------------------------------------------------------
# Export Textures Only
# ---------------------------------------------------------------------------

class URHO_OT_ExportTextures(bpy.types.Operator):
    bl_idname = "urho.export_textures"
    bl_label = "Textures"
    bl_description = "Copy and pack texture files to output directory"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.urho_export.output_path)

    def execute(self, context):
        log = ExportLogger()
        settings = _build_settings(context.scene.urho_export)
        _ensure_dirs(settings)

        objects = _get_mesh_objects(context, settings)
        if not objects:
            self.report({'WARNING'}, "No mesh objects to export")
            return {'CANCELLED'}

        textures_dir = _get_dir(settings, "textures")
        analyzer = PrincipledBSDFAnalyzer()
        mapper = TechniqueMapper(
            prefer_pbr=settings.prefer_pbr,
            pack_textures=settings.pack_pbr_textures,
        )

        texture_count = 0
        processed_materials = set()

        for obj in objects:
            for mat_name, pbr_props, urho_mat in _analyze_object_materials(
                    obj, analyzer, mapper, settings, log):
                if mat_name in processed_materials:
                    continue
                processed_materials.add(mat_name)

                # PBR texture packing
                if settings.pack_pbr_textures and settings.prefer_pbr:
                    if pbr_props.metallic_texture or pbr_props.roughness_texture:
                        metallic_name = (pbr_props.metallic_texture.image_name
                                         if pbr_props.metallic_texture else None)
                        roughness_name = (pbr_props.roughness_texture.image_name
                                          if pbr_props.roughness_texture else None)
                        packed = pack_metallic_roughness(
                            metallic_name, roughness_name,
                            f"{mat_name}_MetRough.png", textures_dir, log)
                        if packed:
                            urho_mat.textures["specular"] = packed

                # Copy all textures referenced by this material
                if urho_mat.textures:
                    copy_all_textures(urho_mat.textures, textures_dir, log)
                    texture_count += len(urho_mat.textures)

        return _finish_export(
            self, log, f"Exported {texture_count} texture(s)")


# ---------------------------------------------------------------------------
# Export Scene / Prefabs Only
# ---------------------------------------------------------------------------

class URHO_OT_ExportScene(bpy.types.Operator):
    bl_idname = "urho.export_scene"
    bl_label = "Scene"
    bl_description = "Export only scene and prefab XML files"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.urho_export.output_path)

    def execute(self, context):
        log = ExportLogger()
        settings = _build_settings(context.scene.urho_export)
        _ensure_dirs(settings)

        all_objs = _get_scene_objects(context, settings)
        if not all_objs:
            self.report({'WARNING'}, "No objects to export")
            return {'CANCELLED'}

        scene_nodes = build_scene_hierarchy(all_objs, settings, log)
        exported = 0

        if scene_nodes:
            # Always write scene XML
            scenes_dir = _get_dir(settings, "scenes")
            scene_path = os.path.join(scenes_dir, "Scene.xml")
            if write_scene(scene_nodes, scene_path, log):
                exported += 1
            # ViewerConfig
            viewer_cfg = compute_viewer_config(
                scene_nodes, getattr(context.scene, 'world', None))
            write_viewer_config(
                viewer_cfg, os.path.join(scenes_dir, "ViewerConfig.xml"), log)

            # Always write prefabs
            objects_dir = _get_dir(settings, "objects")
            for node in scene_nodes:
                prefab_name = node.original_name or node.name
                prefab_path = os.path.join(objects_dir, f"{prefab_name}.xml")
                if write_prefab(node, prefab_path, log):
                    exported += 1

        return _finish_export(
            self, log, f"Exported {exported} scene/prefab file(s)")


# ---------------------------------------------------------------------------
# Export Report Dialog
# ---------------------------------------------------------------------------

class URHO_OT_ExportReport(bpy.types.Operator):
    """Show export log report dialog."""
    bl_idname = "urho.export_report"
    bl_label = "Urho3D Export Report"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        log = get_last_export_log()
        if log is None:
            layout.label(text="No export log available.")
            return

        errors = [(lvl, msg) for lvl, msg in log.messages if lvl in ("ERROR", "CRITICAL")]
        warnings = [(lvl, msg) for lvl, msg in log.messages if lvl == "WARNING"]
        infos = [(lvl, msg) for lvl, msg in log.messages if lvl == "INFO"]

        # Summary row
        row = layout.row()
        row.label(text=f"Errors: {len(errors)}", icon='ERROR')
        row.label(text=f"Warnings: {len(warnings)}", icon='INFO')
        row.label(text=f"Info: {len(infos)}", icon='CHECKMARK')

        # Errors
        if errors:
            box = layout.box()
            box.label(text="Errors", icon='ERROR')
            for _, msg in errors[:20]:
                box.label(text=msg)
            if len(errors) > 20:
                box.label(text=f"... and {len(errors) - 20} more errors")

        # Warnings
        if warnings:
            box = layout.box()
            box.label(text="Warnings", icon='INFO')
            for _, msg in warnings[:20]:
                box.label(text=msg)
            if len(warnings) > 20:
                box.label(text=f"... and {len(warnings) - 20} more warnings")

        # Info (show last 10)
        if infos:
            box = layout.box()
            box.label(text=f"Info ({len(infos)} messages)", icon='CHECKMARK')
            for _, msg in infos[-10:]:
                box.label(text=msg)
            if len(infos) > 10:
                box.label(text=f"... showing last 10 of {len(infos)}")
