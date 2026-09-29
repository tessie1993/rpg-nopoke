"""Scatterable assets: grass, ferns, flowers, mushrooms, twigs, pebbles, leaves.

Each builder returns one mesh object at the origin, standing on Z = 0.
"""
import math
import random
import zlib
from types import SimpleNamespace

import bmesh
from mathutils import Matrix, Vector

from .shapes import add_blade, add_leaf, lathe, rock
from .util import collection, mesh_object, new_bmesh_with_uv, sweep_tube


def grass_clump(name, coll, material, seed, blades=28, height=0.38, spread=0.09, dry=False):
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    for _ in range(blades):
        r = spread * math.sqrt(rng.random())
        a = rng.uniform(0, 2 * math.pi)
        base = Vector((r * math.cos(a), r * math.sin(a), -0.01))
        outward = a + rng.uniform(-0.6, 0.6)
        add_blade(bm, uv, base, outward,
                  lean=rng.uniform(0.08, 0.45), curl=rng.uniform(0.4, 1.4 if dry else 1.0),
                  height=height * rng.uniform(0.55, 1.0), width=rng.uniform(0.005, 0.011),
                  segments=7, twist=rng.uniform(-0.8, 0.8))
    return mesh_object(name, bm, coll, material)


def fern(name, coll, material, seed, fronds=9, length=0.75):
    """Arching fronds with lobed pinnae that shrink toward the tip."""
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    for f in range(fronds):
        yaw = 2 * math.pi * f / fronds + rng.uniform(-0.25, 0.25)
        frond_len = length * rng.uniform(0.7, 1.05)
        heading = Vector((math.cos(yaw), math.sin(yaw), 0))
        side = Vector((-heading.y, heading.x, 0))
        start_pitch, end_pitch = rng.uniform(0.25, 0.55), rng.uniform(1.6, 2.1)
        steps = 16
        spine = [Vector((0, 0, 0))]
        dirs = []
        for i in range(steps):
            t = i / (steps - 1)
            pitch = start_pitch + (end_pitch - start_pitch) * t ** 1.5
            d = heading * math.sin(pitch) + Vector((0, 0, math.cos(pitch)))
            dirs.append(d)
            spine.append(spine[-1] + d * frond_len / steps)
        sweep_tube(bm, spine, [0.004 * (1 - 0.8 * i / steps) for i in range(len(spine))], 4,
                   uv_layer=uv, cap_end=False)
        pairs = 22
        for p in range(pairs):
            t = 0.12 + 0.86 * p / pairs
            i = min(int(t * steps), steps - 1)
            origin = spine[i].lerp(spine[i + 1], t * steps - i)
            direction = dirs[i]
            normal = direction.cross(side).normalized()
            if normal.z < 0:
                normal = -normal
            pinna_len = frond_len * 0.2 * math.sin(math.pi * min(1.0, 0.15 + t * 0.95)) ** 0.8
            for sign in (-1, 1):
                out = (side * sign * 0.85 + direction * 0.5).normalized()
                up = normal - out * normal.dot(out)
                x_axis = out.cross(up).normalized()
                frame = Matrix((x_axis, out, up.normalized())).transposed().to_4x4()
                roll = Matrix.Rotation(sign * 0.1, 4, 'Y')
                frame.translation = origin
                add_leaf(bm, uv, frame @ roll, pinna_len, pinna_len * 0.16,
                         curl=-0.25, fold=0.15, segments=6, lobes=0.35)
    return mesh_object(name, bm, coll, material)


def bluebell(name, coll, stem_mat, petal_mat, seed):
    """Arched stem with drooping bell flowers and strap leaves."""
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    height = rng.uniform(0.25, 0.38)
    lean = rng.uniform(0, 2 * math.pi)
    heading = Vector((math.cos(lean), math.sin(lean), 0))
    stem = [Vector((0, 0, 0))]
    for i in range(1, 12):
        t = i / 11
        stem.append(Vector((0, 0, height * t)) + heading * (0.09 * t ** 2.5))
    sweep_tube(bm, stem, [0.0022] * len(stem), 5, uv_layer=uv)
    bell_profile = [(0.0005, 0.0), (0.004, -0.004), (0.007, -0.012), (0.0085, -0.02), (0.011, -0.024)]
    for k in range(rng.randint(4, 7)):
        t = 0.55 + 0.45 * k / 6
        idx = min(int(t * 11), 11)
        anchor = stem[idx] + heading * 0.012
        tilt = Matrix.Rotation(rng.uniform(0.2, 0.5), 4, Vector((-heading.y, heading.x, 0)))
        spin = Matrix.Rotation(rng.uniform(0, 6.28), 4, 'Z')
        lathe(bm, uv, bell_profile, 10, Matrix.Translation(anchor) @ tilt @ spin, material_index=1)
    for _ in range(3):
        yaw = rng.uniform(0, 2 * math.pi)
        frame = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-0.35, 4, 'X')
        add_leaf(bm, uv, frame, rng.uniform(0.15, 0.22), 0.008, curl=-0.6, fold=0.3, segments=7)
    obj = mesh_object(name, bm, coll, stem_mat)
    obj.data.materials.append(petal_mat)
    return obj


