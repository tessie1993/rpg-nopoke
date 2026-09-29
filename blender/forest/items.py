"""RPG items: treasure chest with gold, lantern post, sword in stone, potions."""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import config
from .magic import point_light
from .shapes import lathe, rock
from .util import add_blocker, box_uv, mesh_data, mesh_object, new_bmesh_with_uv, sweep_tube


def facing_yaw(origin, target):
    """Yaw that turns an object's local -Y (its front) toward target."""
    d = Vector(target) - Vector(origin)
    return math.atan2(d.y, d.x) + math.pi / 2


def beveled_box(bm, size, centre, bevel=0.008):
    geom = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(centre) @ Matrix.Diagonal((*size, 1)))
    verts = geom["verts"]
    edges = list({e for v in verts for e in v.link_edges})
    bmesh.ops.bevel(bm, geom=verts + edges, offset=bevel, segments=2, affect="EDGES", profile=0.5)


def chest(coll, blockers, terrain, mats, seed=131):
    rng = random.Random(seed)
    w, d, h = 0.9, 0.56, 0.44
    x, y = config.CHEST
    root = bpy.data.objects.new("Treasure Chest", None)
    coll.objects.link(root)
    root.location = terrain.point(x, y, -0.03)
    root.rotation_euler.z = facing_yaw((x, y), (-0.2, y + 0.6))

    # Body: front/back/side panels plus floor, as bevelled plank boxes.
    bm, uv = new_bmesh_with_uv()
    t = 0.035
    for cx, cy, sx, sy in ((0, -d / 2 + t / 2, w, t), (0, d / 2 - t / 2, w, t),
                           (-w / 2 + t / 2, 0, t, d - 2 * t), (w / 2 - t / 2, 0, t, d - 2 * t)):
        for k in range(3):
            beveled_box(bm, (sx, sy, h / 3 - 0.004), (cx, cy, (k + 0.5) * h / 3))
    beveled_box(bm, (w - 2 * t, d - 2 * t, t), (0, 0, t / 2))
    box_uv(bm, uv, 2.0)
    body = mesh_object("Chest Body", bm, coll, mats.chest_wood)
    body.parent = root

    # Lid: half cylinder hinged at the back top edge, opened ~28 degrees.
    bm, uv = new_bmesh_with_uv()
    arc = [(math.cos(a) * d / 2, math.sin(a) * d / 2 * 0.8) for a in [math.pi * i / 10 for i in range(11)]]
    rows = []
    for sx in (-w / 2, w / 2):
        rows.append([bm.verts.new((sx, py, pz)) for py, pz in arc])
    for i in range(10):
        bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
    bm.faces.new(rows[0])
    bm.faces.new(list(reversed(rows[1])))
    bmesh.ops.solidify(bm, geom=list(bm.faces), thickness=0.03)
    box_uv(bm, uv, 2.0)
    lid = mesh_object("Chest Lid", bm, coll, mats.chest_wood)
    lid.parent = root
    lid.location = (0, d / 2, h)
    lid.rotation_euler.x = -math.radians(28)
    hinge_offset = Matrix.Translation((0, -d / 2, 0))   # hinge on the back edge
    lid.data.transform(hinge_offset)

    # Iron bands around body and lid, corner caps and a lock plate.
    bm, uv = new_bmesh_with_uv()
    for bx in (-w * 0.33, w * 0.33):
        beveled_box(bm, (0.05, 0.012, h), (bx, -d / 2 - 0.006, h / 2), 0.003)
        beveled_box(bm, (0.05, 0.012, h), (bx, d / 2 + 0.006, h / 2), 0.003)
    beveled_box(bm, (0.1, 0.018, 0.12), (0, -d / 2 - 0.009, h - 0.07), 0.004)
    bands = mesh_object("Chest Iron", bm, coll, mats.iron)
    bands.parent = root
    bm, uv = new_bmesh_with_uv()
    for bx in (-w * 0.33, w * 0.33):
        pts = [Vector((bx, -d / 2 + (d * (1 - math.cos(a)) / 2), math.sin(a) * d / 2 * 0.8 + 0.001))
               for a in [math.pi * i / 12 for i in range(13)]]
        sweep_tube(bm, pts, [0.01] * len(pts), 6, uv_layer=uv)
    lid_bands = mesh_object("Chest Lid Iron", bm, coll, mats.iron)
    lid_bands.parent = lid
    lid_bands.data.transform(hinge_offset)

    # Heaped gold coins inside, a few spilled in front, and a warm glow.
    bm, uv = new_bmesh_with_uv()
    for _ in range(260):
        r = 0.018
        px, py = rng.uniform(-w / 2 + 0.06, w / 2 - 0.06), rng.uniform(-d / 2 + 0.06, d / 2 - 0.06)
        heap = 0.12 * (1 - (px / (w / 2)) ** 2) * (1 - (py / (d / 2)) ** 2)
        tilt = Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "X") @ Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "Y")
        frame = Matrix.Translation((px, py, h - 0.13 + heap + rng.uniform(0, 0.03))) @ tilt
        lathe(bm, uv, [(0.0, 0.0), (r, 0.0), (r, 0.004), (0.0, 0.004)], 16, frame)
    coins = mesh_object("Gold Coins", bm, coll, mats.gold)
    coins.parent = root
    bm, uv = new_bmesh_with_uv()
    for _ in range(14):
        px, py = rng.uniform(-0.5, 0.5), rng.uniform(-0.75, -0.35)
        frame = Matrix.Translation((px, py, 0.035)) @ Matrix.Rotation(rng.uniform(-0.2, 0.2), 4, "X")
        lathe(bm, uv, [(0.0, 0.0), (0.018, 0.0), (0.018, 0.004), (0.0, 0.004)], 16, frame)
    spilled = mesh_object("Spilled Coins", bm, coll, mats.gold)
    spilled.parent = root
    glow = point_light("Chest Glow", coll, Vector((0, 0, h + 0.05)), (1.0, 0.7, 0.3), 25.0, 0.15)
    glow.parent = root
    bpy.context.view_layer.update()
    for part in (body, lid):
        add_blocker(part, blockers)
    return root


