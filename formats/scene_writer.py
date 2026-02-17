"""Write Urho3D scene and prefab XML files."""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement
from typing import List

from ..core.logging import ExportLogger
from ..data.urho_scene import UrhoSceneNode, ViewerConfig
from .xml_utils import write_xml_file, vector3_to_str, quaternion_to_str


_next_id = 0


def _get_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


def _reset_ids():
    global _next_id
    _next_id = 0


_LIGHT_TYPE_MAP = {"Directional": "Directional", "Point": "Point", "Spot": "Spot"}


def _blender_energy_to_brightness(light_type: str, energy: float) -> float:
    """Convert Blender light energy (watts) to Urho3D brightness multiplier.

    Blender uses physical units:
      - Sun: energy 1.0 ≈ overcast, 5-10 ≈ bright day
      - Point/Spot: energy in watts (100-1000 typical)

    Urho3D brightness multiplier defaults to 1.0.
    """
    if light_type == "Directional":
        # Sun: Blender 1.0 → Urho3D ~1.5, Blender 5.0 → ~3.0
        return max(0.5, energy * 1.5)
    else:
        # Point/Spot: Blender watts → reasonable multiplier
        # 100W → ~1.0, 1000W → ~3.2
        return max(0.5, (energy / 100.0) ** 0.5)


