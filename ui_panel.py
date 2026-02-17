import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    StringProperty,
)


class UrhoExportSettings(bpy.types.PropertyGroup):
    """Export settings stored per-scene."""

    # --- Output ---
    output_path: StringProperty(
        name="Output Path",
        description="Root output directory for exported Urho3D resources",
        default="",
        subtype='DIR_PATH',
    )

    use_subdirs: BoolProperty(
        name="Use Subdirectories",
        description="Organize output into Models/, Materials/, Textures/ etc.",
        default=True,
    )

    overwrite: BoolProperty(
        name="Overwrite Existing",
        description="Overwrite existing files",
        default=True,
    )

    # --- Source ---
    only_selected: BoolProperty(
        name="Only Selected",
        description="Export only selected objects",
        default=True,
    )

    scale: FloatProperty(
        name="Scale",
        description="Global scale factor",
        default=1.0,
        min=0.001,
        max=1000.0,
    )

    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers before export",
        default=False,
    )

    use_local_origin: BoolProperty(
        name="Use Local Origin",
        description="Use object's local origin instead of world origin",
        default=True,
    )

    # --- Geometry ---
    export_normal: BoolProperty(
        name="Normals",
        description="Export vertex normals",
        default=True,
    )

    export_uv: BoolProperty(
        name="UV Coordinates",
        description="Export UV coordinates (first UV layer)",
        default=True,
    )

    export_uv2: BoolProperty(
        name="UV2 Coordinates",
        description="Export second UV layer",
        default=False,
    )

    export_tangent: BoolProperty(
        name="Tangents",
        description="Export tangent vectors (requires normals and UVs)",
        default=True,
    )

    export_color: BoolProperty(
        name="Vertex Colors",
        description="Export vertex color attributes",
        default=False,
    )

    # --- Skeleton ---
    export_skeleton: BoolProperty(
        name="Skeleton",
        description="Export armature as skeleton bones",
        default=False,
    )

    only_deform_bones: BoolProperty(
        name="Only Deform Bones",
        description="Export only bones that have the Deform flag enabled",
        default=False,
    )

    only_visible_bones: BoolProperty(
        name="Only Visible Bones",
        description="Export only bones in visible bone collections",
        default=False,
    )

    # --- Animation ---
    export_animations: BoolProperty(
        name="Animations",
        description="Export skeletal animations",
        default=False,
    )

    animation_source: EnumProperty(
        name="Animation Source",
        description="Which animations to export",
        items=[
            ('USED_ACTIONS', "Used Actions", "Actions assigned to the armature"),
            ('ALL_ACTIONS', "All Actions", "All actions in the blend file"),
            ('NLA_TRACKS', "NLA Tracks", "Baked NLA track strips"),
            ('TIMELINE', "Timeline", "Current timeline range"),
        ],
        default='USED_ACTIONS',
    )

    export_anim_position: BoolProperty(
        name="Position Keys",
        description="Export bone position keyframes",
        default=True,
    )

    export_anim_rotation: BoolProperty(
        name="Rotation Keys",
        description="Export bone rotation keyframes",
        default=True,
    )

    export_anim_scale: BoolProperty(
        name="Scale Keys",
        description="Export bone scale keyframes",
        default=False,
    )

    # --- Morphs ---
    export_morphs: BoolProperty(
        name="Morph Targets",
        description="Export shape keys as morph targets",
        default=False,
    )

    export_morph_normals: BoolProperty(
        name="Morph Normals",
        description="Export morph target normals",
        default=True,
    )

    export_morph_tangents: BoolProperty(
        name="Morph Tangents",
        description="Export morph target tangents",
        default=False,
    )

    # --- Materials ---
    export_materials: BoolProperty(
        name="Materials",
        description="Export materials as Urho3D XML",
        default=True,
    )

    prefer_pbr: BoolProperty(
        name="Prefer PBR Techniques",
        description="Use PBR/PBRMetallicRough* techniques when metallic/roughness data is present",
        default=True,
    )

    copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy texture images to output directory",
        default=False,
    )

    pack_pbr_textures: BoolProperty(
        name="Pack PBR Textures",
        description="Combine separate metallic and roughness maps into a single image (R=Roughness, G=Metallic)",
        default=True,
    )

    # --- Optimization ---
    optimize_indices: BoolProperty(
        name="Optimize Vertex Cache",
        description="Reorder triangles for optimal GPU vertex cache utilization (Forsyth algorithm)",
        default=True,
    )

    # --- Scene ---
    export_prefabs: BoolProperty(
        name="Prefabs",
        description="Export objects as Urho3D prefab XML",
        default=False,
    )

    export_scene: BoolProperty(
        name="Scene",
        description="Export full scene as Urho3D scene XML",
        default=False,
    )

    cast_shadows: BoolProperty(
        name="Cast Shadows",
        description="Enable shadow casting on exported models",
        default=True,
    )

    preview: BoolProperty(
        name="Preview",
        description="Launch SceneViewer after export",
        default=False,
    )


