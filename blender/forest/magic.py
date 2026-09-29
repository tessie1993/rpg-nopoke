"""The magical layer: rune stone circle, crystals, fairy ring, wisps, fireflies."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import config
from .shapes import rock
from .util import add_blocker, mesh_data, mesh_object, new_bmesh_with_uv, sweep_tube

# Elder Futhark runes as strokes in a unit box (x in [-0.5, 0.5], y in [0, 1]).
STAVE = ((0.0, 0.0), (0.0, 1.0))
RUNES = {
    "fehu": (STAVE, ((0.0, 0.55), (0.38, 0.85)), ((0.0, 0.8), (0.32, 1.0))),
    "uruz": (((-0.3, 0.0), (-0.3, 1.0)), ((-0.3, 1.0), (0.3, 0.7)), ((0.3, 0.7), (0.3, 0.0))),
    "thurisaz": (((-0.2, 0.0), (-0.2, 1.0)), ((-0.2, 0.75), (0.25, 0.5)), ((0.25, 0.5), (-0.2, 0.25))),
    "ansuz": (STAVE, ((0.0, 1.0), (0.35, 0.8)), ((0.0, 0.75), (0.35, 0.55))),
    "raidho": (STAVE, ((0.0, 1.0), (0.35, 0.78)), ((0.35, 0.78), (0.0, 0.55)), ((0.0, 0.55), (0.35, 0.0))),
    "kenaz": (((0.3, 0.8), (-0.2, 0.5)), ((-0.2, 0.5), (0.3, 0.2))),
    "algiz": (STAVE, ((0.0, 0.6), (-0.35, 1.0)), ((0.0, 0.6), (0.35, 1.0))),
    "sowilo": (((0.25, 1.0), (-0.25, 0.62)), ((-0.25, 0.62), (0.25, 0.38)), ((0.25, 0.38), (-0.25, 0.0))),
    "tiwaz": (STAVE, ((0.0, 1.0), (-0.35, 0.65)), ((0.0, 1.0), (0.35, 0.65))),
    "othala": (((0.0, 1.0), (0.32, 0.65)), ((0.32, 0.65), (0.0, 0.3)), ((0.0, 0.3), (-0.32, 0.65)),
               ((-0.32, 0.65), (0.0, 1.0)), ((0.0, 0.3), (0.3, 0.0)), ((0.0, 0.3), (-0.3, 0.0))),
}


def standing_stone(name, coll, mat, seed, height):
    bm = bmesh.new()
    rock(bm, 1.0, seed, subdivisions=5, squash=1.0, roughness=0.22, flat_cuts=2)
    bmesh.ops.scale(bm, vec=(0.42, 0.24, height / 2.0), verts=bm.verts)
    for v in bm.verts:       # taper toward the top
        t = (v.co.z / height) + 0.5
        v.co.x *= 1.0 - 0.25 * t
        v.co.y *= 1.0 - 0.15 * t
    bmesh.ops.translate(bm, vec=(0, 0, height / 2.0 - 0.35), verts=bm.verts)
    return mesh_object(name, bm, coll, mat)


def carve_runes(stone, coll, mat, names, rune_size=0.26):
    """Glowing rune strokes that follow the stone's +Y face (found by raycast)."""
    bm_stone = bmesh.new()
    bm_stone.from_mesh(stone.data)
    tree = BVHTree.FromBMesh(bm_stone)
    bm_stone.free()
    bm, uv = new_bmesh_with_uv()
    top = max(v.co.z for v in stone.data.vertices)
    for k, name in enumerate(names):
        centre_z = top - 0.45 - k * rune_size * 1.35
        for (x0, y0), (x1, y1) in RUNES[name]:
            samples = []
            for i in range(7):
                t = i / 6
                x = (x0 + (x1 - x0) * t) * rune_size
                z = centre_z + ((y0 + (y1 - y0) * t) - 0.5) * rune_size
                hit, normal, _, _ = tree.ray_cast(Vector((x, 2.0, z)), Vector((0, -1, 0)))
                if hit is not None:
                    samples.append(hit - normal * 0.004)
            if len(samples) > 1:
                sweep_tube(bm, samples, [0.011] * len(samples), 6, uv_layer=uv)
    runes = mesh_object(f"{stone.name} Runes", bm, coll, mat)
    runes.parent = stone
    return runes


