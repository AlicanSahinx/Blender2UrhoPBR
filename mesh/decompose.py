"""Mesh decomposition: extract vertices, triangles, UVs, colors from Blender mesh."""

from __future__ import annotations

import math
from contextlib import contextmanager
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    import bpy

from ..core.logging import ExportLogger
from ..core.types import ExportSettings
from ..data.intermediate import (
    IntermediateGeometry,
    IntermediateLodLevel,
    IntermediateModel,
    IntermediateMorph,
    IntermediateMorphVertex,
    IntermediateVertex,
)

# Small epsilon for float comparisons
EPSILON = 1e-6


@contextmanager
def evaluated_mesh(obj, depsgraph, apply_modifiers: bool = False):
    """Context manager that yields a temporary evaluated mesh and cleans up."""
    eval_obj = obj.evaluated_get(depsgraph) if apply_modifiers else obj
    mesh = eval_obj.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        mesh.calc_loop_triangles()
        yield mesh, eval_obj
    finally:
        eval_obj.to_mesh_clear()


def _blender_to_urho_pos(co, scale: float) -> Tuple[float, float, float]:
    """Convert Blender position (X-right, Y-forward, Z-up) to Urho3D (X-right, Y-up, Z-forward)."""
    return (co[0] * scale, co[2] * scale, co[1] * scale)


def _blender_to_urho_normal(n) -> Tuple[float, float, float]:
    """Convert Blender normal to Urho3D coordinate system."""
    return (n[0], n[2], n[1])


def _blender_to_urho_uv(uv) -> Tuple[float, float]:
    """Convert Blender UV (origin bottom-left) to Urho3D (origin top-left)."""
    return (uv[0], 1.0 - uv[1])


def _color_to_ubyte4(color) -> Tuple[int, int, int, int]:
    """Convert float RGBA color [0..1] to uint8 RGBA [0..255]."""
    return (
        max(0, min(255, int(color[0] * 255.0 + 0.5))),
        max(0, min(255, int(color[1] * 255.0 + 0.5))),
        max(0, min(255, int(color[2] * 255.0 + 0.5))),
        max(0, min(255, int(color[3] * 255.0 + 0.5))) if len(color) > 3 else 255,
    )


