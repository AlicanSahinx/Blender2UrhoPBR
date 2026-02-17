"""Urho3D material output data structures."""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class UrhoMaterialResult:
    """The result of mapping a Blender material to Urho3D material."""

    technique_name: str = "Techniques/NoTexture.xml"

    # Texture unit assignments: {"diffuse": "image_name.png", "normal": ...}
    textures: Dict[str, str] = field(default_factory=dict)

    # Material parameters
    mat_diff_color: Optional[Tuple[float, float, float, float]] = None   # RGBA
    mat_spec_color: Optional[Tuple[float, float, float, float]] = None   # RGB + power
    mat_emissive_color: Optional[Tuple[float, float, float]] = None      # RGB
    metallic: Optional[float] = None
    roughness: Optional[float] = None

    # Shader defines
    vs_defines: str = ""
    ps_defines: str = ""

    # Cull mode
    cull_mode: str = "ccw"      # "ccw" (default backface cull), "cw", "none"
    shadow_cull: str = "ccw"