def _write_transform(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write position/rotation/scale attributes if non-default."""
    if node.position != (0.0, 0.0, 0.0):
        SubElement(node_elem, "attribute", name="Position",
                   value=vector3_to_str(*node.position))
    if node.rotation != (1.0, 0.0, 0.0, 0.0):
        SubElement(node_elem, "attribute", name="Rotation",
                   value=quaternion_to_str(*node.rotation))
    if node.scale != (1.0, 1.0, 1.0):
        SubElement(node_elem, "attribute", name="Scale",
                   value=vector3_to_str(*node.scale))


def _write_light(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write Urho3D Light component."""
    comp = SubElement(node_elem, "component", type="Light", id=str(_get_id()))
    SubElement(comp, "attribute", name="Light Type",
               value=node.light_type)

    c = node.light_color
    SubElement(comp, "attribute", name="Color",
               value=f"{c[0]:.4g} {c[1]:.4g} {c[2]:.4g} {c[3]:.4g}")

    if node.light_type != "Directional":
        SubElement(comp, "attribute", name="Range",
                   value=f"{node.light_range:.4g}")

    if node.light_type == "Spot":
        SubElement(comp, "attribute", name="Spot FOV",
                   value=f"{node.light_spot_fov:.4g}")

    SubElement(comp, "attribute", name="Specular Intensity",
               value=f"{node.light_specular:.4g}")

    # Brightness from Blender energy
    brightness = _blender_energy_to_brightness(node.light_type, node.light_energy)
    if brightness != 1.0:
        SubElement(comp, "attribute", name="Brightness Multiplier",
                   value=f"{brightness:.4g}")

    if node.light_cast_shadows:
        SubElement(comp, "attribute", name="Cast Shadows", value="true")


def _write_camera(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write Urho3D Camera component."""
    comp = SubElement(node_elem, "component", type="Camera", id=str(_get_id()))
    SubElement(comp, "attribute", name="Near Clip",
               value=f"{node.camera_near:.4g}")
    SubElement(comp, "attribute", name="Far Clip",
               value=f"{node.camera_far:.4g}")

    if node.camera_ortho:
        SubElement(comp, "attribute", name="Orthographic", value="true")
        SubElement(comp, "attribute", name="Ortho Size",
                   value=f"{node.camera_ortho_size:.4g}")
    else:
        SubElement(comp, "attribute", name="FOV",
                   value=f"{node.camera_fov:.4g}")


def _write_tags(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write Urho3D node Tags attribute from suffix flags.

    Tags are StringVector type — serialized as child <string> elements,
    not as a semicolon-separated value attribute.
    """
    tags: list[str] = []
    if node.no_collision:
        tags.append("nocol")
    if node.is_billboard:
        tags.append("billboard")
    if tags:
        tags_elem = SubElement(node_elem, "attribute", name="Tags")
        for tag in tags:
            SubElement(tags_elem, "string", value=tag)


def _write_navmesh(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write a navmesh-only node: invisible model + Navigable component."""
    comp = SubElement(node_elem, "component", type="StaticModel", id=str(_get_id()))
    SubElement(comp, "attribute", name="Model", value=f"Model;{node.model_path}")
    SubElement(comp, "attribute", name="Cast Shadows", value="false")
    SubElement(comp, "attribute", name="Is Enabled", value="false")
    # Navigable component for Urho3D navigation system
    SubElement(node_elem, "component", type="Navigable", id=str(_get_id()))


def _write_trigger_body(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write a ghost RigidBody + CollisionShape for trigger volumes."""
    comp = SubElement(node_elem, "component", type="RigidBody", id=str(_get_id()))
    SubElement(comp, "attribute", name="Mass", value="0")
    SubElement(comp, "attribute", name="Is Trigger", value="true")
    SubElement(comp, "attribute", name="Is Kinematic", value="true")
    _write_collision_shape(node_elem, node)


def _write_mesh(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write StaticModel or AnimatedModel component with suffix flags."""
    if not node.model_path:
        return

    # Tags (nocol, billboard)
    _write_tags(node_elem, node)

    # Navmesh: invisible model + Navigable, no other components
    if node.is_navmesh:
        _write_navmesh(node_elem, node)
        return

    comp_type = "AnimatedModel" if node.is_animated else "StaticModel"
    comp = SubElement(node_elem, "component", type=comp_type, id=str(_get_id()))
    SubElement(comp, "attribute", name="Model", value=f"Model;{node.model_path}")

    if node.material_paths:
        # ResourceRefList: "Material;path1;path2;path3"
        mat_value = "Material;" + ";".join(node.material_paths)
        SubElement(comp, "attribute", name="Material", value=mat_value)

    if node.cast_shadows:
        SubElement(comp, "attribute", name="Cast Shadows", value="true")

    if node.is_occluder:
        SubElement(comp, "attribute", name="Is Occluder", value="true")

    # Note: _lod1/_lod2 suffixes affect file naming only.
    # Urho3D LOD is per-geometry inside .mdl, not a scene attribute.

    # AnimationController for animated models
    if node.is_animated and node.animation_paths:
        SubElement(node_elem, "component", type="AnimationController",
                   id=str(_get_id()))

    # Physics components
    if node.no_collision:
        pass  # no physics; SceneViewer respects "nocol" tag
    elif node.is_trigger:
        _write_trigger_body(node_elem, node)
    elif node.has_rigid_body:
        _write_rigid_body(node_elem, node)
        _write_collision_shape(node_elem, node)


def _write_rigid_body(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write Urho3D RigidBody component."""
    comp = SubElement(node_elem, "component", type="RigidBody", id=str(_get_id()))
    SubElement(comp, "attribute", name="Mass", value=f"{node.rb_mass:.4g}")
    SubElement(comp, "attribute", name="Friction", value=f"{node.rb_friction:.4g}")
    SubElement(comp, "attribute", name="Restitution",
               value=f"{node.rb_restitution:.4g}")


def _write_collision_shape(node_elem: Element, node: UrhoSceneNode) -> None:
    """Write Urho3D CollisionShape component."""
    if not node.collision_shape:
        return

    comp = SubElement(node_elem, "component", type="CollisionShape",
                      id=str(_get_id()))

    SubElement(comp, "attribute", name="Shape Type", value=node.collision_shape)

    if node.collision_shape == "Box":
        s = node.collision_size
        SubElement(comp, "attribute", name="Size",
                   value=f"{s[0]:.4g} {s[1]:.4g} {s[2]:.4g}")
    elif node.collision_shape == "Sphere":
        SubElement(comp, "attribute", name="Size",
                   value=f"{node.collision_radius:.4g} {node.collision_radius:.4g} {node.collision_radius:.4g}")
    elif node.collision_shape in ("Capsule", "Cylinder"):
        SubElement(comp, "attribute", name="Size",
                   value=f"{node.collision_radius * 2:.4g} {node.collision_height:.4g} {node.collision_radius * 2:.4g}")
    elif node.collision_shape in ("ConvexHull", "TriangleMesh"):
        if node.collision_model:
            SubElement(comp, "attribute", name="Model", value=node.collision_model)


def _write_node(parent_element: Element, node: UrhoSceneNode) -> None:
    """Recursively write a scene node and its children."""
    node_elem = SubElement(parent_element, "node", id=str(_get_id()))

    SubElement(node_elem, "attribute", name="Is Enabled", value="true")
    SubElement(node_elem, "attribute", name="Name", value=node.name)

    _write_transform(node_elem, node)

    if node.node_type == "mesh":
        _write_mesh(node_elem, node)
    elif node.node_type == "light":
        _write_light(node_elem, node)
    elif node.node_type == "camera":
        _write_camera(node_elem, node)
    # "empty" nodes: just transform, no component

    for child in node.children:
        _write_node(node_elem, child)


def _has_light_recursive(node: UrhoSceneNode) -> bool:
    """Check if a node or any of its children is a light."""
    if node.node_type == "light":
        return True
    return any(_has_light_recursive(c) for c in node.children)


def _write_default_light(parent: Element) -> None:
    """Write a default directional (sun) light when no lights are exported."""
    light_node = SubElement(parent, "node", id=str(_get_id()))
    SubElement(light_node, "attribute", name="Is Enabled", value="true")
    SubElement(light_node, "attribute", name="Name", value="DefaultSunLight")
    # Rotation: angled down ~55° from horizon for natural sunlight look
    SubElement(light_node, "attribute", name="Rotation",
               value="0.8195 0.4266 -0.1767 0.3394")
    comp = SubElement(light_node, "component", type="Light", id=str(_get_id()))
    SubElement(comp, "attribute", name="Light Type", value="Directional")
    SubElement(comp, "attribute", name="Color", value="1 0.95 0.9 1")
    SubElement(comp, "attribute", name="Brightness Multiplier", value="8")
    SubElement(comp, "attribute", name="Specular Intensity", value="1")
    SubElement(comp, "attribute", name="Cast Shadows", value="true")


def write_scene(
    nodes: List[UrhoSceneNode],
    filepath: str,
    log: ExportLogger,
) -> bool:
    """Write a full Urho3D scene XML file."""
    try:
        _reset_ids()
        root = Element("scene", id=str(_get_id()))

        # Scene components
        SubElement(root, "component", type="Octree", id=str(_get_id()))
        SubElement(root, "component", type="DebugRenderer", id=str(_get_id()))

        # Default Zone (ambient lighting + fog)
        zone_node = SubElement(root, "node", id=str(_get_id()))
        SubElement(zone_node, "attribute", name="Name", value="Zone")
        zone_comp = SubElement(zone_node, "component", type="Zone",
                               id=str(_get_id()))
        SubElement(zone_comp, "attribute", name="Bounding Box Min",
                   value="-1000 -1000 -1000")
        SubElement(zone_comp, "attribute", name="Bounding Box Max",
                   value="1000 1000 1000")
        SubElement(zone_comp, "attribute", name="Ambient Color",
                   value="0.5 0.5 0.5 1")
        SubElement(zone_comp, "attribute", name="Fog Color",
                   value="0.5 0.5 0.7 1")
        SubElement(zone_comp, "attribute", name="Fog Start", value="100")
        SubElement(zone_comp, "attribute", name="Fog End", value="300")

        # Scene nodes
        for node in nodes:
            _write_node(root, node)

        # Add default directional light if no lights in scene
        has_light = any(_has_light_recursive(n) for n in nodes)
        if not has_light:
            _write_default_light(root)

        write_xml_file(root, filepath)

    except Exception as e:
        log.error(f"Failed to write scene '{filepath}': {e}")
        return False

    log.info(f"Written scene: {filepath}")
    return True


def write_prefab(
    node: UrhoSceneNode,
    filepath: str,
    log: ExportLogger,
) -> bool:
    """Write a single Urho3D prefab (node) XML file."""
    try:
        _reset_ids()
        root = Element("node", id=str(_get_id()))

        SubElement(root, "attribute", name="Is Enabled", value="true")
        SubElement(root, "attribute", name="Name", value=node.name)

        if node.position != (0.0, 0.0, 0.0):
            SubElement(root, "attribute", name="Position",
                       value=vector3_to_str(*node.position))
        if node.rotation != (1.0, 0.0, 0.0, 0.0):
            SubElement(root, "attribute", name="Rotation",
                       value=quaternion_to_str(*node.rotation))
        if node.scale != (1.0, 1.0, 1.0):
            SubElement(root, "attribute", name="Scale",
                       value=vector3_to_str(*node.scale))

        # Model component
        if node.model_path:
            comp_type = "AnimatedModel" if node.is_animated else "StaticModel"
            comp = SubElement(root, "component", type=comp_type, id=str(_get_id()))
            SubElement(comp, "attribute", name="Model", value=f"Model;{node.model_path}")

            if node.material_paths:
                mat_value = "Material;" + ";".join(node.material_paths)
                SubElement(comp, "attribute", name="Material", value=mat_value)

            if node.cast_shadows:
                SubElement(comp, "attribute", name="Cast Shadows", value="true")

        # Children
        for child in node.children:
            _write_node(root, child)

        write_xml_file(root, filepath)

    except Exception as e:
        log.error(f"Failed to write prefab '{filepath}': {e}")
        return False

    log.info(f"Written prefab: {filepath}")
    return True


def write_viewer_config(
    config: ViewerConfig,
    filepath: str,
    log: ExportLogger,
) -> bool:
    """Write ViewerConfig.xml alongside the scene file."""
    try:
        root = Element("viewerConfig", version="1")

        # Camera target
        SubElement(root, "camera",
                   target=vector3_to_str(*config.camera_target))

        # Light energies
        for name, light_type, energy in config.light_energies:
            SubElement(root, "light",
                       name=name, type=light_type, energy=f"{energy:g}")

        # Zone
        SubElement(root, "zone",
                   ambientColor=vector3_to_str(*config.ambient_color),
                   fogColor=vector3_to_str(*config.fog_color))

        # Feature toggles
        SubElement(root, "fillLight",
                   enabled="true" if config.fill_light_enabled else "false")
        SubElement(root, "skybox",
                   enabled="true" if config.skybox_enabled else "false")
        SubElement(root, "fxaa",
                   enabled="true" if config.fxaa_enabled else "false")

        write_xml_file(root, filepath)

    except Exception as e:
        log.error(f"Failed to write viewer config '{filepath}': {e}")
        return False

    log.info(f"Written viewer config: {filepath}")
    return True