class URHO_PT_ExportPanel(bpy.types.Panel):
    bl_label = "Urho3D Export"
    bl_idname = "URHO_PT_export_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.urho_export

        # Output
        box = layout.box()
        box.label(text="Output", icon='EXPORT')
        box.prop(settings, "output_path")
        row = box.row()
        row.prop(settings, "use_subdirs")
        row.prop(settings, "overwrite")

        # Source
        box = layout.box()
        box.label(text="Source", icon='OBJECT_DATA')
        row = box.row()
        row.prop(settings, "only_selected")
        row.prop(settings, "apply_modifiers")
        box.prop(settings, "scale")
        box.prop(settings, "use_local_origin")

        # Geometry
        box = layout.box()
        box.label(text="Geometry", icon='MESH_DATA')
        row = box.row(align=True)
        row.prop(settings, "export_normal", toggle=True)
        row.prop(settings, "export_uv", toggle=True)
        row.prop(settings, "export_uv2", toggle=True)
        row = box.row(align=True)
        row.prop(settings, "export_tangent", toggle=True)
        row.prop(settings, "export_color", toggle=True)

        # Skeleton
        box = layout.box()
        box.label(text="Skeleton", icon='ARMATURE_DATA')
        box.prop(settings, "export_skeleton")
        if settings.export_skeleton:
            row = box.row()
            row.prop(settings, "only_deform_bones")
            row.prop(settings, "only_visible_bones")

        # Animation
        box = layout.box()
        box.label(text="Animation", icon='ANIM')
        box.prop(settings, "export_animations")
        if settings.export_animations:
            box.prop(settings, "animation_source")
            row = box.row(align=True)
            row.prop(settings, "export_anim_position", toggle=True)
            row.prop(settings, "export_anim_rotation", toggle=True)
            row.prop(settings, "export_anim_scale", toggle=True)

        # Morphs
        box = layout.box()
        box.label(text="Morph Targets", icon='SHAPEKEY_DATA')
        box.prop(settings, "export_morphs")
        if settings.export_morphs:
            row = box.row()
            row.prop(settings, "export_morph_normals")
            row.prop(settings, "export_morph_tangents")

        # Materials
        box = layout.box()
        box.label(text="Materials", icon='MATERIAL')
        box.prop(settings, "export_materials")
        if settings.export_materials:
            box.prop(settings, "prefer_pbr")
            box.prop(settings, "copy_textures")
            if settings.prefer_pbr:
                box.prop(settings, "pack_pbr_textures")

        # Optimization
        box = layout.box()
        box.label(text="Optimization", icon='MOD_DECIM')
        box.prop(settings, "optimize_indices")

        # Scene
        box = layout.box()
        box.label(text="Scene", icon='SCENE_DATA')
        row = box.row()
        row.prop(settings, "export_prefabs")
        row.prop(settings, "export_scene")
        box.prop(settings, "cast_shadows")

        # Export buttons
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("urho.export", icon='EXPORT')
        row.operator("urho.export_report", text="", icon='TEXT')
        row = layout.row()
        row.prop(settings, "preview", icon='PLAY')

        # Individual export buttons
        box = layout.box()
        box.label(text="Export Individual", icon='DOWNARROW_HLT')
        row = box.row(align=True)
        row.operator("urho.export_models", icon='MESH_DATA')
        row.operator("urho.export_materials", icon='MATERIAL')
        row.operator("urho.export_animations", icon='ANIM')
        row = box.row(align=True)
        row.operator("urho.export_textures", icon='TEXTURE')
        row.operator("urho.export_scene", icon='SCENE_DATA')