def decompose_mesh(
    obj,
    depsgraph,
    settings: ExportSettings,
    log: ExportLogger,
) -> Optional[IntermediateModel]:
    """
    Decompose a Blender mesh object into an IntermediateModel.

    Steps:
    1. Get evaluated mesh with triangulated loops
    2. Build unique vertices from loop data (position, normal, UV, color)
    3. Group triangles by material slot (each slot = one geometry)
    4. Compute bounding box

    For skinned meshes (with armature), vertex positions are transformed
    from mesh-local space to armature space so they match bone coordinates.
    """
    if obj.type != 'MESH':
        log.warning(f"Object '{obj.name}' is not a mesh, skipping")
        return None

    model = IntermediateModel(name=obj.name)

    with evaluated_mesh(obj, depsgraph, settings.apply_modifiers) as (mesh, eval_obj):
        if not mesh.loop_triangles:
            log.warning(f"Mesh '{obj.name}' has no triangles, skipping")
            return None

        # Get UV layer
        uv_layer = None
        if settings.export_uv and mesh.uv_layers.active:
            uv_layer = mesh.uv_layers.active.data

        uv2_layer = None
        if settings.export_uv2 and len(mesh.uv_layers) > 1:
            uv2_layer = mesh.uv_layers[1].data

        # Get color attribute (Blender 4.x: color_attributes)
        color_attr = None
        color_domain = None
        if settings.export_color and mesh.color_attributes.active:
            color_attr = mesh.color_attributes.active
            color_domain = color_attr.domain  # 'POINT' or 'CORNER'

        # Build bone weight lookup if exporting skeleton
        bone_weights_lookup: Dict[int, Tuple[Tuple[float, ...], Tuple[int, ...]]] = {}
        # For skinned meshes, compute mesh-to-armature transform so vertex
        # positions are in armature space (matching bone coordinates).
        mesh_to_armature = None
        mesh_to_armature_rot = None  # 3x3 for normals
        if settings.export_skeleton:
            bone_weights_lookup = _build_bone_weights(obj, mesh, log)
            armature_obj = obj.find_armature()
            if armature_obj and bone_weights_lookup:
                mesh_to_armature = armature_obj.matrix_world.inverted() @ obj.matrix_world
                mesh_to_armature_rot = mesh_to_armature.to_3x3()

        # Vertex deduplication map: hash_key -> vertex index
        vertex_map: Dict[tuple, int] = {}

        # Per-material triangle lists
        geom_triangles: Dict[int, List[Tuple[int, int, int]]] = {}

        # Build vertices from loop triangles
        for tri in mesh.loop_triangles:
            mat_idx = tri.material_index
            if mat_idx not in geom_triangles:
                geom_triangles[mat_idx] = []

            tri_indices = []
            for i in range(3):
                loop_idx = tri.loops[i]
                vert_idx = mesh.loops[loop_idx].vertex_index
                vertex = mesh.vertices[vert_idx]

                # Position — for skinned meshes, transform to armature space
                if mesh_to_armature is not None:
                    co_armature = mesh_to_armature @ vertex.co
                    pos = _blender_to_urho_pos(co_armature, settings.scale)
                else:
                    pos = _blender_to_urho_pos(vertex.co, settings.scale)

                # Normal (Blender 4.1+: corner_normals available without calc_normals_split)
                normal = None
                if settings.export_normal:
                    if hasattr(mesh, 'corner_normals') and len(mesh.corner_normals) > 0:
                        n = mesh.corner_normals[loop_idx].vector
                    else:
                        n = tri.split_normals[i]
                    # For skinned meshes, rotate normals to armature space
                    if mesh_to_armature_rot is not None:
                        n = mesh_to_armature_rot @ n
                    normal = _blender_to_urho_normal(n)

                # UV
                uv = None
                if uv_layer is not None:
                    uv = _blender_to_urho_uv(uv_layer[loop_idx].uv)

                uv2 = None
                if uv2_layer is not None:
                    uv2 = _blender_to_urho_uv(uv2_layer[loop_idx].uv)

                # Color
                color = None
                if color_attr is not None:
                    if color_domain == 'CORNER':
                        color = _color_to_ubyte4(color_attr.data[loop_idx].color)
                    elif color_domain == 'POINT':
                        color = _color_to_ubyte4(color_attr.data[vert_idx].color)

                # Bone weights
                bone_w = None
                bone_i = None
                if bone_weights_lookup and vert_idx in bone_weights_lookup:
                    bone_w, bone_i = bone_weights_lookup[vert_idx]

                # Build intermediate vertex
                iv = IntermediateVertex(
                    position=pos,
                    normal=normal,
                    uv=uv,
                    uv2=uv2,
                    color=color,
                    bone_weights=bone_w,
                    bone_indices=bone_i,
                    blender_index=vert_idx,
                )

                # Deduplicate
                key = iv.hash_key()
                if key in vertex_map:
                    idx = vertex_map[key]
                else:
                    idx = len(model.vertices)
                    vertex_map[key] = idx
                    model.vertices.append(iv)

                tri_indices.append(idx)

            # Flip winding order: Y↔Z swap reverses handedness,
            # so (a, b, c) → (a, c, b) to keep front faces correct.
            a, b, c = tri_indices
            geom_triangles[mat_idx].append((a, c, b))

        # Build geometries (one per material)
        mat_slots = obj.material_slots
        for mat_idx in sorted(geom_triangles.keys()):
            mat_name = ""
            if mat_idx < len(mat_slots) and mat_slots[mat_idx].material:
                mat_name = mat_slots[mat_idx].material.name

            lod = IntermediateLodLevel(
                distance=0.0,
                triangles=geom_triangles[mat_idx],
            )
            geom = IntermediateGeometry(
                material_name=mat_name,
                material_index=mat_idx,
                lod_levels=[lod],
            )
            model.geometries.append(geom)

        # Compute bounding box
        if model.vertices:
            xs = [v.position[0] for v in model.vertices]
            ys = [v.position[1] for v in model.vertices]
            zs = [v.position[2] for v in model.vertices]
            model.bbox_min = (min(xs), min(ys), min(zs))
            model.bbox_max = (max(xs), max(ys), max(zs))

        # Decompose morph targets (shape keys)
        if settings.export_morphs and obj.data.shape_keys:
            model.morphs = _decompose_morphs(
                obj, depsgraph, settings, model, vertex_map, log)

        log.info(f"Mesh '{obj.name}': {len(model.vertices)} vertices, "
                 f"{sum(len(g.lod_levels[0].triangles) for g in model.geometries)} triangles, "
                 f"{len(model.geometries)} geometries, "
                 f"{len(model.morphs)} morphs")

    return model