def lantern_post(coll, blockers, terrain, mats):
    x, y = config.LANTERN_POST
    base = terrain.point(x, y, -0.4)
    yaw = facing_yaw((x, y), (0.6, y))
    frame = Matrix.Translation(base) @ Matrix.Rotation(yaw, 4, "Z")
    bm, uv = new_bmesh_with_uv()
    post = [frame @ Vector((0.02 * math.sin(i), 0, 2.75 * i / 10)) for i in range(11)]
    sweep_tube(bm, post, [0.075 - 0.01 * i / 10 for i in range(11)], 10, uv_layer=uv, u_scale=1)
    arm = [frame @ Vector((0, -0.7 * i / 6, 2.6 + 0.02 * math.sin(i))) for i in range(7)]
    sweep_tube(bm, arm, [0.045] * 7, 8, uv_layer=uv)
    brace = [frame @ Vector((0, -0.35 * i / 4, 2.2 + 0.36 * i / 4)) for i in range(5)]
    sweep_tube(bm, brace, [0.03] * 5, 6, uv_layer=uv)
    wood = mesh_object("Lantern Post", bm, coll, mats.log_bark)
    add_blocker(wood, blockers)

    hang = frame @ Vector((0, -0.62, 2.58))
    top = hang - Vector((0, 0, 0.18))
    bm, uv = new_bmesh_with_uv()
    sweep_tube(bm, [hang, top], [0.004, 0.004], 6, uv_layer=uv)
    lathe(bm, uv, [(0.0, 0.0), (0.02, 0.0), (0.11, -0.07), (0.1, -0.085), (0.0, -0.085)], 4,
          Matrix.Translation(top) @ Matrix.Rotation(math.pi / 4, 4, "Z"))
    body_bottom = top - Vector((0, 0, 0.36))
    lathe(bm, uv, [(0.0, 0.0), (0.095, 0.0), (0.095, 0.03), (0.0, 0.03)], 4,
          Matrix.Translation(body_bottom) @ Matrix.Rotation(math.pi / 4, 4, "Z"))
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        corner = Vector((math.cos(a), math.sin(a), 0)) * 0.093
        sweep_tube(bm, [body_bottom + corner, top - Vector((0, 0, 0.085)) + corner], [0.006] * 2, 5, uv_layer=uv)
    iron = mesh_object("Lantern Frame", bm, coll, mats.iron)

    bm, uv = new_bmesh_with_uv()
    lathe(bm, uv, [(0.0, 0.03), (0.085, 0.03), (0.085, 0.27), (0.0, 0.27)], 4,
          Matrix.Translation(body_bottom) @ Matrix.Rotation(math.pi / 4, 4, "Z"))
    glass = mesh_object("Lantern Glass", bm, coll, mats.glass)
    glass.visible_shadow = False      # let the candle light pass through
    bm, uv = new_bmesh_with_uv()
    lathe(bm, uv, [(0.0, 0.03), (0.022, 0.03), (0.022, 0.11), (0.0, 0.11)], 16, Matrix.Translation(body_bottom))
    candle = mesh_object("Candle", bm, coll, mats.mushroom_stem)
    bm, uv = new_bmesh_with_uv()
    lathe(bm, uv, [(0.0, 0.115), (0.007, 0.125), (0.009, 0.14), (0.005, 0.16), (0.0, 0.175)], 12,
          Matrix.Translation(body_bottom))
    flame = mesh_object("Candle Flame", bm, coll, mats.flame)
    flame.visible_shadow = False
    point_light("Lantern Light", coll, body_bottom + Vector((0, 0, 0.15)), (1.0, 0.6, 0.25), 40.0, 0.03)
    return wood, iron, glass, candle, flame


