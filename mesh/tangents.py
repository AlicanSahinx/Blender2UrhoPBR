"""Tangent generation using the Lengyel algorithm."""

from __future__ import annotations

import math
from typing import List, Tuple

from ..data.intermediate import IntermediateModel


def generate_tangents(model: IntermediateModel) -> None:
    """
    Generate tangent vectors for all vertices in the model using
    the Lengyel method (Computing Tangent Space Basis Vectors).

    Requires positions, normals, and UV coordinates to be present.
    Modifies vertices in-place, setting tangent as (tx, ty, tz, sign).
    """
    vertex_count = len(model.vertices)
    if vertex_count == 0:
        return

    # Check prerequisites
    v0 = model.vertices[0]
    if v0.normal is None or v0.uv is None:
        return

    # Accumulators
    tan1 = [(0.0, 0.0, 0.0)] * vertex_count  # tangent direction
    tan2 = [(0.0, 0.0, 0.0)] * vertex_count  # bitangent direction

    # Process all triangles
    for geom in model.geometries:
        for lod in geom.lod_levels:
            for tri in lod.triangles:
                i0, i1, i2 = tri
                v0 = model.vertices[i0]
                v1 = model.vertices[i1]
                v2 = model.vertices[i2]

                p0, p1, p2 = v0.position, v1.position, v2.position
                uv0, uv1, uv2 = v0.uv, v1.uv, v2.uv

                # Edge vectors
                dx1 = p1[0] - p0[0]
                dy1 = p1[1] - p0[1]
                dz1 = p1[2] - p0[2]
                dx2 = p2[0] - p0[0]
                dy2 = p2[1] - p0[1]
                dz2 = p2[2] - p0[2]

                # UV edge vectors
                du1 = uv1[0] - uv0[0]
                dv1 = uv1[1] - uv0[1]
                du2 = uv2[0] - uv0[0]
                dv2 = uv2[1] - uv0[1]

                det = du1 * dv2 - du2 * dv1
                if abs(det) < 1e-8:
                    continue
                r = 1.0 / det

                # Tangent direction
                sx = (dv2 * dx1 - dv1 * dx2) * r
                sy = (dv2 * dy1 - dv1 * dy2) * r
                sz = (dv2 * dz1 - dv1 * dz2) * r

                # Bitangent direction
                tx = (du1 * dx2 - du2 * dx1) * r
                ty = (du1 * dy2 - du2 * dy1) * r
                tz = (du1 * dz2 - du2 * dz1) * r

                # Accumulate for each vertex of the triangle
                for idx in (i0, i1, i2):
                    t1 = tan1[idx]
                    tan1[idx] = (t1[0] + sx, t1[1] + sy, t1[2] + sz)
                    t2 = tan2[idx]
                    tan2[idx] = (t2[0] + tx, t2[1] + ty, t2[2] + tz)

    # Orthogonalize and compute handedness
    for i in range(vertex_count):
        v = model.vertices[i]
        if v.normal is None:
            continue

        n = v.normal
        t = tan1[i]

        # Gram-Schmidt orthogonalize: tangent = normalize(t - n * dot(n, t))
        dot_nt = n[0] * t[0] + n[1] * t[1] + n[2] * t[2]
        tx = t[0] - n[0] * dot_nt
        ty = t[1] - n[1] * dot_nt
        tz = t[2] - n[2] * dot_nt

        length = math.sqrt(tx * tx + ty * ty + tz * tz)
        if length < 1e-8:
            v.tangent = (0.0, 0.0, 0.0, 1.0)
            continue

        inv_len = 1.0 / length
        tx *= inv_len
        ty *= inv_len
        tz *= inv_len

        # Handedness: sign = dot(cross(n, t), tan2) < 0 ? -1 : 1
        cx = n[1] * t[2] - n[2] * t[1]
        cy = n[2] * t[0] - n[0] * t[2]
        cz = n[0] * t[1] - n[1] * t[0]
        b = tan2[i]
        sign = -1.0 if (cx * b[0] + cy * b[1] + cz * b[2]) < 0.0 else 1.0

        v.tangent = (tx, ty, tz, sign)
