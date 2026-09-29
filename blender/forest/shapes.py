"""Low-level mesh builders: leaves, grass blades, lathed shapes, rocks."""
import math
import random

import bmesh
from mathutils import Matrix, Vector, noise


def add_leaf(bm, uv, matrix, length, width, curl=0.2, fold=0.25, segments=8, lobes=0.0):
    """Leaf along +Y with its face toward +Z, base at the origin of matrix.

    Five vertices per row (edge, half, midrib, half, edge) give a folded midrib.
    UV: u across (0.5 = midrib), v from base (0) to tip (1).
    """
    rows = []
    offsets = (-1.0, -0.5, 0.0, 0.5, 1.0)
    for i in range(segments):
        v = i / segments
        w = width * max(0.06, math.sin(math.pi * v ** 0.75) ** 0.9)
        if lobes:
            w *= 1.0 - lobes * abs(math.sin(v * math.pi * 7.0))
        y = v * length
        z_curl = curl * length * v * v
        row = []
        for o in offsets:
            z = z_curl - fold * w * abs(o)
            co = matrix @ Vector((o * w, y, z))
            row.append((bm.verts.new(co), (0.5 + o * w / (2 * width), v)))
        rows.append(row)
    tip = bm.verts.new(matrix @ Vector((0.0, length, curl * length)))

    for i in range(segments - 1):
        for k in range(4):
            quad = (rows[i][k], rows[i][k + 1], rows[i + 1][k + 1], rows[i + 1][k])
            face = bm.faces.new([q[0] for q in quad])
            for loop, q in zip(face.loops, quad):
                loop[uv].uv = q[1]
    last = rows[-1]
    for k in range(4):
        face = bm.faces.new((last[k][0], last[k + 1][0], tip))
        for loop, co in zip(face.loops, (last[k][1], last[k + 1][1], (0.5, 1.0))):
            loop[uv].uv = co


def add_blade(bm, uv, base, yaw, lean, curl, height, width, segments=7, twist=0.4, fold=0.35):
    """Grass blade rising from base, leaning along yaw and drooping with curl.

    Three vertices per row (edge, folded midrib, edge). UV v runs base -> tip.
    """
    heading = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    side0 = Vector((-heading.y, heading.x, 0.0))
    step = height / segments
    pos = Vector(base)
    rows = []
    for i in range(segments):
        t = i / segments
        theta = lean + curl * t * t
        direction = heading * math.sin(theta) + Vector((0, 0, math.cos(theta)))
        spin = twist * t
        side = side0 * math.cos(spin) + direction.cross(side0) * math.sin(spin)
        w = width * (1.0 - t ** 1.6) * (0.7 + 0.3 * math.sin(math.pi * min(1.0, t * 1.8)))
        normal = direction.cross(side).normalized()
        row = []
        for o in (-1.0, 0.0, 1.0):
            co = pos + side * (o * w) + normal * (fold * w * (1.0 - abs(o)))
            row.append((bm.verts.new(co), (0.5 + 0.5 * o, t)))
        rows.append(row)
        pos = pos + direction * step
    tip = bm.verts.new(pos)
    for i in range(segments - 1):
        for k in range(2):
            quad = (rows[i][k], rows[i][k + 1], rows[i + 1][k + 1], rows[i + 1][k])
            face = bm.faces.new([q[0] for q in quad])
            for loop, q in zip(face.loops, quad):
                loop[uv].uv = q[1]
    for k in range(2):
        face = bm.faces.new((rows[-1][k][0], rows[-1][k + 1][0], tip))
        for loop, co in zip(face.loops, (rows[-1][k][1], rows[-1][k + 1][1], (0.5, 1.0))):
            loop[uv].uv = co


def lathe(bm, uv, profile, segments, matrix=Matrix(), close_top=False, material_index=0,
          wobble=0.0, seed=0):
    """Revolve a (radius, z) profile (bottom to top) around Z."""
    rings = []
    total = sum((Vector(profile[i + 1]) - Vector(profile[i])).length for i in range(len(profile) - 1))
    v_acc = [0.0]
    for i in range(1, len(profile)):
        v_acc.append(v_acc[-1] + (Vector(profile[i]) - Vector(profile[i - 1])).length / total)
    for (r, z) in profile:
        ring = []
        for s in range(segments):
            a = 2 * math.pi * s / segments
            rr = r * (1.0 + wobble * noise.noise(Vector((math.cos(a) * 2 + seed, math.sin(a) * 2, z * 4))))
            ring.append(bm.verts.new(matrix @ Vector((rr * math.cos(a), rr * math.sin(a), z))))
        rings.append(ring)
    faces = []
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            face = bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
            face.material_index = material_index
            for loop, co in zip(face.loops, ((s / segments, v_acc[i]), ((s + 1) / segments, v_acc[i]),
                                              ((s + 1) / segments, v_acc[i + 1]), (s / segments, v_acc[i + 1]))):
                loop[uv].uv = co
            faces.append(face)
    if close_top:
        face = bm.faces.new(rings[-1])
        face.material_index = material_index
    return rings, faces


def rock(bm, radius, seed, subdivisions=5, squash=0.65, roughness=0.35, flat_cuts=3):
    """Displaced icosphere with a few planar cuts for fractured faces."""
    rng = random.Random(seed)
    bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=radius)
    offset = Vector((rng.uniform(-50, 50), rng.uniform(-50, 50), rng.uniform(-50, 50)))
    planes = []
    for _ in range(flat_cuts):
        n = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 1))).normalized()
        planes.append((n, radius * rng.uniform(0.62, 0.8)))
    for v in bm.verts:
        p = v.co.copy()
        d = p.normalized()
        big = noise.fractal(d * 1.3 + offset, 1.0, 2.0, 3)
        small = noise.fractal(d * 4.0 + offset, 0.6, 2.2, 4)
        r = radius * (1.0 + roughness * 0.55 * big + roughness * 0.18 * small)
        p = d * r
        for n, dist in planes:
            depth = p.dot(n) - dist
            if depth > 0:
                p -= n * depth * 0.92
        p.z *= squash
        v.co = p
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
