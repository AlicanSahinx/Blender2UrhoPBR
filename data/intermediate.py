from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


@dataclass
class IntermediateVertex:
    """A unique vertex with all per-loop attributes."""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal: Optional[Tuple[float, float, float]] = None
    uv: Optional[Tuple[float, float]] = None
    uv2: Optional[Tuple[float, float]] = None
    tangent: Optional[Tuple[float, float, float, float]] = None
    color: Optional[Tuple[int, int, int, int]] = None  # RGBA 0-255
    bone_weights: Optional[Tuple[float, ...]] = None    # up to 4
    bone_indices: Optional[Tuple[int, ...]] = None      # up to 4
    blender_index: Optional[int] = None  # original Blender vertex index

    def hash_key(self) -> tuple:
        """Hashable key for vertex deduplication."""
        return (
            self.position,
            self.normal,
            self.uv,
            self.uv2,
            self.color,
        )


@dataclass
class IntermediateLodLevel:
    """A single LOD level within a geometry."""
    distance: float = 0.0
    triangles: List[Tuple[int, int, int]] = field(default_factory=list)


@dataclass
class IntermediateGeometry:
    """A geometry (one per material slot)."""
    material_name: str = ""
    material_index: int = 0
    lod_levels: List[IntermediateLodLevel] = field(default_factory=list)


@dataclass
class IntermediateMorphVertex:
    """A morphed vertex delta."""
    vertex_index: int = 0
    position_delta: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    normal_delta: Optional[Tuple[float, float, float]] = None
    tangent_delta: Optional[Tuple[float, float, float]] = None


@dataclass
class IntermediateMorph:
    """A single morph target (shape key)."""
    name: str = ""
    vertices: List[IntermediateMorphVertex] = field(default_factory=list)


@dataclass
class IntermediateBone:
    """A skeleton bone."""
    name: str = ""
    index: int = 0
    parent_index: int = 0  # same as own index if root
    bind_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bind_rotation: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)  # wxyz
    bind_scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    inverse_bind_matrix: Optional[List[List[float]]] = None  # 3x4 row-major
    collision_mask: int = 0
    bounding_sphere_radius: float = 0.0
    bounding_box_min: Optional[Tuple[float, float, float]] = None
    bounding_box_max: Optional[Tuple[float, float, float]] = None


@dataclass
class IntermediateTrackKeyframe:
    """A single keyframe in an animation track."""
    time: float = 0.0
    position: Optional[Tuple[float, float, float]] = None
    rotation: Optional[Tuple[float, float, float, float]] = None  # wxyz
    scale: Optional[Tuple[float, float, float]] = None


@dataclass
class IntermediateTrack:
    """An animation track (one per bone)."""
    name: str = ""
    keyframes: List[IntermediateTrackKeyframe] = field(default_factory=list)


@dataclass
class IntermediateAnimation:
    """A complete animation."""
    name: str = ""
    duration: float = 0.0
    tracks: List[IntermediateTrack] = field(default_factory=list)


@dataclass
class IntermediateMaterial:
    """Material properties extracted from Blender."""
    name: str = ""
    diffuse_color: Tuple[float, float, float, float] = (0.8, 0.8, 0.8, 1.0)
    specular_color: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    emissive_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    metallic: float = 0.0
    roughness: float = 0.5
    textures: Dict[str, str] = field(default_factory=dict)  # unit_name -> image_name
    two_sided: bool = False
    alpha_mask: bool = False
    unlit: bool = False
    technique_name: str = ""


@dataclass
class IntermediateModel:
    """All data for a single exported object."""
    name: str = ""
    vertices: List[IntermediateVertex] = field(default_factory=list)
    geometries: List[IntermediateGeometry] = field(default_factory=list)
    morphs: List[IntermediateMorph] = field(default_factory=list)
    bones: List[IntermediateBone] = field(default_factory=list)
    animations: List[IntermediateAnimation] = field(default_factory=list)
    materials: List[IntermediateMaterial] = field(default_factory=list)
    bbox_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)
