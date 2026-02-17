"""Write Urho3D material XML files."""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement

from ..core.logging import ExportLogger
from ..data.urho_material import UrhoMaterialResult
from .xml_utils import write_xml_file


def write_material(
    material: UrhoMaterialResult,
    filepath: str,
    textures_subdir: str,
    log: ExportLogger,
) -> bool:
    """
    Write an UrhoMaterialResult to an Urho3D material XML file.

    Output format:
    <material>
        <technique name="Techniques/..." />
        <texture unit="diffuse" name="Textures/..." />
        <parameter name="MatDiffColor" value="r g b a" />
        ...
    </material>
    """
    try:
        root = Element("material")

        # Technique
        SubElement(root, "technique", name=material.technique_name)

        # Textures
        for unit, image_name in material.textures.items():
            tex_path = f"{textures_subdir}/{image_name}" if textures_subdir else image_name
            SubElement(root, "texture", unit=unit, name=tex_path)

        # Shader defines
        if material.vs_defines:
            SubElement(root, "shader", vsdefines=material.vs_defines)
        if material.ps_defines:
            SubElement(root, "shader", psdefines=material.ps_defines)

        # Parameters
        if material.mat_diff_color is not None:
            c = material.mat_diff_color
            SubElement(root, "parameter",
                       name="MatDiffColor",
                       value=f"{c[0]:g} {c[1]:g} {c[2]:g} {c[3]:g}")

        if material.mat_spec_color is not None:
            c = material.mat_spec_color
            SubElement(root, "parameter",
                       name="MatSpecColor",
                       value=f"{c[0]:g} {c[1]:g} {c[2]:g} {c[3]:g}")

        if material.mat_emissive_color is not None:
            c = material.mat_emissive_color
            SubElement(root, "parameter",
                       name="MatEmissiveColor",
                       value=f"{c[0]:g} {c[1]:g} {c[2]:g}")

        if material.metallic is not None:
            SubElement(root, "parameter",
                       name="Metallic",
                       value=f"{material.metallic:g}")

        if material.roughness is not None:
            SubElement(root, "parameter",
                       name="Roughness",
                       value=f"{material.roughness:g}")

        # PBR materials need MatEnvMapColor for IBL reflections
        if material.metallic is not None or material.roughness is not None:
            SubElement(root, "parameter",
                       name="MatEnvMapColor",
                       value="1 1 1")

        # Cull mode
        if material.cull_mode != "ccw":
            SubElement(root, "cull", value=material.cull_mode)
        if material.shadow_cull != "ccw":
            SubElement(root, "shadowcull", value=material.shadow_cull)

        write_xml_file(root, filepath)

    except Exception as e:
        log.error(f"Failed to write material '{filepath}': {e}")
        return False

    log.info(f"Written material: {filepath}")
    return True