def stone_circle(coll, blockers, terrain, mats, seed=71):
    rng = random.Random(seed)
    cx, cy = config.CLEARING_CENTER
    names = list(RUNES)
    stones = []
    for i in range(config.STONE_COUNT):
        angle = -math.pi / 2 + math.tau * (i + 0.5) / config.STONE_COUNT
        # Nudge stones off the paths that cross the circle.
        for nudge in (0.0, 0.18, -0.18, 0.32, -0.32):
            a = angle + nudge
            x = cx + config.STONE_CIRCLE_RADIUS * math.cos(a)
            y = cy + config.STONE_CIRCLE_RADIUS * math.sin(a)
            if terrain.path_distance(x, y) > 1.5:
                break
        stone = standing_stone(f"Rune Stone {i}", coll, mats.runestone, seed + i, rng.uniform(1.7, 2.5))
        stone.location = terrain.point(x, y)
        facing = math.atan2(cy - y, cx - x) - math.pi / 2     # local +Y toward the centre
        stone.rotation_euler = (rng.uniform(-0.06, 0.06), rng.uniform(-0.06, 0.06), facing)
        carve_runes(stone, coll, mats.rune_glow, rng.sample(names, 3))
        bpy.context.view_layer.update()
        add_blocker(stone, blockers)
        stones.append(stone)
    return stones


def crystal(bm, uv, base, direction, length, radius, material_index, rng):
    """Hexagonal crystal: slightly tapered prism with a pyramidal tip."""
    rot = direction.to_track_quat("Z", "Y").to_matrix().to_4x4()
    frame = Matrix.Translation(base) @ rot @ Matrix.Rotation(rng.uniform(0, math.tau), 4, "Z")
    rings = []
    for z, scale in ((-0.1 * length, 1.0), (0.75 * length, 0.9)):
        ring = [bm.verts.new(frame @ Vector((radius * scale * math.cos(k * math.pi / 3),
                                             radius * scale * math.sin(k * math.pi / 3), z))) for k in range(6)]
        rings.append(ring)
    tip = bm.verts.new(frame @ Vector((rng.uniform(-0.2, 0.2) * radius, rng.uniform(-0.2, 0.2) * radius, length)))
    faces = []
    for k in range(6):
        k2 = (k + 1) % 6
        faces.append(bm.faces.new((rings[0][k], rings[0][k2], rings[1][k2], rings[1][k])))
        faces.append(bm.faces.new((rings[1][k], rings[1][k2], tip)))
    faces.append(bm.faces.new(list(reversed(rings[0]))))
    for face in faces:
        face.material_index = material_index
        face.smooth = False


def crystal_cluster(name, coll, mats, centre, count, size, seed):
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    for i in range(count):
        tilt = 0.0 if i == 0 else rng.uniform(0.25, 0.9)
        yaw = rng.uniform(0, math.tau)
        direction = Vector((math.sin(tilt) * math.cos(yaw), math.sin(tilt) * math.sin(yaw), math.cos(tilt)))
        length = size * (1.0 if i == 0 else rng.uniform(0.35, 0.75))
        offset = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), 0)) * size * 0.12
        violet = 1 if i % 3 == 2 else 0
        crystal(bm, uv, offset, direction, length, length * rng.uniform(0.12, 0.18), violet, rng)
    obj = bpy.data.objects.new(name, mesh_data(name, bm, mats.crystal, smooth=False))
    obj.data.materials.append(mats.crystal_violet)
    coll.objects.link(obj)
    obj.location = centre
    obj.visible_shadow = False        # glowing crystals must not block their own lights
    return obj


def point_light(name, coll, location, color, energy, radius):
    light = bpy.data.lights.new(name, "POINT")
    light.color = color
    light.energy = energy
    light.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, light)
    obj.location = location
    coll.objects.link(obj)
    return obj


