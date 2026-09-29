"""Hand-placed natural props: boulders, a fallen log, stumps."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

from . import config
from .shapes import lathe, rock
from .trees import add_base_moss, resample, trunk_relief
from .util import add_blocker, mesh_data, mesh_object, new_bmesh_with_uv, sweep_tube


def boulders(coll, blockers, terrain, mat, seed=31):
    rng = random.Random(seed)
    shapes = []
    for i in range(5):
        bm = bmesh.new()
        rock(bm, 1.0, seed + i, subdivisions=6, squash=rng.uniform(0.55, 0.8), roughness=0.4, flat_cuts=4)
        shapes.append(mesh_data(f"Boulder Shape {i}", bm, mat))

    # (x, y, size): framing the path, around the clearing and in the forest.
    spots = [(-2.6, -14.5, 0.7), (2.9, -21.0, 0.9), (-3.4, -4.0, 1.1), (3.6, -7.5, 0.55),
             (-6.5, 4.0, 1.4), (7.4, 11.5, 1.2), (-8.0, 13.0, 0.9), (4.5, 20.5, 1.6),
             (-12.0, -8.0, 1.8), (11.0, -12.0, 1.3), (-16.0, 22.0, 2.0), (15.0, 2.0, 1.5),
             (-2.2, -26.0, 0.8), (1.4, 16.0, 0.6), (-1.1, 22.8, 0.9)]
    placed = []
    for i, (x, y, size) in enumerate(spots):
        obj = bpy.data.objects.new(f"Boulder {i}", shapes[i % len(shapes)])
        coll.objects.link(obj)
        obj.scale = (size * rng.uniform(0.9, 1.3), size * rng.uniform(0.8, 1.1), size)
        obj.rotation_euler = (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(0, math.tau))
        obj.location = terrain.point(x, y, -0.25 * size)
        bpy.context.view_layer.update()
        add_blocker(obj, blockers)
        placed.append(obj)
    return placed


def fallen_log(coll, blockers, terrain, bark_mat, wood_mat, fungus_mat, seed=41):
    rng = random.Random(seed)
    x, y = config.FALLEN_LOG
    yaw = 0.95
    length, r0, r1 = 7.0, 0.42, 0.3
    heading = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    start = Vector((x, y, 0)) - heading * (length / 2)
    points, radii = [], []
    for i in range(41):
        t = i / 40
        p = start + heading * (length * t)
        p += Vector((-heading.y, heading.x, 0)) * (0.25 * math.sin(t * 2.4))
        r = r0 + (r1 - r0) * t
        p.z = terrain.height(p.x, p.y) + r * 0.55
        points.append(p)
        radii.append(r)

    bm, uv = new_bmesh_with_uv()

    def bark(point, angle):
        rot = 1.0 + 0.05 * noise.noise(Vector((math.cos(angle) * 5, math.sin(angle) * 5, point.x + point.y)))
        return rot * (0.93 if math.sin(angle) < -0.6 else 1.0)   # rot sagging underside

    rings = sweep_tube(bm, points, radii, 40, uv_layer=uv, noise=bark, u_scale=3, cap_end=True)
    bm.faces.ensure_lookup_table()
    end_cap = bm.faces[-1]
    start_cap = bm.faces.new(rings[0])
    for cap in (start_cap, end_cap):
        cap.material_index = 1   # cut wood with growth rings
    # Broken branch stubs.
    for k in range(4):
        i = rng.randint(6, 34)
        side = Vector((-heading.y, heading.x, 0)) * rng.choice((-1, 1))
        base = points[i]
        direction = (side + Vector((0, 0, rng.uniform(0.3, 0.9)))).normalized()
        stub = [base + direction * (d * 0.6) for d in (0.0, 0.3, 0.6, 1.0)]
        sweep_tube(bm, stub, [radii[i] * f for f in (0.35, 0.3, 0.26, 0.2)], 12, uv_layer=uv)
    log = mesh_object("Fallen Log", bm, coll, bark_mat)
    log.data.materials.append(wood_mat)

    # Bracket fungi: flat horizontal shelves half sunk into the log's flank.
    bm, uv = new_bmesh_with_uv()
    side = Vector((-heading.y, heading.x, 0))
    for k in range(9):
        i = rng.randint(4, 36)
        angle = rng.uniform(-0.3, 0.7)
        normal = side * math.cos(angle) * rng.choice((-1, 1)) + Vector((0, 0, math.sin(angle)))
        center = points[i] + normal * radii[i] * 0.95
        size = rng.uniform(0.05, 0.11)
        profile = [(0.0, -0.008), (size * 1.02, -0.004), (size, 0.004), (size * 0.6, 0.014), (0.0, 0.016)]
        lathe(bm, uv, profile, 20, Matrix.Translation(center))
    fungi = mesh_object("Bracket Fungi", bm, coll, fungus_mat)
    add_blocker(log, blockers)
    return log, fungi


def stump(name, coll, blockers, terrain, x, y, radius, height, bark_mat, wood_mat, seed):
    bm, uv = new_bmesh_with_uv()
    base_z = terrain.height(x, y)
    points = [Vector((x, y, base_z - 0.4)), Vector((x, y, base_z + height))]
    points, radii = resample(points, [radius, radius * 0.92], 0.05)
    tilt = random.Random(seed).uniform(-0.06, 0.06)
    for p in points:
        p.z += tilt * (p.x - x)
    sweep_tube(bm, points, radii, 36, uv_layer=uv, noise=trunk_relief(base_z, 0.8, 5, seed),
               u_scale=max(1, round(2 * math.pi * radius)), cap_end=True)
    add_base_moss(bm, terrain.height, fade=0.8)
    bm.faces.ensure_lookup_table()
    bm.faces[-1].material_index = 1
    obj = mesh_object(name, bm, coll, bark_mat)
    obj.data.materials.append(wood_mat)
    add_blocker(obj, blockers)
    return obj


def build(coll, blockers, terrain, mats):
    boulders(coll, blockers, terrain, mats.boulder)
    fallen_log(coll, blockers, terrain, mats.log_bark, mats.cut_wood, mats.fungus)
    for i, (x, y, r, h) in enumerate(((-4.6, -10.5, 0.45, 0.55), (6.2, 6.5, 0.55, 0.4), (-9.5, 19.0, 0.6, 0.7))):
        stump(f"Stump {i}", coll, blockers, terrain, x, y, r, h, mats.tree_bark, mats.cut_wood, seed=60 + i)