def star_flower(name, coll, stem_mat, petal_mat, seed):
    """Small white five-petal flowers on thin stems."""
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    for _ in range(rng.randint(3, 6)):
        base = Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), 0))
        h = rng.uniform(0.08, 0.18)
        top = base + Vector((rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), h))
        sweep_tube(bm, [base, base.lerp(top, 0.5) + Vector((0.004, 0, 0)), top], [0.0012] * 3, 4, uv_layer=uv)
        face_up = Matrix.Rotation(rng.uniform(-0.4, 0.4), 4, 'X')
        start = len(bm.faces)
        for p in range(5):
            frame = (Matrix.Translation(top) @ face_up @ Matrix.Rotation(2 * math.pi * p / 5, 4, 'Z')
                     @ Matrix.Rotation(-1.35, 4, 'X'))
            add_leaf(bm, uv, frame, 0.011, 0.005, curl=0.3, fold=0.1, segments=4)
        bm.faces.ensure_lookup_table()
        for face in bm.faces[start:]:
            face.material_index = 1
    obj = mesh_object(name, bm, coll, stem_mat)
    obj.data.materials.append(petal_mat)
    return obj


def mushroom(bm, uv, base, cap_r, stem_h, cap_height, lean=0.0, yaw=0.0, stem_index=0, cap_index=1,
             gill_index=0):
    """One mushroom: flared stem, gill underside and domed cap."""
    frame = (Matrix.Translation(base) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(lean, 4, 'X'))
    sr = cap_r * 0.22
    stem = [(sr * 1.5, -0.01), (sr * 1.2, 0.0), (sr, stem_h * 0.3), (sr * 0.9, stem_h * 0.8), (sr * 0.95, stem_h)]
    lathe(bm, uv, stem, 12, frame, material_index=stem_index)
    gills = [(sr * 0.95, stem_h), (cap_r * 0.55, stem_h + cap_height * 0.12), (cap_r, stem_h + cap_height * 0.18)]
    lathe(bm, uv, gills, 20, frame, material_index=gill_index)
    cap = [(cap_r, stem_h + cap_height * 0.18), (cap_r * 1.02, stem_h + cap_height * 0.35),
           (cap_r * 0.9, stem_h + cap_height * 0.7), (cap_r * 0.6, stem_h + cap_height * 0.93),
           (cap_r * 0.25, stem_h + cap_height), (0.0, stem_h + cap_height * 1.01)]
    lathe(bm, uv, cap, 20, frame, material_index=cap_index)


def mushroom_cluster(name, coll, stem_mat, cap_mat, seed, count=5, scale=1.0, glowing=False):
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    for i in range(count):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.0, 0.06 * scale) if i else 0.0
        cap_r = scale * rng.uniform(0.018, 0.04) * (1.3 if i == 0 else 1.0)
        mushroom(bm, uv, Vector((r * math.cos(a), r * math.sin(a), 0)), cap_r,
                 stem_h=cap_r * rng.uniform(1.8, 3.2 if glowing else 2.4),
                 cap_height=cap_r * rng.uniform(0.5, 0.8), lean=rng.uniform(-0.25, 0.25),
                 yaw=rng.uniform(0, 6.28))
    obj = mesh_object(name, bm, coll, stem_mat)
    obj.data.materials.append(cap_mat)
    return obj


def twig(name, coll, material, seed, length=0.4):
    """Fallen stick with a couple of side twigs, lying on the ground."""
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()

    def branch(start, heading, length_, radius, depth):
        points, radii = [start], [radius]
        p, d = start.copy(), heading.normalized()
        steps = max(3, int(length_ / 0.04))
        for i in range(1, steps + 1):
            d = (d + Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), rng.uniform(-0.03, 0.03)))).normalized()
            d.z *= 0.2
            p = p + d * length_ / steps
            points.append(p.copy())
            radii.append(radius * (1 - 0.65 * i / steps))
        sweep_tube(bm, points, radii, 6 if depth == 0 else 5, uv_layer=uv, u_scale=2 * math.pi * radius)
        if depth < 1:
            for _ in range(rng.randint(1, 3)):
                k = rng.randint(1, len(points) - 2)
                side = Vector((-d.y, d.x, 0)) * rng.choice((-1, 1))
                branch(points[k], d * 0.6 + side, length_ * rng.uniform(0.25, 0.5), radii[k] * 0.6, depth + 1)

    r0 = rng.uniform(0.004, 0.009)
    branch(Vector((-length / 2, 0, r0 * 0.8)), Vector((1, 0, 0)), length, r0, 0)
    return mesh_object(name, bm, coll, material)