def _decompose_morphs(
    obj,
    depsgraph,
    settings: ExportSettings,
    base_model: IntermediateModel,
    vertex_map: Dict[tuple, int],
    log: ExportLogger,
) -> List[IntermediateMorph]:
    """
    Decompose shape keys into morph targets.

    Pipeline:
    1. Save all shape key values
    2. Zero all shape keys (back to basis)
    3. For each non-basis shape key:
       a. Set value to 1.0
       b. Evaluate mesh
       c. Compare with base mesh, compute deltas
       d. Reset value to 0.0
    4. Restore original shape key values
    """
    shape_keys = obj.data.shape_keys
    if not shape_keys or len(shape_keys.key_blocks) < 2:
        return []

    key_blocks = shape_keys.key_blocks
    basis = key_blocks[0]  # First key is always "Basis"

    # Save original values
    saved_values = [(kb.value, kb.mute) for kb in key_blocks]

    # Zero all keys
    for kb in key_blocks:
        kb.value = 0.0
        kb.mute = False

    # Get base vertex positions (with basis shape at value=0)
    base_positions: Dict[int, Tuple[float, float, float]] = {}
    base_normals: Dict[int, Tuple[float, float, float]] = {}
    for v in base_model.vertices:
        if v.blender_index is not None:
            base_positions[v.blender_index] = v.position
            if v.normal is not None:
                base_normals[v.blender_index] = v.normal

    morphs: List[IntermediateMorph] = []

    try:
        for ki in range(1, len(key_blocks)):
            kb = key_blocks[ki]
            kb.value = 1.0

            # Evaluate the mesh with this shape key active
            with evaluated_mesh(obj, depsgraph, False) as (morph_mesh, _):
                morph = IntermediateMorph(name=kb.name)

                for vi, base_v in enumerate(base_model.vertices):
                    if base_v.blender_index is None:
                        continue

                    bl_idx = base_v.blender_index
                    if bl_idx >= len(morph_mesh.vertices):
                        continue

                    morph_vert = morph_mesh.vertices[bl_idx]
                    morph_pos = _blender_to_urho_pos(morph_vert.co, settings.scale)

                    # Position delta
                    dx = morph_pos[0] - base_v.position[0]
                    dy = morph_pos[1] - base_v.position[1]
                    dz = morph_pos[2] - base_v.position[2]

                    if abs(dx) < EPSILON and abs(dy) < EPSILON and abs(dz) < EPSILON:
                        continue

                    # Normal delta
                    normal_delta = None
                    if settings.export_morph_normals and base_v.normal is not None:
                        if hasattr(morph_mesh, 'corner_normals') and len(morph_mesh.corner_normals) > 0:
                            # Use vertex normal as approximation for morph
                            mn = morph_vert.normal
                            morph_n = _blender_to_urho_normal(mn)
                            normal_delta = (
                                morph_n[0] - base_v.normal[0],
                                morph_n[1] - base_v.normal[1],
                                morph_n[2] - base_v.normal[2],
                            )

                    morph.vertices.append(IntermediateMorphVertex(
                        vertex_index=vi,
                        position_delta=(dx, dy, dz),
                        normal_delta=normal_delta,
                    ))

                if morph.vertices:
                    morphs.append(morph)
                    log.info(f"Morph '{kb.name}': {len(morph.vertices)} affected vertices")

            kb.value = 0.0

    finally:
        # Restore original values
        for i, (val, mute) in enumerate(saved_values):
            key_blocks[i].value = val
            key_blocks[i].mute = mute

    return morphs


