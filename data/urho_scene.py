"""Urho3D scene data structures."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ViewerConfig:
    """Viewer configuration hints exported alongside the scene."""
    camera_target: Tuple[float, float, float] = (0.0, 2.0, 0.0)
    light_energies: List[Tuple[str, str, float]] = field(default_factory=list)
    # Each tuple: (node_name, light_type, blender_energy)
    ambient_color: Tuple[float, float, float] = (0.15, 0.15, 0.2)
    fog_color: Tuple[float, float, float] = (0.5, 0.5, 0.7)
    fill_light_enabled: bool = True
    skybox_enabled: bool = True
    fxaa_enabled: bool = True


@dataclass
class UrhoSceneNode:
    """A node in the Urho3D scene hierarchy."""
    name: str = ""
    node_type: str = "mesh"  # mesh, light, camera, empty
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)  # wxyz
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    parent_name: str = ""
    # Mesh
    model_path: str = ""
    material_paths: List[str] = field(default_factory=list)
    is_animated: bool = False
    animation_paths: List[str] = field(default_factory=list)  # e.g. ["Animations/Walk.ani"]
    cast_shadows: bool = False
    # Suffix-derived flags (from name_parser)
    original_name: str = ""        # Blender object name (for .mdl / prefab filenames)
    is_occluder: bool = False
    is_trigger: bool = False
    is_navmesh: bool = False
    is_billboard: bool = False
    lod_distance: float = 0.0     # 0 = default/LOD0
    no_collision: bool = False     # skip physics entirely
    force_two_side: bool = False   # material clone: cull=none
    force_alpha: bool = False      # material clone: Alpha technique + ALPHAMASK
    # Light
    light_type: str = ""  # Directional, Point, Spot
    light_color: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    light_range: float = 10.0
    light_spot_fov: float = 30.0
    light_cast_shadows: bool = True
    light_energy: float = 1.0
    light_specular: float = 1.0
    # Camera
    camera_fov: float = 45.0
    camera_near: float = 0.1
    camera_far: float = 1000.0
    camera_ortho: bool = False
    camera_ortho_size: float = 10.0
    # Physics
    has_rigid_body: bool = False
    rb_mass: float = 0.0  # 0 = static
    rb_friction: float = 0.5
    rb_restitution: float = 0.0
    collision_shape: str = ""  # Box, Sphere, Capsule, ConvexHull, TriangleMesh
    collision_size: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    collision_radius: float = 0.5
    collision_height: float = 1.0
    collision_model: str = ""  # model path for ConvexHull/TriangleMesh
    # Children
    children: List['UrhoSceneNode'] = field(default_factory=list)