def pebble(name, coll, material, seed, size=0.06):
    bm = bmesh.new()
    rock(bm, size, seed, subdivisions=3, squash=0.55, roughness=0.3, flat_cuts=2)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, -size * 0.15))
    return mesh_object(name, bm, coll, material)


def fallen_leaf(name, coll, material, seed):
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    length = rng.uniform(0.05, 0.09)
    frame = Matrix.Translation((0, -length / 2, 0.004))
    add_leaf(bm, uv, frame, length, length * rng.uniform(0.28, 0.42),
             curl=rng.uniform(-0.3, 0.45), fold=rng.uniform(0.1, 0.4), segments=7,
             lobes=rng.choice((0.0, 0.0, 0.3)))
    return mesh_object(name, bm, coll, material)


def leaf_spray(name, coll, leaf_mat, twig_mat, seed, length=0.42, leaf_len=0.1):
    """Branchlet along +Y with side twigs and ~20 leaves facing +Z: the canopy instance."""
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()

    def twiglet(origin, heading, twig_len, radius, leaves):
        side = Vector((-heading.y, heading.x, 0.0))
        points = [origin + heading * (twig_len * i / 6) + Vector((0, 0, 0.012 * math.sin(i * 0.9)))
                  for i in range(7)]
        sweep_tube(bm, points, [radius * (1 - i / 8) for i in range(7)], 5, uv_layer=uv,
                   u_scale=2 * math.pi * radius)
        for k in range(leaves):
            t = 0.2 + 0.8 * k / (leaves - 1)
            anchor = origin + heading * (twig_len * t)
            sign = 1 if k % 2 else -1
            spread = sign * rng.uniform(0.55, 1.0) if k < leaves - 1 else rng.uniform(-0.15, 0.15)
            direction = (heading * math.cos(spread) + side * math.sin(spread)).normalized()
            x_axis = direction.cross(Vector((0, 0, 1))).normalized()
            frame = Matrix((x_axis, direction, Vector((0, 0, 1)))).transposed().to_4x4()
            frame.translation = anchor
            tilt = Matrix.Rotation(rng.uniform(-0.3, 0.15), 4, 'X') @ Matrix.Rotation(rng.uniform(-0.35, 0.35), 4, 'Y')
            start = len(bm.faces)
            add_leaf(bm, uv, frame @ tilt, leaf_len * rng.uniform(0.75, 1.2), leaf_len * 0.32,
                     curl=rng.uniform(-0.2, 0.25), fold=0.25, segments=7, lobes=0.18)
            bm.faces.ensure_lookup_table()
            for face in bm.faces[start:]:
                face.material_index = 1

    main = Vector((0, 1, 0))
    twiglet(Vector((0, 0, 0)), main, length, 0.005, 8)
    for k, t in enumerate((0.3, 0.5, 0.7)):
        sign = 1 if k % 2 else -1
        heading = Vector((sign * rng.uniform(0.5, 0.8), 1.0, rng.uniform(-0.05, 0.1))).normalized()
        twiglet(main * (length * t), heading, length * rng.uniform(0.4, 0.55), 0.0035, 5)
    obj = mesh_object(name, bm, coll, twig_mat)
    obj.data.materials.append(leaf_mat)
    return obj


def build_assets(mats, root):
    """Variant collections used as scatter sources."""
    def group(name, builder, variants, *args, **kwargs):
        coll = collection(name, parent=root)
        for i in range(variants):
            builder(f"{name} {i}", coll, *args, seed=zlib.crc32(name.encode()) % 1000 + i * 17, **kwargs)
        return coll

    return SimpleNamespace(
        grass=group("Grass", grass_clump, 5, mats.grass),
        tall_grass=group("Tall Grass", grass_clump, 3, mats.grass, blades=40, height=0.65, spread=0.12),
        dry_grass=group("Dry Grass", grass_clump, 3, mats.dry_grass, blades=22, height=0.45, dry=True),
        ferns=group("Ferns", fern, 4, mats.fern),
        bluebells=group("Bluebells", bluebell, 5, mats.stem, mats.bluebell),
        star_flowers=group("Star Flowers", star_flower, 4, mats.stem, mats.star_petal),
        toadstools=group("Toadstools", mushroom_cluster, 3, mats.mushroom_stem, mats.toadstool,
                         count=3, scale=1.8),
        glowcaps=group("Glowcaps", mushroom_cluster, 4, mats.glowcap_stem, mats.glowcap, count=7,
                       glowing=True),
        twigs=group("Twigs", twig, 7, mats.twig),
        pebbles=group("Pebbles", pebble, 6, mats.pebble),
        fallen_leaves=group("Fallen Leaves", fallen_leaf, 8, mats.fallen_leaf),
        leaf_sprays=group("Leaf Sprays", leaf_spray, 4, mats.canopy, mats.twig),
    )
