"""Scene graph hierarchy extraction from Blender."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:
    import bpy

from ..core.logging import ExportLogger
from ..core.name_parser import material_suffix, parse_object_name
from ..core.types import ExportSettings
from ..data.urho_scene import UrhoSceneNode, ViewerConfig


def _blender_to_urho_pos(co, scale: float) -> Tuple[float, float, float]:
    return (co[0] * scale, co[2] * scale, co[1] * scale)


def _blender_to_urho_quat(q) -> Tuple[float, float, float, float]:
    return (q.w, -q.x, -q.z, -q.y)


def _blender_to_urho_scale(s) -> Tuple[float, float, float]:
    return (s[0], s[2], s[1])


_BLENDER_LIGHT_MAP = {
    'SUN': 'Directional',
    'POINT': 'Point',
    'SPOT': 'Spot',
    'AREA': 'Point',  # approximate
}


def _make_base_node(obj, settings: ExportSettings, node_type: str) -> UrhoSceneNode:
    """Create a node with common transform fields."""
    return UrhoSceneNode(
        name=obj.name,
        node_type=node_type,
        position=_blender_to_urho_pos(obj.location, settings.scale),
        rotation=_blender_to_urho_quat(
            obj.rotation_quaternion
            if obj.rotation_mode == 'QUATERNION'
            else obj.matrix_local.to_quaternion()),
        scale=_blender_to_urho_scale(obj.scale),
        parent_name=obj.parent.name if obj.parent else "",
    )


def _build_mesh_node(obj, settings: ExportSettings) -> UrhoSceneNode:
    node = _make_base_node(obj, settings, "mesh")
    armature_obj = obj.find_armature()
    node.is_animated = armature_obj is not None

    # Parse name suffixes
    parsed = parse_object_name(obj.name)
    node.name = parsed.clean_name
    node.original_name = obj.name

    # Apply suffix flags
    node.cast_shadows = settings.cast_shadows and not parsed.noshadow
    node.no_collision = parsed.nocol
    node.is_occluder = parsed.occluder
    node.is_trigger = parsed.trigger
    node.is_navmesh = parsed.navmesh
    node.is_billboard = parsed.billboard
    node.force_two_side = parsed.two_side
    node.force_alpha = parsed.alpha
    # lod_level stored in parsed but not written to scene XML;
    # Urho3D LOD is per-geometry inside .mdl (future: multi-LOD export).

    # For skinned meshes, use armature's world position/rotation instead
    # of the mesh's local offset (vertices are exported in armature space).
    if armature_obj is not None and settings.export_skeleton:
        node.position = _blender_to_urho_pos(armature_obj.location, settings.scale)
        node.rotation = _blender_to_urho_quat(
            armature_obj.rotation_quaternion
            if armature_obj.rotation_mode == 'QUATERNION'
            else armature_obj.matrix_local.to_quaternion())
        node.scale = _blender_to_urho_scale(armature_obj.scale)

    # Collect animation paths from armature actions
    if armature_obj is not None:
        _collect_animation_paths(armature_obj, node, settings)

    # Model path (without ResourceRef prefix — added by scene_writer)
    models_subdir = settings.paths.models if settings.use_subdirs else ""
    node.model_path = (
        f"{models_subdir}/{obj.name}.mdl"
        if models_subdir else f"{obj.name}.mdl"
    )

    # Material paths (without ResourceRef prefix — added by scene_writer)
    materials_subdir = settings.paths.materials if settings.use_subdirs else ""
    mat_sfx = material_suffix(parsed)
    for slot in obj.material_slots:
        if slot.material:
            mat_name = slot.material.name + mat_sfx
            mat_path = (
                f"{materials_subdir}/{mat_name}.xml"
                if materials_subdir
                else f"{mat_name}.xml"
            )
            node.material_paths.append(mat_path)

    # Physics: skip for nocol, setup trigger ghost, or detect Blender rigid body
    if parsed.nocol:
        pass  # no physics at all
    elif parsed.trigger:
        _detect_physics(obj, node, settings)
        node.has_rigid_body = True
        node.is_trigger = True
        node.rb_mass = 0.0
    else:
        _detect_physics(obj, node, settings)

    return node


def _collect_animation_paths(armature_obj, node: UrhoSceneNode,
                             settings: ExportSettings) -> None:
    """Find all actions used by the armature and build animation resource paths."""
    anim_subdir = settings.paths.animations if settings.use_subdirs else ""
    seen = set()

    # Current action
    if armature_obj.animation_data and armature_obj.animation_data.action:
        name = armature_obj.animation_data.action.name
        if name not in seen:
            seen.add(name)
            path = (f"{anim_subdir}/{name}.ani" if anim_subdir
                    else f"{name}.ani")
            node.animation_paths.append(path)

    # NLA strips
    if armature_obj.animation_data:
        for track in armature_obj.animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action and strip.action.name not in seen:
                    seen.add(strip.action.name)
                    name = strip.action.name
                    path = (f"{anim_subdir}/{name}.ani" if anim_subdir
                            else f"{name}.ani")
                    node.animation_paths.append(path)


def _detect_physics(obj, node: UrhoSceneNode, settings: ExportSettings) -> None:
    """Detect Blender rigid body and collision shape, map to Urho3D."""
    rb = getattr(obj, 'rigid_body', None)
    if rb is None:
        return

    node.has_rigid_body = True
    node.rb_mass = 0.0 if rb.type == 'PASSIVE' else rb.mass
    node.rb_friction = rb.friction
    node.rb_restitution = rb.restitution

    # Map Blender collision shape to Urho3D
    shape = rb.collision_shape
    dims = obj.dimensions * settings.scale

    if shape == 'BOX':
        node.collision_shape = "Box"
        node.collision_size = (dims.x, dims.z, dims.y)  # Y↔Z swap
    elif shape == 'SPHERE':
        node.collision_shape = "Sphere"
        node.collision_radius = max(dims) * 0.5
    elif shape == 'CAPSULE':
        node.collision_shape = "Capsule"
        node.collision_radius = max(dims.x, dims.y) * 0.5
        node.collision_height = dims.z
    elif shape == 'CYLINDER':
        node.collision_shape = "Cylinder"
        node.collision_radius = max(dims.x, dims.y) * 0.5
        node.collision_height = dims.z
    elif shape == 'CONVEX_HULL':
        node.collision_shape = "ConvexHull"
        models_subdir = settings.paths.models if settings.use_subdirs else ""
        node.collision_model = (
            f"Model;{models_subdir}/{obj.name}.mdl"
            if models_subdir else f"Model;{obj.name}.mdl"
        )
    elif shape == 'MESH':
        node.collision_shape = "TriangleMesh"
        models_subdir = settings.paths.models if settings.use_subdirs else ""
        node.collision_model = (
            f"Model;{models_subdir}/{obj.name}.mdl"
            if models_subdir else f"Model;{obj.name}.mdl"
        )
    else:
        # Fallback: use bounding box as Box shape
        node.collision_shape = "Box"
        node.collision_size = (dims.x, dims.z, dims.y)


def _build_light_node(obj, settings: ExportSettings) -> UrhoSceneNode:
    node = _make_base_node(obj, settings, "light")
    light = obj.data

    node.light_type = _BLENDER_LIGHT_MAP.get(light.type, 'Point')
    node.light_color = (light.color[0], light.color[1], light.color[2], 1.0)
    node.light_energy = light.energy
    node.light_cast_shadows = getattr(light, 'use_shadow', True)

    if light.type in ('POINT', 'SPOT', 'AREA'):
        # Blender uses watts; Urho3D uses a simple range.
        # Rough heuristic: range ≈ sqrt(energy) * scale
        node.light_range = max(1.0, (light.energy ** 0.5) * settings.scale)

    if light.type == 'SPOT':
        import math
        node.light_spot_fov = math.degrees(light.spot_size)

    return node


def _build_camera_node(obj, settings: ExportSettings) -> UrhoSceneNode:
    node = _make_base_node(obj, settings, "camera")
    cam = obj.data

    import math
    if cam.type == 'ORTHO':
        node.camera_ortho = True
        node.camera_ortho_size = cam.ortho_scale * settings.scale
    else:
        node.camera_fov = math.degrees(cam.angle)

    node.camera_near = cam.clip_start * settings.scale
    node.camera_far = cam.clip_end * settings.scale
    return node


def compute_viewer_config(
    nodes: List[UrhoSceneNode],
    blender_world=None,
) -> ViewerConfig:
    """Compute ViewerConfig from scene nodes and Blender world settings."""
    config = ViewerConfig()

    # Camera target: bounding box center of all mesh nodes (Urho3D coords)
    mesh_positions: List[Tuple[float, float, float]] = []
    _collect_positions(nodes, "mesh", mesh_positions)
    if mesh_positions:
        min_x = min(p[0] for p in mesh_positions)
        max_x = max(p[0] for p in mesh_positions)
        min_y = min(p[1] for p in mesh_positions)
        max_y = max(p[1] for p in mesh_positions)
        min_z = min(p[2] for p in mesh_positions)
        max_z = max(p[2] for p in mesh_positions)
        config.camera_target = (
            (min_x + max_x) * 0.5,
            (min_y + max_y) * 0.5,
            (min_z + max_z) * 0.5,
        )

    # Light energies
    _collect_light_energies(nodes, config.light_energies)

    # World ambient from Blender Background node
    if blender_world and getattr(blender_world, 'use_nodes', False):
        bg = _find_background_node(blender_world)
        if bg:
            try:
                c = bg.inputs['Color'].default_value
                config.ambient_color = (c[0], c[1], c[2])
            except (KeyError, IndexError):
                pass

    return config


def _collect_positions(
    nodes: List[UrhoSceneNode],
    node_type: str,
    out: List[Tuple[float, float, float]],
) -> None:
    for node in nodes:
        if node.node_type == node_type:
            out.append(node.position)
        _collect_positions(node.children, node_type, out)


def _collect_light_energies(
    nodes: List[UrhoSceneNode],
    out: List[Tuple[str, str, float]],
) -> None:
    for node in nodes:
        if node.node_type == "light":
            out.append((node.name, node.light_type, node.light_energy))
        _collect_light_energies(node.children, out)


def _find_background_node(world):
    """Find the Background shader node in a Blender world node tree."""
    if not getattr(world, 'node_tree', None):
        return None
    for node in world.node_tree.nodes:
        if node.type == 'BACKGROUND':
            return node
    return None


_LOD_SUFFIX_RE = __import__('re').compile(r'^.+_LOD\d+\.?\d*$')


def build_scene_hierarchy(
    objects: list,
    settings: ExportSettings,
    log: ExportLogger,
) -> List[UrhoSceneNode]:
    """
    Build a list of UrhoSceneNode from Blender objects,
    preserving parent-child relationships.
    Handles MESH, LIGHT, CAMERA, and EMPTY types.
    Returns root-level nodes (with children nested).
    LOD variant objects (e.g. MyMesh_LOD1) are skipped —
    their geometry is merged into the base .mdl file.
    """
    node_map: Dict[str, UrhoSceneNode] = {}

    for obj in objects:
        # Skip LOD variant meshes — they're merged into the base model
        if obj.type == 'MESH' and _LOD_SUFFIX_RE.match(obj.name):
            continue

        if obj.type == 'MESH':
            node = _build_mesh_node(obj, settings)
        elif obj.type == 'LIGHT':
            node = _build_light_node(obj, settings)
            log.info(f"Light '{obj.name}': {node.light_type}")
        elif obj.type == 'CAMERA':
            node = _build_camera_node(obj, settings)
            log.info(f"Camera '{obj.name}': fov={node.camera_fov:.1f}")
        elif obj.type == 'EMPTY':
            node = _make_base_node(obj, settings, "empty")
        else:
            continue

        node_map[obj.name] = node

    # Build tree
    roots = []
    for name, node in node_map.items():
        if node.parent_name and node.parent_name in node_map:
            node_map[node.parent_name].children.append(node)
        else:
            roots.append(node)

    return roots
