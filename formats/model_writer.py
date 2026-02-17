"""Write Urho3D .mdl (UMDL) binary model files."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Set, Tuple

from ..core.logging import ExportLogger
from ..data.urho_model import (
    ELEMENT_BINDICES,
    ELEMENT_BWEIGHTS,
    ELEMENT_COLOR,
    ELEMENT_NORMAL,
    ELEMENT_POSITION,
    ELEMENT_TANGENT,
    ELEMENT_UV1,
    ELEMENT_UV2,
    MAX_SKIN_MATRICES,
    MODEL_MAGIC,
    MORPH_ELEMENTS,
    PRIMITIVE_TRIANGLE_LIST,
    compute_element_mask,
)
from .binary_writer import binary_file

if TYPE_CHECKING:
    from ..data.intermediate import IntermediateModel, IntermediateGeometry


def write_model(model: IntermediateModel, filepath: str, log: ExportLogger) -> bool:
    """
    Write an IntermediateModel to Urho3D .mdl binary format.

    Format: UMDL header, vertex buffers, index buffers, geometries,
    morphs, bones, bounding box, geometry centers.
    """
    if not model.vertices or not model.geometries:
        log.error(f"Model '{model.name}' has no data to write")
        return False

    # Determine what elements are present
    v0 = model.vertices[0]
    has_normal = v0.normal is not None
    has_uv1 = v0.uv is not None
    has_uv2 = v0.uv2 is not None
    has_color = v0.color is not None
    has_tangent = v0.tangent is not None
    has_weights = v0.bone_weights is not None

    element_mask = compute_element_mask(
        has_position=True,
        has_normal=has_normal,
        has_color=has_color,
        has_uv1=has_uv1,
        has_uv2=has_uv2,
        has_tangent=has_tangent,
        has_weights=has_weights,
    )

    # Compute bone bounding info (needed for AnimatedModel frustum culling)
    if model.bones:
        _compute_bone_bounds(model, log)

    # Build per-geometry bone remapping if needed
    bone_maps = _build_bone_maps(model, log) if model.bones else {}

    # Build flat index buffers with per-geometry LOD ranges
    all_indices: List[int] = []
    # geom_lod_ranges[gi][li] = (start, count)
    geom_lod_ranges: List[List[Tuple[int, int]]] = []
    for geom in model.geometries:
        lod_ranges = []
        for lod in geom.lod_levels:
            start = len(all_indices)
            for tri in lod.triangles:
                all_indices.extend(tri)
            lod_ranges.append((start, len(all_indices) - start))
        geom_lod_ranges.append(lod_ranges)

    # Determine index size
    vertex_count = len(model.vertices)
    use_32bit = vertex_count > 65535
    index_size = 4 if use_32bit else 2

    # Compute morph range
    morph_start = 0
    morph_count = 0
    if model.morphs:
        affected = set()
        for morph in model.morphs:
            for mv in morph.vertices:
                affected.add(mv.vertex_index)
        if affected:
            morph_start = min(affected)
            morph_count = max(affected) - morph_start + 1

    try:
        with binary_file(filepath) as w:
            # Magic
            w.write_ascii(MODEL_MAGIC)

            # --- Vertex Buffers (1 buffer) ---
            w.write_uint(1)

            w.write_uint(vertex_count)
            w.write_uint(element_mask)
            w.write_uint(morph_start)
            w.write_uint(morph_count)

            for v in model.vertices:
                w.write_vector3(v.position)

                if has_normal:
                    w.write_vector3(v.normal)

                if has_color:
                    c = v.color or (255, 255, 255, 255)
                    w.write_color_ubyte4(c[0], c[1], c[2], c[3])

                if has_uv1:
                    w.write_vector2(v.uv or (0.0, 0.0))

                if has_uv2:
                    w.write_vector2(v.uv2 or (0.0, 0.0))

                if has_tangent:
                    t = v.tangent or (0.0, 0.0, 0.0, 1.0)
                    w.write_float(t[0])
                    w.write_float(t[1])
                    w.write_float(t[2])
                    w.write_float(t[3])

                if has_weights:
                    bw = v.bone_weights or (0.0, 0.0, 0.0, 0.0)
                    for i in range(4):
                        w.write_float(bw[i] if i < len(bw) else 0.0)
                    bi = v.bone_indices or (0, 0, 0, 0)
                    for i in range(4):
                        # If bone remapping is active, remap the bone indices
                        bone_idx = bi[i] if i < len(bi) else 0
                        w.write_ubyte(bone_idx)

            # --- Index Buffers (1 buffer) ---
            w.write_uint(1)
            w.write_uint(len(all_indices))
            w.write_uint(index_size)

            for idx in all_indices:
                if use_32bit:
                    w.write_uint(idx)
                else:
                    w.write_ushort(idx)

            # --- Geometries ---
            w.write_uint(len(model.geometries))

            for gi, geom in enumerate(model.geometries):
                # Bone mapping for this geometry
                if gi in bone_maps:
                    bmap = bone_maps[gi]
                    w.write_uint(len(bmap))
                    for bone_idx in bmap:
                        w.write_uint(bone_idx)
                else:
                    w.write_uint(0)

                # LOD levels
                w.write_uint(len(geom.lod_levels))

                for li, lod in enumerate(geom.lod_levels):
                    start, count = geom_lod_ranges[gi][li]
                    w.write_float(lod.distance)
                    w.write_uint(PRIMITIVE_TRIANGLE_LIST)
                    w.write_uint(0)  # vertex buffer index
                    w.write_uint(0)  # index buffer index
                    w.write_uint(start)
                    w.write_uint(count)

            # --- Morphs ---
            w.write_uint(len(model.morphs))

            for morph in model.morphs:
                w.write_cstring(morph.name)
                w.write_uint(1)  # affected buffers (always 1 - our single VB)

                # Buffer index
                w.write_uint(0)

                # Morph element mask
                morph_mask = ELEMENT_POSITION
                has_morph_normals = any(
                    mv.normal_delta is not None for mv in morph.vertices)
                has_morph_tangents = any(
                    mv.tangent_delta is not None for mv in morph.vertices)
                if has_morph_normals:
                    morph_mask |= ELEMENT_NORMAL
                if has_morph_tangents:
                    morph_mask |= ELEMENT_TANGENT
                w.write_uint(morph_mask)

                # Vertex count
                w.write_uint(len(morph.vertices))

                for mv in morph.vertices:
                    w.write_uint(mv.vertex_index)

                    # Position delta
                    w.write_vector3(mv.position_delta)

                    # Normal delta
                    if morph_mask & ELEMENT_NORMAL:
                        nd = mv.normal_delta or (0.0, 0.0, 0.0)
                        w.write_vector3(nd)

                    # Tangent delta (xyz only, no w)
                    if morph_mask & ELEMENT_TANGENT:
                        td = mv.tangent_delta or (0.0, 0.0, 0.0)
                        w.write_vector3(td)

            # --- Bones ---
            w.write_uint(len(model.bones))
            for bone in model.bones:
                w.write_cstring(bone.name)
                w.write_uint(bone.parent_index)
                w.write_vector3(bone.bind_position)
                w.write_quaternion(*bone.bind_rotation)
                w.write_vector3(bone.bind_scale)

                if bone.inverse_bind_matrix:
                    w.write_matrix3x4(bone.inverse_bind_matrix)
                else:
                    for row in range(3):
                        for col in range(4):
                            w.write_float(1.0 if row == col else 0.0)

                w.write_ubyte(bone.collision_mask)
                if bone.collision_mask & 0x01:
                    w.write_float(bone.bounding_sphere_radius)
                if bone.collision_mask & 0x02:
                    w.write_vector3(bone.bounding_box_min or (0, 0, 0))
                    w.write_vector3(bone.bounding_box_max or (0, 0, 0))

            # --- Bounding Box ---
            w.write_vector3(model.bbox_min)
            w.write_vector3(model.bbox_max)

            # --- Geometry Centers ---
            for geom in model.geometries:
                center = _compute_geometry_center(model, geom)
                w.write_vector3(center)

    except Exception as e:
        log.error(f"Failed to write model '{filepath}': {e}")
        return False

    log.info(f"Written model: {filepath} "
             f"({vertex_count} verts, {len(model.bones)} bones, "
             f"{len(model.morphs)} morphs)")
    return True


def _build_bone_maps(
    model: IntermediateModel,
    log: ExportLogger,
) -> Dict[int, List[int]]:
    """
    Build per-geometry bone remapping when bone count exceeds MAX_SKIN_MATRICES.

    Returns: dict of geometry_index -> list of global bone indices used by that geometry.
    Empty dict if no remapping needed (bone count <= MAX_SKIN_MATRICES).
    """
    if len(model.bones) <= MAX_SKIN_MATRICES:
        # No remapping needed, but still provide bone maps for skinned models
        bone_list = list(range(len(model.bones)))
        return {gi: bone_list for gi in range(len(model.geometries))}

    log.warning(f"Model '{model.name}' has {len(model.bones)} bones, "
                f"exceeding limit of {MAX_SKIN_MATRICES}. Remapping per geometry.")

    result: Dict[int, List[int]] = {}

    for gi, geom in enumerate(model.geometries):
        # Collect all bone indices used by this geometry's vertices
        used_bones: Set[int] = set()
        for lod in geom.lod_levels:
            for tri in lod.triangles:
                for vi in tri:
                    v = model.vertices[vi]
                    if v.bone_indices:
                        if v.bone_weights:
                            for bi, bw in zip(v.bone_indices, v.bone_weights):
                                if bw > 0.0001:
                                    used_bones.add(bi)
                        else:
                            for bi in v.bone_indices:
                                used_bones.add(bi)

        bone_list = sorted(used_bones)

        if len(bone_list) > MAX_SKIN_MATRICES:
            log.warning(f"Geometry {gi} of '{model.name}' uses {len(bone_list)} bones, "
                        f"truncating to {MAX_SKIN_MATRICES}")
            bone_list = bone_list[:MAX_SKIN_MATRICES]

        # Remap vertex bone indices for this geometry
        remap = {global_idx: local_idx for local_idx, global_idx in enumerate(bone_list)}

        for lod in geom.lod_levels:
            for tri in lod.triangles:
                for vi in tri:
                    v = model.vertices[vi]
                    if v.bone_indices:
                        new_indices = tuple(
                            remap.get(bi, 0) for bi in v.bone_indices
                        )
                        v.bone_indices = new_indices

        result[gi] = bone_list

    return result


def _compute_bone_bounds(model: IntermediateModel, log: ExportLogger) -> None:
    """
    Compute bounding sphere and bounding box for each bone.

    For each bone, find all vertices weighted to it, transform vertex
    positions into bone-local space using the inverse bind matrix,
    then compute AABB and bounding sphere radius.

    Sets collision_mask=3 (sphere+box) on every bone that has vertices.
    """
    if not model.bones:
        return

    import math

    num_bones = len(model.bones)

    # Per-bone vertex lists in bone-local space
    bone_verts: list = [[] for _ in range(num_bones)]

    for v in model.vertices:
        if not v.bone_weights or not v.bone_indices:
            continue
        px, py, pz = v.position
        for bi_idx, bw in zip(v.bone_indices, v.bone_weights):
            if bw < 0.001 or bi_idx >= num_bones:
                continue
            bone = model.bones[bi_idx]
            ibm = bone.inverse_bind_matrix
            if not ibm:
                continue
            # Transform vertex position by inverse bind matrix (3x4 row-major)
            lx = ibm[0][0] * px + ibm[0][1] * py + ibm[0][2] * pz + ibm[0][3]
            ly = ibm[1][0] * px + ibm[1][1] * py + ibm[1][2] * pz + ibm[1][3]
            lz = ibm[2][0] * px + ibm[2][1] * py + ibm[2][2] * pz + ibm[2][3]
            bone_verts[bi_idx].append((lx, ly, lz))

    for bi, bone in enumerate(model.bones):
        verts = bone_verts[bi]
        if not verts:
            # No vertices for this bone — use a small default bounding
            bone.collision_mask = 3
            bone.bounding_sphere_radius = 0.1
            bone.bounding_box_min = (-0.1, -0.1, -0.1)
            bone.bounding_box_max = (0.1, 0.1, 0.1)
            continue

        min_x = min(v[0] for v in verts)
        min_y = min(v[1] for v in verts)
        min_z = min(v[2] for v in verts)
        max_x = max(v[0] for v in verts)
        max_y = max(v[1] for v in verts)
        max_z = max(v[2] for v in verts)

        # Bounding sphere radius = max distance from origin in bone-local space
        radius = 0.0
        for lx, ly, lz in verts:
            d = math.sqrt(lx * lx + ly * ly + lz * lz)
            if d > radius:
                radius = d

        bone.collision_mask = 3  # SPHERE | BOX
        bone.bounding_sphere_radius = radius
        bone.bounding_box_min = (min_x, min_y, min_z)
        bone.bounding_box_max = (max_x, max_y, max_z)

    log.info(f"Computed bone bounding data for {num_bones} bones")


def _compute_geometry_center(model: IntermediateModel, geom) -> tuple:
    """Compute the average position of all vertices in a geometry."""
    sx, sy, sz = 0.0, 0.0, 0.0
    count = 0
    seen = set()

    for lod in geom.lod_levels:
        for tri in lod.triangles:
            for idx in tri:
                if idx not in seen:
                    seen.add(idx)
                    v = model.vertices[idx]
                    sx += v.position[0]
                    sy += v.position[1]
                    sz += v.position[2]
                    count += 1

    if count == 0:
        return (0.0, 0.0, 0.0)
    return (sx / count, sy / count, sz / count)
