from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import os


class PathType(Enum):
    """Urho3D resource path types."""
    ROOT = auto()
    MODELS = auto()
    ANIMATIONS = auto()
    MATERIALS = auto()
    TECHNIQUES = auto()
    TEXTURES = auto()
    OBJECTS = auto()
    SCENES = auto()


@dataclass
class PathConfig:
    """Configurable subdirectory names for Urho3D resource layout."""
    root: str = ""
    models: str = "Models"
    animations: str = "Animations"
    materials: str = "Materials"
    techniques: str = "Techniques"
    textures: str = "Textures"
    objects: str = "Objects"
    scenes: str = "Scenes"

    def get_subdir(self, path_type: PathType) -> str:
        mapping = {
            PathType.ROOT: "",
            PathType.MODELS: self.models,
            PathType.ANIMATIONS: self.animations,
            PathType.MATERIALS: self.materials,
            PathType.TECHNIQUES: self.techniques,
            PathType.TEXTURES: self.textures,
            PathType.OBJECTS: self.objects,
            PathType.SCENES: self.scenes,
        }
        return mapping[path_type]

    def get_full_path(self, path_type: PathType) -> str:
        return os.path.join(self.root, self.get_subdir(path_type))


@dataclass
class ExportSettings:
    """All export settings, populated from the UI PropertyGroup."""

    # Source
    only_selected: bool = True
    scale: float = 1.0
    apply_modifiers: bool = False
    use_local_origin: bool = True
    forward_axis: str = 'Z'  # Urho3D default: Z forward
    up_axis: str = 'Y'       # Urho3D default: Y up

    # Geometry
    export_position: bool = True
    export_normal: bool = True
    export_uv: bool = True
    export_uv2: bool = False
    export_tangent: bool = True
    export_color: bool = False

    # Skeleton
    export_skeleton: bool = False
    only_deform_bones: bool = False
    only_visible_bones: bool = False

    # Animation
    export_animations: bool = False
    animation_source: str = 'USED_ACTIONS'
    export_anim_position: bool = True
    export_anim_rotation: bool = True
    export_anim_scale: bool = False

    # Morphs
    export_morphs: bool = False
    export_morph_normals: bool = True
    export_morph_tangents: bool = False

    # Materials
    export_materials: bool = True
    copy_textures: bool = False
    prefer_pbr: bool = True
    pack_pbr_textures: bool = True

    # Optimization
    optimize_indices: bool = True

    # Scene
    export_prefabs: bool = False
    export_scene: bool = False
    cast_shadows: bool = False

    # Files
    overwrite: bool = True
    use_subdirs: bool = True

    # Paths
    paths: PathConfig = field(default_factory=PathConfig)
