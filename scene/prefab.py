"""Prefab and scene XML generation for Urho3D."""

from __future__ import annotations

from typing import List

from ..data.urho_scene import UrhoSceneNode


def build_prefab_xml(node: UrhoSceneNode) -> dict:
    """
    Build a dictionary representation of a prefab node for XML generation.
    Used by scene_writer.py.
    """
    return {
        "name": node.name,
        "position": node.position,
        "rotation": node.rotation,
        "scale": node.scale,
        "model_path": node.model_path,
        "material_paths": node.material_paths,
        "is_animated": node.is_animated,
        "cast_shadows": node.cast_shadows,
        "children": [build_prefab_xml(child) for child in node.children],
    }
