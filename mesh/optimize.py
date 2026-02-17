"""Vertex cache optimization using Tom Forsyth's linear-speed algorithm."""

from __future__ import annotations

from typing import List, Tuple

# Typical GPU post-transform vertex cache size
CACHE_SIZE = 32

# Score constants (Forsyth's recommended values)
_LAST_TRI_SCORE = 0.75
_CACHE_DECAY_POWER = 1.5
_VALENCE_BOOST_SCALE = 2.0
_VALENCE_BOOST_POWER = -0.5


def _vertex_score(cache_position: int, active_tri_count: int) -> float:
    """
    Compute Forsyth vertex score.

    cache_position: -1 if not in cache, otherwise 0..CACHE_SIZE-1
    active_tri_count: number of not-yet-emitted triangles using this vertex
    """
    if active_tri_count == 0:
        return -1.0

    score = 0.0

    # Cache position score
    if cache_position >= 0:
        if cache_position < 3:
            # Vertices from the most recent triangle get a fixed bonus
            score = _LAST_TRI_SCORE
        else:
            # Score decays with position in cache
            t = (cache_position - 3) / (CACHE_SIZE - 3)
            score = (1.0 - t) ** _CACHE_DECAY_POWER

    # Valence boost: fewer remaining triangles = higher priority
    score += _VALENCE_BOOST_SCALE * (active_tri_count ** _VALENCE_BOOST_POWER)

    return score


def optimize_triangles(
    triangles: List[Tuple[int, int, int]],
    vertex_count: int,
) -> List[Tuple[int, int, int]]:
    """
    Reorder triangles for optimal GPU vertex cache utilization.

    Uses Tom Forsyth's linear-speed vertex cache optimization algorithm.
    Returns a new list of triangles in optimized order.

    If the input is small enough to fit entirely in cache, returns as-is.
    """
    tri_count = len(triangles)
    if tri_count <= 1 or vertex_count <= CACHE_SIZE:
        return list(triangles)

    # Per-vertex: list of triangle indices that use this vertex
    vert_tris: List[List[int]] = [[] for _ in range(vertex_count)]
    for ti, tri in enumerate(triangles):
        for vi in tri:
            if 0 <= vi < vertex_count:
                vert_tris[vi].append(ti)

    # Per-vertex active triangle count (decremented as triangles are emitted)
    active_count = [len(tl) for tl in vert_tris]

    # Per-vertex cache position (-1 = not in cache)
    cache_pos = [-1] * vertex_count

    # Per-vertex score
    scores = [_vertex_score(-1, active_count[v]) for v in range(vertex_count)]

    # Per-triangle score (sum of its vertex scores)
    tri_scores = [0.0] * tri_count
    for ti, tri in enumerate(triangles):
        tri_scores[ti] = sum(scores[v] for v in tri if 0 <= v < vertex_count)

    # Emitted flag per triangle
    emitted = [False] * tri_count

    # LRU cache (most recent at front)
    cache: List[int] = []

    # Find the best starting triangle
    best_tri = max(range(tri_count), key=lambda i: tri_scores[i])

    result: List[Tuple[int, int, int]] = []
    emitted_count = 0

    while emitted_count < tri_count:
        if emitted[best_tri]:
            # Find next best un-emitted triangle
            best_tri = -1
            best_score = -2.0
            for ti in range(tri_count):
                if not emitted[ti] and tri_scores[ti] > best_score:
                    best_score = tri_scores[ti]
                    best_tri = ti
            if best_tri < 0:
                break

        # Emit triangle
        tri = triangles[best_tri]
        result.append(tri)
        emitted[best_tri] = True
        emitted_count += 1

        # Update cache with the 3 vertices of the emitted triangle
        new_verts = []
        for v in tri:
            if 0 <= v < vertex_count:
                active_count[v] -= 1
                if cache_pos[v] < 0:
                    new_verts.append(v)

        # Insert new vertices at front of cache, shift others
        old_cache = cache[:]
        cache = list(tri[i] for i in range(3) if 0 <= tri[i] < vertex_count)
        for v in old_cache:
            if v not in cache:
                cache.append(v)

        # Trim cache to size
        if len(cache) > CACHE_SIZE:
            for v in cache[CACHE_SIZE:]:
                cache_pos[v] = -1
            cache = cache[:CACHE_SIZE]

        # Update cache positions
        for pos, v in enumerate(cache):
            cache_pos[v] = pos

        # Recompute scores for affected vertices
        dirty_verts = set()
        for v in cache:
            dirty_verts.add(v)
        for v in tri:
            if 0 <= v < vertex_count:
                dirty_verts.add(v)

        for v in dirty_verts:
            scores[v] = _vertex_score(cache_pos[v], active_count[v])

        # Recompute triangle scores for triangles touching dirty vertices
        # and find the best next triangle
        best_tri = -1
        best_score = -2.0

        dirty_tris = set()
        for v in dirty_verts:
            for ti in vert_tris[v]:
                if not emitted[ti]:
                    dirty_tris.add(ti)

        for ti in dirty_tris:
            s = sum(scores[v] for v in triangles[ti] if 0 <= v < vertex_count)
            tri_scores[ti] = s
            if s > best_score:
                best_score = s
                best_tri = ti

    return result


def optimize_model_indices(model) -> None:
    """
    Optimize all triangle lists in an IntermediateModel for vertex cache.
    Modifies geometry LOD levels in-place.
    """
    vertex_count = len(model.vertices)
    for geom in model.geometries:
        for lod in geom.lod_levels:
            if lod.triangles:
                lod.triangles = optimize_triangles(lod.triangles, vertex_count)