def crystals(coll, blockers, terrain, mats):
    cx, cy = config.CLEARING_CENTER
    altar = bmesh.new()
    rock(altar, 0.75, 77, subdivisions=5, squash=0.45, roughness=0.3, flat_cuts=3)
    altar_obj = mesh_object("Crystal Altar", altar, coll, mats.boulder)
    altar_obj.location = terrain.point(cx, cy, -0.1)
    bpy.context.view_layer.update()
    add_blocker(altar_obj, blockers)
    crystal_cluster("Altar Crystals", coll, mats, terrain.point(cx, cy, 0.15), 13, 1.3, 81)
    point_light("Altar Glow", coll, terrain.point(cx, cy, 1.1), (0.35, 0.8, 1.0), 150.0, 0.3)

    hx, hy = config.HERO_TREE
    for i, (dx, dy) in enumerate(((2.3, -1.2), (-2.0, -1.8), (0.6, -2.6))):
        x, y = hx + dx, hy + dy
        crystal_cluster(f"Root Crystals {i}", coll, mats, terrain.point(x, y, -0.05), 7, 0.55, 90 + i)
        point_light(f"Root Crystal Glow {i}", coll, terrain.point(x, y, 0.5), (0.45, 0.6, 1.0), 45.0, 0.2)


def fairy_ring(coll, terrain, glowcaps, centre=(4.3, 5.6), radius=1.25, count=16, seed=95):
    rng = random.Random(seed)
    sources = list(glowcaps.objects)
    for i in range(count):
        a = math.tau * i / count + rng.uniform(-0.1, 0.1)
        x = centre[0] + radius * math.cos(a) * rng.uniform(0.92, 1.08)
        y = centre[1] + radius * math.sin(a) * rng.uniform(0.92, 1.08)
        obj = bpy.data.objects.new(f"Fairy Ring {i}", sources[i % len(sources)].data)
        obj.location = terrain.point(x, y)
        obj.rotation_euler.z = rng.uniform(0, math.tau)
        obj.scale = (rng.uniform(1.0, 1.6),) * 3
        coll.objects.link(obj)
    point_light("Fairy Ring Glow", coll, terrain.point(centre[0], centre[1], 0.35), (0.3, 0.9, 1.0), 30.0, 0.5)


def wisps(coll, terrain, mats, count=30, seed=101):
    """Floating light orbs along the path, in the clearing and around the hero tree."""
    rng = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1.0)
    orb = mesh_data("Wisp Orb", bm, mats.wisp)
    cx, cy = config.CLEARING_CENTER
    hx, hy = config.HERO_TREE
    for i in range(count):
        zone = i % 3
        if zone == 0:
            a, r = rng.uniform(0, math.tau), rng.uniform(1.0, 6.5)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        elif zone == 1:
            y = rng.uniform(-16.0, 3.0)
            x = rng.uniform(-3.0, 3.0)
        else:
            a, r = rng.uniform(0, math.tau), rng.uniform(2.5, 6.0)
            x, y = hx + r * math.cos(a), hy + r * math.sin(a)
        obj = bpy.data.objects.new(f"Wisp {i}", orb)
        obj.visible_shadow = False        # some orbs contain a point light
        obj.location = terrain.point(x, y, rng.uniform(0.8, 3.4))
        obj.scale = (rng.uniform(0.015, 0.03),) * 3
        coll.objects.link(obj)
        if i % 5 == 0:
            point_light(f"Wisp Light {i}", coll, obj.location, (0.55, 0.9, 1.0), 12.0, 0.05)


def fireflies(coll, terrain, mats, count=450, seed=113):
    rng = random.Random(seed)
    bm = bmesh.new()
    for _ in range(count):
        x, y = rng.uniform(-14, 14), rng.uniform(-26, 24)
        centre = terrain.point(x, y, rng.uniform(0.25, 2.6))
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=rng.uniform(0.004, 0.008),
                                   matrix=Matrix.Translation(centre))
    return mesh_object("Fireflies", bm, coll, mats.firefly)


def build(coll, blockers, terrain, mats, assets):
    stone_circle(coll, blockers, terrain, mats)
    crystals(coll, blockers, terrain, mats)
    fairy_ring(coll, terrain, assets.glowcaps)
    wisps(coll, terrain, mats)
    fireflies(coll, terrain, mats)