def decompose_lod_objects(
    objects: list,
    depsgraph,
    settings: ExportSettings,
    log: ExportLogger,
) -> Dict[str, IntermediateModel]:
    """
    Detect LOD objects by naming convention (ObjectName_LOD0, _LOD1, _LOD2...)
    and merge LOD levels into the base geometry.

    Convention: "MyMesh_LOD0.5" means LOD distance 0.5
    Returns: dict of base_name -> IntermediateModel with merged LODs
    """
    import re
    lod_pattern = re.compile(r'^(.+)_LOD(\d+\.?\d*)$')

    # Group objects by base name — only track LOD-related objects
    lod_variants: Dict[str, list] = {}  # base_name -> [(distance, obj)]
    base_candidates: Dict[str, object] = {}  # base_name -> base obj

    for obj in objects:
        if obj.type != 'MESH':
            continue
        match = lod_pattern.match(obj.name)
        if match:
            base_name = match.group(1)
            distance = float(match.group(2))
            if base_name not in lod_variants:
                lod_variants[base_name] = []
            lod_variants[base_name].append((distance, obj))
        else:
            base_candidates[obj.name] = obj

    # Build final groups: only include bases that have LOD variants
    base_objects: Dict[str, list] = {}
    for base_name, variants in lod_variants.items():
        lod_list = list(variants)
        # Add the base object as LOD0 if it exists
        if base_name in base_candidates:
            lod_list.insert(0, (0.0, base_candidates[base_name]))
        lod_list.sort(key=lambda x: x[0])
        base_objects[base_name] = lod_list

    results: Dict[str, IntermediateModel] = {}

    for base_name, lod_list in base_objects.items():
        # Decompose each LOD level (already sorted by distance)
        base_model = None
        for distance, obj in lod_list:
            model = decompose_mesh(obj, depsgraph, settings, log)
            if model is None:
                continue

            if base_model is None:
                base_model = model
                base_model.name = base_name
                # Set distance for LOD0 geometries
                for geom in base_model.geometries:
                    for lod in geom.lod_levels:
                        lod.distance = distance
            else:
                # Merge LOD variant's vertices into base model
                vertex_offset = len(base_model.vertices)
                base_model.vertices.extend(model.vertices)

                # Expand bounding box
                base_model.bbox_min = (
                    min(base_model.bbox_min[0], model.bbox_min[0]),
                    min(base_model.bbox_min[1], model.bbox_min[1]),
                    min(base_model.bbox_min[2], model.bbox_min[2]),
                )
                base_model.bbox_max = (
                    max(base_model.bbox_max[0], model.bbox_max[0]),
                    max(base_model.bbox_max[1], model.bbox_max[1]),
                    max(base_model.bbox_max[2], model.bbox_max[2]),
                )

                if len(model.geometries) != len(base_model.geometries):
                    log.warning(
                        f"LOD '{obj.name}' has {len(model.geometries)} geometries "
                        f"but base '{base_name}' has {len(base_model.geometries)} "
                        f"(material count mismatch)")

                # Merge as additional LOD level with remapped indices
                for gi, geom in enumerate(model.geometries):
                    if gi < len(base_model.geometries):
                        for lod in geom.lod_levels:
                            lod.distance = distance
                            # Offset triangle indices to reference merged vertex buffer
                            lod.triangles = [
                                (a + vertex_offset, b + vertex_offset, c + vertex_offset)
                                for a, b, c in lod.triangles
                            ]
                            base_model.geometries[gi].lod_levels.append(lod)

                log.info(f"LOD {distance} merged for '{base_name}' from '{obj.name}' "
                         f"(+{len(model.vertices)} vertices)")

        if base_model:
            results[base_name] = base_model

    return results


def _build_bone_weights(
    obj,
    mesh,
    log: ExportLogger,
) -> Dict[int, Tuple[Tuple[float, ...], Tuple[int, ...]]]:
    """
    Build a lookup of vertex_index -> (weights_tuple, indices_tuple).
    Weights are normalized, max 4 per vertex (BONES_PER_VERTEX).
    """
    MAX_BONES = 4
    result: Dict[int, Tuple[Tuple[float, ...], Tuple[int, ...]]] = {}

    # Map vertex group index -> bone index
    # Vertex groups may include non-bone groups, filter by armature bone names
    armature_obj = obj.find_armature()
    if not armature_obj:
        return result

    bone_names = set(b.name for b in armature_obj.data.bones)
    group_to_bone: Dict[int, int] = {}
    bone_index_map: Dict[str, int] = {}

    # Build bone name -> bone index (order in armature.bones)
    for i, bone in enumerate(armature_obj.data.bones):
        bone_index_map[bone.name] = i

    for vg in obj.vertex_groups:
        if vg.name in bone_names:
            group_to_bone[vg.index] = bone_index_map[vg.name]

    # Extract per-vertex weights
    for vert in mesh.vertices:
        weights = []
        for g in vert.groups:
            if g.group in group_to_bone and g.weight > 0.0001:
                weights.append((g.weight, group_to_bone[g.group]))

        if not weights:
            continue

        # Sort by weight descending, keep top 4
        weights.sort(key=lambda x: x[0], reverse=True)
        weights = weights[:MAX_BONES]

        # Normalize
        total = sum(w for w, _ in weights)
        if total > 0:
            weights = [(w / total, idx) for w, idx in weights]

        # Pad to 4
        while len(weights) < MAX_BONES:
            weights.append((0.0, 0))

        w_tuple = tuple(w for w, _ in weights)
        i_tuple = tuple(idx for _, idx in weights)
        result[vert.index] = (w_tuple, i_tuple)

    return result
