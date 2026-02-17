"""Armature/skeleton decomposition for Blender 4.x."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    import bpy

from ..core.logging import ExportLogger
from ..core.types import ExportSettings
from ..data.intermediate import IntermediateBone


def is_bone_visible(bone) -> bool:
    """Check bone visibility using Blender 4.x Bone Collections API."""
    # Blender 4.0+: bone.collections replaces armature.layers/bone.layers
    if not hasattr(bone, 'collections') or not bone.collections:
        return True
    return any(coll.is_visible for coll in bone.collections)


def decompose_armature(
    armature_obj,
    mesh_obj,
    settings: ExportSettings,
    log: ExportLogger,
) -> List[IntermediateBone]:
    """
    Decompose a Blender armature into a list of IntermediateBone.

    Coordinate conversion:
    - Root bones get a -90 deg X rotation (Blender Z-up -> Urho3D Y-up)
    - Child bones use relative parent-space transforms (no extra conversion)
    - Inverse bind matrix: swap rows 1&2, negate column 2
    """
    from mathutils import Matrix, Quaternion, Vector

    armature = armature_obj.data
    if not armature.bones:
        log.warning(f"Armature '{armature_obj.name}' has no bones")
        return []

    log.info(f"Decomposing armature: {armature_obj.name} ({len(armature.bones)} bones)")

    # Collect bones in armature.bones iteration order — this MUST match
    # the order used by _build_bone_weights() in decompose.py so that
    # vertex bone indices reference the correct bones.
    bone_pairs: List[Tuple] = []  # (bone, parent_bone_or_None)

    def _bone_passes_filter(bone) -> bool:
        if settings.only_visible_bones and not is_bone_visible(bone):
            return False
        if settings.only_deform_bones and not bone.use_deform:
            return False
        return True

    def _has_exportable_descendant(bone) -> bool:
        for child in bone.children_recursive:
            if _bone_passes_filter(child):
                return True
        return False

    for bone in armature.bones:
        if _bone_passes_filter(bone) or _has_exportable_descendant(bone):
            bone_pairs.append((bone, bone.parent))

    if not bone_pairs:
        log.warning(f"Armature '{armature_obj.name}' has no exportable bones")
        return []

    # Build name-to-index map
    name_to_index: Dict[str, int] = {}
    for i, (bone, _) in enumerate(bone_pairs):
        name_to_index[bone.name] = i

    # Convert bones
    result: List[IntermediateBone] = []
    rot_minus90_x = Matrix.Rotation(math.radians(-90.0), 4, 'X')

    for i, (bone, parent) in enumerate(bone_pairs):
        # Compute bone matrix in parent space
        bone_matrix = bone.matrix_local.copy()

        if parent:
            bone_matrix = parent.matrix_local.inverted() @ bone_matrix
        else:
            # Root bone: apply -90 X rotation for Z-up to Y-up
            bone_matrix = rot_minus90_x @ bone_matrix

        if settings.scale != 1.0:
            bone_matrix.translation *= settings.scale

        # Extract local transform
        t = bone_matrix.to_translation()
        q = bone_matrix.to_quaternion()
        s = bone_matrix.to_scale()

        # Convert to left-hand coordinates
        pos = (t.x, t.y, -t.z)
        rot = (q.w, -q.x, -q.y, q.z)  # wxyz
        scl = (s.x, s.y, s.z)

        # Compute inverse bind matrix
        # Take matrix_local (armature space), apply row/column swaps
        ml = bone.matrix_local.copy()
        if settings.scale != 1.0:
            ml.translation *= settings.scale

        # Swap row 1 and row 2
        ml[1][:], ml[2][:] = ml[2][:], ml[1][:]
        # Negate column 2
        ml[0][2] = -ml[0][2]
        ml[1][2] = -ml[1][2]
        ml[2][2] = -ml[2][2]

        # Invert for skinning
        inv = ml.inverted()
        # Extract 3x4 (top 3 rows, all 4 columns)
        inv_3x4 = [
            [inv[0][0], inv[0][1], inv[0][2], inv[0][3]],
            [inv[1][0], inv[1][1], inv[1][2], inv[1][3]],
            [inv[2][0], inv[2][1], inv[2][2], inv[2][3]],
        ]

        # Parent index
        parent_index = i  # root bones point to themselves
        if parent and parent.name in name_to_index:
            parent_index = name_to_index[parent.name]

        ib = IntermediateBone(
            name=bone.name,
            index=i,
            parent_index=parent_index,
            bind_position=pos,
            bind_rotation=rot,
            bind_scale=scl,
            inverse_bind_matrix=inv_3x4,
        )
        result.append(ib)

    log.info(f"Decomposed {len(result)} bones from armature '{armature_obj.name}'")
    return result