def sword_in_stone(coll, blockers, terrain, mats, seed=151):
    x, y = config.SWORD_STONE
    bm = bmesh.new()
    rock(bm, 0.8, seed, subdivisions=6, squash=0.6, roughness=0.3, flat_cuts=3)
    stone = mesh_object("Sword Stone", bm, coll, mats.boulder)
    stone.location = terrain.point(x, y, -0.15)
    bpy.context.view_layer.update()
    add_blocker(stone, blockers)

    top = stone.location + Vector((0.05, 0.02, 1.0))   # guard ~0.5 m above the stone
    frame = Matrix.Translation(top) @ Matrix.Rotation(0.12, 4, "X") @ Matrix.Rotation(0.5, 4, "Z")
    length = 0.95

    # Blade: diamond cross-section, tip buried in the stone, rising to the guard.
    bm, uv = new_bmesh_with_uv()
    rows = []
    for i in range(21):
        t = i / 20                      # 0 at the guard, 1 at the (buried) tip
        z = -length * t
        half_w = 0.032 * (1 - t ** 3) + 0.001
        ridge = 0.0045 * (1 - 0.6 * t) + 0.001
        rows.append([bm.verts.new(frame @ Vector(v)) for v in
                     ((-half_w, 0, z), (0, ridge, z), (half_w, 0, z), (0, -ridge, z))])
    for i in range(20):
        for k in range(4):
            k2 = (k + 1) % 4
            bm.faces.new((rows[i][k], rows[i][k2], rows[i + 1][k2], rows[i + 1][k]))
    blade = mesh_object("Sword Blade", bm, coll, mats.steel, smooth=False)

    bm, uv = new_bmesh_with_uv()
    guard = [frame @ Vector((0.13 * (i / 6 - 0.5) * 2, 0, 0.012 + 0.02 * ((i / 6 - 0.5) * 2) ** 2))
             for i in range(7)]
    sweep_tube(bm, guard, [0.013] * 7, 10, uv_layer=uv)
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=0.03, matrix=frame @ Matrix.Translation((0, 0, 0.23)))
    hilt = mesh_object("Sword Hilt", bm, coll, mats.gold)
    bm, uv = new_bmesh_with_uv()
    sweep_tube(bm, [frame @ Vector((0, 0, 0.02)), frame @ Vector((0, 0, 0.205))], [0.017, 0.016], 12,
               uv_layer=uv, v_scale=20.0)
    grip = mesh_object("Sword Grip", bm, coll, mats.leather)
    return stone, blade, hilt, grip


def potions(coll, terrain, mats, seed=171):
    rng = random.Random(seed)
    x, y = config.CHEST
    flask = [(0.0, 0.0), (0.035, 0.002), (0.055, 0.03), (0.058, 0.06), (0.045, 0.1), (0.016, 0.125),
             (0.014, 0.17), (0.018, 0.175)]
    liquid = [(0.0, 0.004), (0.031, 0.006), (0.05, 0.03), (0.052, 0.058), (0.0, 0.058)]
    cork = [(0.0, 0.165), (0.013, 0.165), (0.015, 0.2), (0.0, 0.2)]
    for i, (dx, dy, mat) in enumerate(((-0.75, -0.2, mats.potion_red), (-0.62, 0.05, mats.potion_blue),
                                       (-0.85, 0.12, mats.potion_green))):
        frame = Matrix.Translation(terrain.point(x + dx, y + dy, -0.005)) @ Matrix.Rotation(rng.uniform(0, 6.3), 4, "Z")
        for part, profile, material, close in (("Flask", flask, mats.glass, False),
                                               ("Liquid", liquid, mat, True),
                                               ("Cork", cork, mats.cut_wood, True)):
            bm, uv = new_bmesh_with_uv()
            lathe(bm, uv, profile, 24, frame, close_top=close)
            mesh_object(f"Potion {i} {part}", bm, coll, material)


def build(coll, blockers, terrain, mats):
    chest(coll, blockers, terrain, mats)
    potions(coll, terrain, mats)
    lantern_post(coll, blockers, terrain, mats)
    sword_in_stone(coll, blockers, terrain, mats)
