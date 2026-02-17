"""Principled BSDF node tree analyzer for Blender 4.x materials."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    import bpy


@dataclass
class TextureInfo:
    """Resolved texture information from a shader node."""
    image_name: str = ""
    filepath: str = ""
    uv_map_name: str = ""


@dataclass
class PBRProperties:
    """Extracted PBR properties from a Principled BSDF node."""

    # Colors
    base_color: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    base_color_alpha: float = 1.0
    metallic: float = 0.0
    roughness: float = 0.5
    specular_ior_level: float = 0.5
    emission_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    emission_strength: float = 1.0
    alpha: float = 1.0

    # Textures
    base_color_texture: Optional[TextureInfo] = None
    metallic_texture: Optional[TextureInfo] = None
    roughness_texture: Optional[TextureInfo] = None
    normal_texture: Optional[TextureInfo] = None
    emission_texture: Optional[TextureInfo] = None
    ao_texture: Optional[TextureInfo] = None

    # Flags
    has_transparency: bool = False
    uses_alpha_clip: bool = False
    is_two_sided: bool = False
    is_unlit: bool = False


class PrincipledBSDFAnalyzer:
    """
    Walks a Blender material's node tree to extract PBR properties.
    Directly traverses the node graph instead of using PrincipledBSDFWrapper
    for maximum control over node chain following.
    """

    def analyze(self, material) -> Optional[PBRProperties]:
        """Analyze a Blender material and extract PBR properties."""
        if not material or not material.use_nodes or not material.node_tree:
            return self._analyze_simple_material(material)

        bsdf = self._find_principled_bsdf(material.node_tree)
        if bsdf is None:
            return None

        props = PBRProperties()

        self._extract_base_color(bsdf, props)
        self._extract_metallic(bsdf, props)
        self._extract_roughness(bsdf, props)
        self._extract_normal(bsdf, props)
        self._extract_emission(bsdf, props)
        self._extract_alpha(bsdf, material, props)
        self._detect_ao_texture(material.node_tree, props)

        # Two-sided: only enable when user explicitly turned on backface culling
        # then turned it off — Blender 5.0 defaults use_backface_culling=False,
        # but for game export we default to single-sided (Urho3D convention).
        # Detect deliberate two-sided: check if Thin Film or Transmission is used,
        # which typically implies see-through geometry (leaves, glass, etc.)
        transmission = self._get_input(bsdf, 'Transmission Weight', 'Transmission')
        has_transmission = (transmission is not None
                           and (transmission.is_linked
                                or transmission.default_value > 0.01))
        if has_transmission:
            props.is_two_sided = True

        # Unlit detection: emission-only, no diffuse contribution
        if (props.base_color_texture is None
                and all(c < 0.01 for c in props.base_color)
                and props.emission_strength > 0
                and any(c > 0 for c in props.emission_color)):
            props.is_unlit = True

        return props

    def _analyze_simple_material(self, material) -> Optional[PBRProperties]:
        """Fallback for materials without node trees."""
        if material is None:
            return None
        props = PBRProperties()
        c = material.diffuse_color
        props.base_color = (c[0], c[1], c[2])
        props.alpha = c[3] if len(c) > 3 else 1.0
        props.metallic = material.metallic
        props.roughness = material.roughness
        return props

    def _find_principled_bsdf(self, node_tree):
        """Find the first Principled BSDF node in the tree."""
        for node in node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return node
        return None

    def _get_input(self, node, *names):
        """Get a node input by trying multiple names (handles Blender 4.0 renames)."""
        for name in names:
            inp = node.inputs.get(name)
            if inp is not None:
                return inp
        return None

    def _get_connected_texture(self, socket) -> Optional[TextureInfo]:
        """Follow links from a socket to find a connected Image Texture node."""
        if socket is None or not socket.is_linked:
            return None

        link = socket.links[0]
        node = link.from_node

        # Direct Image Texture connection
        if node.type == 'TEX_IMAGE' and node.image:
            return self._texture_info_from_node(node)

        # Normal Map node -> follow its Color input
        if node.type == 'NORMAL_MAP':
            color_input = node.inputs.get('Color')
            if color_input:
                return self._get_connected_texture(color_input)

        # Separate RGB/XYZ, Math, MixRGB -> follow through inputs
        if node.type in ('SEPRGB', 'SEPXYZ', 'MATH', 'MIX_RGB', 'MIX',
                         'VALTORGB', 'INVERT', 'GAMMA', 'CURVE_RGB'):
            for inp in node.inputs:
                result = self._get_connected_texture(inp)
                if result:
                    return result

        return None

    def _texture_info_from_node(self, node) -> TextureInfo:
        """Extract TextureInfo from an Image Texture node."""
        # Ensure image_name has a file extension
        name = node.image.name
        if not os.path.splitext(name)[1]:
            # Get extension from filepath, default to .png
            fp = node.image.filepath or ""
            ext = os.path.splitext(fp)[1] if fp else ".png"
            name = name + (ext or ".png")
        info = TextureInfo(
            image_name=name,
            filepath=node.image.filepath or "",
        )
        # Check for UV map specification
        vector_input = node.inputs.get('Vector')
        if vector_input and vector_input.is_linked:
            uv_node = vector_input.links[0].from_node
            if uv_node.type == 'UVMAP':
                info.uv_map_name = uv_node.uv_map
        return info

    def _extract_base_color(self, bsdf, props: PBRProperties) -> None:
        socket = self._get_input(bsdf, 'Base Color')
        if socket is None:
            return

        props.base_color_texture = self._get_connected_texture(socket)

        if not socket.is_linked:
            val = socket.default_value
            props.base_color = (val[0], val[1], val[2])
            props.base_color_alpha = val[3] if len(val) > 3 else 1.0

    def _extract_metallic(self, bsdf, props: PBRProperties) -> None:
        socket = self._get_input(bsdf, 'Metallic')
        if socket is None:
            return

        props.metallic_texture = self._get_connected_texture(socket)

        if not socket.is_linked:
            props.metallic = socket.default_value

    def _extract_roughness(self, bsdf, props: PBRProperties) -> None:
        socket = self._get_input(bsdf, 'Roughness')
        if socket is None:
            return

        props.roughness_texture = self._get_connected_texture(socket)

        if not socket.is_linked:
            props.roughness = socket.default_value

    def _extract_normal(self, bsdf, props: PBRProperties) -> None:
        socket = self._get_input(bsdf, 'Normal')
        if socket is None:
            return
        props.normal_texture = self._get_connected_texture(socket)

    def _extract_emission(self, bsdf, props: PBRProperties) -> None:
        # Blender 4.0: "Emission Color" (was "Emission" in older versions)
        color_socket = self._get_input(bsdf, 'Emission Color', 'Emission')
        if color_socket is not None:
            props.emission_texture = self._get_connected_texture(color_socket)
            if not color_socket.is_linked:
                val = color_socket.default_value
                props.emission_color = (val[0], val[1], val[2])

        strength_socket = self._get_input(bsdf, 'Emission Strength')
        if strength_socket is not None and not strength_socket.is_linked:
            props.emission_strength = strength_socket.default_value

    def _extract_alpha(self, bsdf, material, props: PBRProperties) -> None:
        socket = self._get_input(bsdf, 'Alpha')
        alpha_is_linked = socket is not None and socket.is_linked
        if socket is not None and not alpha_is_linked:
            props.alpha = socket.default_value

        # Determine if material actually uses transparency.
        # Blender 5.0 defaults: surface_render_method='DITHERED', blend_method='HASHED'
        # These do NOT mean the material is transparent — only mark transparent if
        # alpha < 1.0 or alpha socket has a connected texture.
        if alpha_is_linked:
            props.has_transparency = True
        elif props.alpha < 1.0:
            props.has_transparency = True

        # Check for explicit alpha clip blend mode (user deliberately set it)
        blend = getattr(material, 'blend_method', 'OPAQUE')
        if blend in ('ALPHA_CLIP',):
            props.has_transparency = True
            props.uses_alpha_clip = True

    def _detect_ao_texture(self, node_tree, props: PBRProperties) -> None:
        """
        Detect AO texture by looking for image textures connected via
        Multiply MixRGB nodes or with 'ao' / 'ambient_occlusion' in the name.
        """
        for node in node_tree.nodes:
            if node.type != 'TEX_IMAGE' or not node.image:
                continue
            name_lower = node.image.name.lower()
            if 'ao' in name_lower or 'ambient_occlusion' in name_lower or 'ambientlight' in name_lower:
                props.ao_texture = TextureInfo(
                    image_name=node.image.name,
                    filepath=node.image.filepath or "",
                )
                break
