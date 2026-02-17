"""Texture path resolution, copy, and PBR channel packing utilities."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    import bpy

from ..core.logging import ExportLogger
from ..core.types import ExportSettings


def _get_image(name: str):
    """Look up a Blender image by name, trying with and without extension."""
    import bpy
    img = bpy.data.images.get(name)
    if img is None:
        # Blender often stores images without the file extension
        base = os.path.splitext(name)[0]
        img = bpy.data.images.get(base)
    return img


def resolve_texture_path(
    image_name: str,
    textures_dir: str,
    settings: ExportSettings,
) -> str:
    """
    Resolve an image name to a relative Urho3D resource path.
    Returns path like "Textures/albedo.png".
    """
    if settings.use_subdirs:
        return f"{settings.paths.textures}/{image_name}"
    return image_name


def copy_texture(
    image_name: str,
    textures_dir: str,
    log: ExportLogger,
) -> bool:
    """
    Copy a Blender image to the textures output directory.
    Handles packed images (saves them) and external images (copies them).
    """
    try:
        import bpy
    except ImportError:
        log.error("Cannot import bpy - not running inside Blender")
        return False

    image = _get_image(image_name)
    if image is None:
        log.warning(f"Image '{image_name}' not found in bpy.data.images")
        return False

    dest_path = os.path.join(textures_dir, image_name)

    # Ensure filename has an extension
    if not os.path.splitext(dest_path)[1]:
        dest_path += ".png"

    try:
        if image.packed_file:
            image.save(filepath=dest_path)
            log.info(f"Saved packed image: {dest_path}")
        else:
            src = bpy.path.abspath(image.filepath)
            if not src or not os.path.isfile(src):
                log.warning(f"Image source not found: {src}")
                return False
            if os.path.abspath(src) != os.path.abspath(dest_path):
                shutil.copy2(src, dest_path)
                log.info(f"Copied texture: {src} -> {dest_path}")
    except Exception as e:
        log.error(f"Failed to copy texture '{image_name}': {e}")
        return False

    return True


def copy_all_textures(
    textures: Dict[str, str],
    textures_dir: str,
    log: ExportLogger,
) -> None:
    """Copy all textures referenced by a material to the output directory."""
    os.makedirs(textures_dir, exist_ok=True)
    copied = set()
    for unit_name, image_name in textures.items():
        if image_name and image_name not in copied:
            copy_texture(image_name, textures_dir, log)
            copied.add(image_name)


def pack_metallic_roughness(
    metallic_image_name: Optional[str],
    roughness_image_name: Optional[str],
    output_name: str,
    textures_dir: str,
    log: ExportLogger,
) -> Optional[str]:
    """
    Pack separate metallic and roughness grayscale maps into a single RGB image.

    Urho3D PBR convention:
      R channel = Roughness
      G channel = Metallic
      B channel = 0 (unused)

    Returns the packed image filename, or None on failure.
    """
    try:
        import bpy
    except ImportError:
        log.error("Cannot import bpy")
        return None

    metallic_img = _get_image(metallic_image_name) if metallic_image_name else None
    roughness_img = _get_image(roughness_image_name) if roughness_image_name else None

    if metallic_img is None and roughness_img is None:
        return None

    # Determine output size from whichever image is available
    source_img = metallic_img or roughness_img
    width, height = source_img.size[0], source_img.size[1]

    if width == 0 or height == 0:
        log.warning("Source texture has zero dimensions")
        return None

    # Get pixel data as flat float arrays
    metallic_pixels = None
    if metallic_img:
        metallic_pixels = list(metallic_img.pixels[:])

    roughness_pixels = None
    if roughness_img:
        roughness_pixels = list(roughness_img.pixels[:])

    # Build packed image
    packed_name = output_name
    if packed_name in bpy.data.images:
        packed = bpy.data.images[packed_name]
        if packed.size[0] != width or packed.size[1] != height:
            bpy.data.images.remove(packed)
            packed = bpy.data.images.new(packed_name, width, height, alpha=False)
    else:
        packed = bpy.data.images.new(packed_name, width, height, alpha=False)

    pixel_count = width * height
    packed_pixels = [0.0] * (pixel_count * 4)  # RGBA

    for i in range(pixel_count):
        # Source images are RGBA (4 channels per pixel)
        # Take R channel as grayscale value
        roughness_val = 0.5
        metallic_val = 0.0

        if roughness_pixels:
            roughness_val = roughness_pixels[i * 4]  # R channel

        if metallic_pixels:
            metallic_val = metallic_pixels[i * 4]  # R channel

        offset = i * 4
        packed_pixels[offset + 0] = roughness_val  # R = Roughness
        packed_pixels[offset + 1] = metallic_val    # G = Metallic
        packed_pixels[offset + 2] = 0.0             # B = unused
        packed_pixels[offset + 3] = 1.0             # A = 1

    packed.pixels[:] = packed_pixels

    # Save to disk
    os.makedirs(textures_dir, exist_ok=True)
    output_path = os.path.join(textures_dir, packed_name)
    if not os.path.splitext(output_path)[1]:
        output_path += ".png"

    packed.filepath_raw = output_path
    packed.file_format = 'PNG'
    packed.save()

    log.info(f"Packed metallic+roughness -> {output_path}")
    return packed_name
