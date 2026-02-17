"""Map Blender PBR properties to Urho3D techniques and material parameters."""

from __future__ import annotations

from ..data.urho_material import UrhoMaterialResult
from .analyzer import PBRProperties


class TechniqueMapper:
    """
    Maps PBRProperties to Urho3D technique names and material parameters.

    Urho3D PBR technique naming (from CoreData/Techniques/PBR/):

      Without metallic/roughness texture maps:
        PBRNoTexture, PBRDiff, PBRNormal, PBRDiffNormal
        + AO, Emissive, Alpha suffixes

      With metallic/roughness texture maps (specular slot):
        PBRMetallicRoughSpec, PBRMetallicRoughDiffSpec,
        PBRMetallicRoughNormalSpec, PBRMetallicRoughDiffNormalSpec
        + AO, Emissive, Alpha suffixes

    Legacy technique naming (from CoreData/Techniques/):
        NoTexture, Diff, DiffNormal, DiffNormalSpec, DiffAlpha, etc.

    Urho3D PBR specular slot convention:
        R = Roughness, G = Metallic, B = unused.
        Separate roughness/metallic textures MUST be packed into a single
        image before using the Spec variant (pack_textures=True).
    """

    def __init__(self, prefer_pbr: bool = True, pack_textures: bool = True):
        self.prefer_pbr = prefer_pbr
        self.pack_textures = pack_textures

    def map_material(self, props: PBRProperties) -> UrhoMaterialResult:
        """Map PBR properties to Urho3D material result."""
        result = UrhoMaterialResult()

        has_diffuse_tex = props.base_color_texture is not None
        has_normal_tex = props.normal_texture is not None
        has_metallic_tex = props.metallic_texture is not None
        has_roughness_tex = props.roughness_texture is not None
        # Only use Spec variant when textures will be packed properly.
        # Raw grayscale roughness in specular slot is wrong — Urho3D PBR
        # reads R=Roughness, G=Metallic from the specular texture.
        has_spec_tex = (has_metallic_tex or has_roughness_tex) and self.pack_textures
        has_emission_tex = props.emission_texture is not None
        has_ao_tex = props.ao_texture is not None
        has_alpha = props.has_transparency

        # Decide PBR vs legacy
        # When prefer_pbr is on, ALL Principled BSDF materials use PBR path
        # (even metallic=0 materials like plastic, rubber, etc.)
        is_pbr = self.prefer_pbr and not props.is_unlit

        if is_pbr:
            self._map_pbr(props, result,
                          has_diffuse_tex, has_normal_tex, has_spec_tex,
                          has_ao_tex, has_emission_tex, has_alpha)
        else:
            self._map_legacy(props, result,
                             has_diffuse_tex, has_normal_tex, has_emission_tex,
                             has_spec_tex, has_alpha)

        # Two-sided
        if props.is_two_sided:
            result.cull_mode = "none"
            result.shadow_cull = "none"

        # Alpha mask
        if props.uses_alpha_clip:
            result.ps_defines = _append_define(result.ps_defines, "ALPHAMASK")

        # Finalize technique path
        if not result.technique_name.startswith("Techniques/"):
            result.technique_name = f"Techniques/{result.technique_name}.xml"

        return result

    def _map_pbr(self, props: PBRProperties, result: UrhoMaterialResult,
                 has_diff: bool, has_norm: bool, has_spec: bool,
                 has_ao: bool, has_emissive: bool, has_alpha: bool) -> None:
        """
        Build PBR technique name matching Urho3D CoreData conventions.

        With specular (metallic/roughness) textures:
          PBR/PBRMetallicRough[Diff][Normal]Spec[AO][Emissive][Alpha]

        Without specular textures:
          PBR/PBR{NoTexture|Diff|Normal|DiffNormal}[AO][Emissive][Alpha]
        """
        if has_spec:
            # MetallicRough variant: always ends with "Spec"
            tech = "PBR/PBRMetallicRough"
            if has_diff:
                tech += "Diff"
                result.textures["diffuse"] = props.base_color_texture.image_name
            if has_norm:
                tech += "Normal"
                result.textures["normal"] = props.normal_texture.image_name
            tech += "Spec"
            if props.metallic_texture:
                result.textures["specular"] = props.metallic_texture.image_name
            elif props.roughness_texture:
                result.textures["specular"] = props.roughness_texture.image_name
        else:
            # Non-texture or Diff/Normal only PBR
            if not has_diff and not has_norm:
                tech = "PBR/PBRNoTexture"
            else:
                tech = "PBR/PBR"
                if has_diff:
                    tech += "Diff"
                    result.textures["diffuse"] = props.base_color_texture.image_name
                if has_norm:
                    tech += "Normal"
                    result.textures["normal"] = props.normal_texture.image_name

        # Suffixes
        if has_ao:
            tech += "AO"
            result.textures["emissive"] = props.ao_texture.image_name

        if has_emissive:
            tech += "Emissive"
            if props.emission_texture:
                result.textures["emissive"] = props.emission_texture.image_name

        if has_alpha:
            tech += "Alpha"

        result.technique_name = tech

        # PBR parameters (match Urho3D HoverBike material structure)
        bc = props.base_color
        result.mat_diff_color = (bc[0], bc[1], bc[2], props.alpha)
        result.mat_spec_color = (1.0, 1.0, 1.0, 1.0)

        # Urho3D PBR shader: roughness = texture.r + cRoughness (ADDITIVE!)
        # When specular texture exists, params must be 0 so texture values are used directly
        if has_spec:
            result.metallic = 0.0
            result.roughness = 0.0
        else:
            result.metallic = props.metallic
            result.roughness = props.roughness

        # Emission
        if any(c > 0.0 for c in props.emission_color) and props.emission_strength > 0.0:
            ec = props.emission_color
            s = props.emission_strength
            result.mat_emissive_color = (ec[0] * s, ec[1] * s, ec[2] * s)

    def _map_legacy(self, props: PBRProperties, result: UrhoMaterialResult,
                    has_diff: bool, has_norm: bool, has_emission: bool,
                    has_spec: bool, has_alpha: bool) -> None:
        """Build legacy (non-PBR) technique name."""
        if not has_diff:
            tech = "NoTexture"
        else:
            tech = "Diff"
            result.textures["diffuse"] = props.base_color_texture.image_name

            if has_norm:
                tech += "Normal"
                result.textures["normal"] = props.normal_texture.image_name

            if has_spec:
                tech += "Spec"
                if props.metallic_texture:
                    result.textures["specular"] = props.metallic_texture.image_name
                elif props.roughness_texture:
                    result.textures["specular"] = props.roughness_texture.image_name

        if has_emission:
            tech += "Emissive"
            result.textures["emissive"] = props.emission_texture.image_name

        if props.is_unlit:
            tech += "Unlit"

        if has_alpha:
            tech += "Alpha"

        result.technique_name = tech

        # Legacy parameters
        bc = props.base_color
        result.mat_diff_color = (bc[0], bc[1], bc[2], props.alpha)

        # Legacy specular: invert roughness as "power"
        spec = props.specular_ior_level
        power = max(1.0, ((1.0 - props.roughness) * 30.0) ** 2.0)
        result.mat_spec_color = (spec, spec, spec, power)

        # Emission
        if any(c > 0.0 for c in props.emission_color):
            ec = props.emission_color
            s = props.emission_strength
            result.mat_emissive_color = (ec[0] * s, ec[1] * s, ec[2] * s)


def _append_define(existing: str, new_define: str) -> str:
    if existing:
        return f"{existing} {new_define}"
    return new_define
