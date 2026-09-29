"""Trees. Sapling Tree Gen grows the branch skeleton and leaf placement; every
branch is then rebuilt as a high-poly bark mesh (metric UVs, bark ridges,
buttress roots) and Sapling's leaves become oriented leaf-twig instances."""
import ast
import math
import random
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, noise
from mathutils.geometry import interpolate_bezier

from . import config
from .util import (add_blocker, assert_links_valid, collection, link, mesh_data, mesh_object,
                   move_to_collection, new_bmesh_with_uv, node, set_input, sweep_tube)

SAPLING_PRESETS = Path(bpy.utils.user_resource("EXTENSIONS")) / "blender_org" / "sapling_tree_gen" / "presets"

SPECIES = {
    # Broad, mossy oak-like trees.
    "Oak": ("small_maple", dict(scale=15.0, scaleV=3.0, ratio=0.03, ratioPower=1.25,
                                branches=(0, 70, 16, 10), baseSize=0.33, baseSplits=1,
                                leaves=26, leafScale=0.2, curveV=(25.0, 40.0, 40.0, 0.0),
                                attractUp=(-0.3, -0.5, 0.0, 0.0))),
    # Tall, slender canopy trees.
    "Beech": ("white_birch", dict(scale=19.0, scaleV=3.0, ratio=0.022, ratioPower=1.35,
                                  branches=(0, 55, 22, 10), baseSize=0.45, leaves=22,
                                  leafScale=0.2)),
}

HERO = ("japanese_maple", dict(levels=3, scale=17.0, scaleV=0.0, ratio=0.065, ratioPower=1.3,
                               branches=(0, 40, 14, 10), length=(1.0, 0.42, 0.5, 0.3),
                               curveV=(250.0, 120.0, 80.0, 0.0), baseSize=0.3, baseSplits=2,
                               segSplits=(0.3, 0.35, 0.4, 0.0), splitAngle=(25.0, 20.0, 25.0, 0.0),
                               rootFlare=1.6, leaves=28, leafScale=0.2))


def sapling_params(preset, overrides, seed):
    params = ast.literal_eval((SAPLING_PRESETS / f"{preset}.py").read_text().split("\n", 3)[-1])
    params.update(overrides)
    params.update(seed=seed, bevel=True, showLeaves=True, leafShape="rect", useArm=False,
                  makeMesh=False, prune=False)
    return params


def grow_skeleton(preset, overrides, seed):
    """Run Sapling, return ([(points, radii)], [(base, rotation quaternion)])."""
    before = set(bpy.data.objects)
    result = bpy.ops.curve.tree_add(**sapling_params(preset, overrides, seed))
    if result != {"FINISHED"}:
        raise RuntimeError(f"Sapling tree_add failed: {result}")
    created = [o for o in bpy.data.objects if o not in before]
    curve_obj = next(o for o in created if o.type == "CURVE")
    leaf_obj = next(o for o in created if o.type == "MESH")

    branches = []
    to_world = curve_obj.matrix_world
    for spline in curve_obj.data.splines:
        bp = spline.bezier_points
        points, radii = [], []
        for i in range(len(bp) - 1):
            steps = max(2, int((bp[i + 1].co - bp[i].co).length / 0.08))
            seg = interpolate_bezier(bp[i].co, bp[i].handle_right, bp[i + 1].handle_left, bp[i + 1].co, steps + 1)
            for k, p in enumerate(seg[:-1]):
                points.append(to_world @ p)
                radii.append(bp[i].radius + (bp[i + 1].radius - bp[i].radius) * k / steps)
        points.append(to_world @ bp[-1].co)
        radii.append(bp[-1].radius)
        if len(points) > 1:
            branches.append((points, radii))

    leaves = leaf_frames(leaf_obj)
    for obj in created:
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Curve):
            bpy.data.curves.remove(data)
        elif isinstance(data, bpy.types.Mesh):
            bpy.data.meshes.remove(data)
    return branches, leaves


def leaf_frames(leaf_obj):
    """Sapling 'rect' leaves are quads (0.5,0,0) (0.5,0,1) (-0.5,0,1) (-0.5,0,0) in
    leaf space: base at z=0, tip at z=1, width along x."""
    mw = leaf_obj.matrix_world
    verts = leaf_obj.data.vertices
    frames = []
    for poly in leaf_obj.data.polygons:
        v0, v1, v2, v3 = (mw @ verts[i].co for i in poly.vertices)
        base, tip = (v0 + v3) / 2, (v1 + v2) / 2
        axis = tip - base
        if axis.length < 1e-6:
            continue
        axis.normalize()
        normal = (v0 - v3).cross(axis).normalized()
        if normal.z < 0:
            normal = -normal
        x_axis = axis.cross(normal).normalized()
        rot = Matrix((x_axis, axis, normal)).transposed().to_quaternion()
        frames.append((base, rot))
    return frames


def resample(points, radii, spacing):
    """Uniform arc-length resampling of a polyline and its radii."""
    pts = np.array([tuple(p) for p in points])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    count = max(2, int(math.ceil(arc[-1] / spacing)) + 1)
    targets = np.linspace(0.0, arc[-1], count)
    out = np.stack([np.interp(targets, arc, pts[:, k]) for k in range(3)], axis=1)
    return [Vector(p) for p in out], list(np.interp(targets, arc, radii))


def trunk_relief(base_z, flare, lobes, seed):
    """Radial multiplier: buttress roots near the ground plus bark ridges."""
    phase = random.Random(seed).uniform(0, math.tau)

    def relief(point, angle):
        h = max(0.0, point.z - base_z)
        wobble = 0.35 * noise.noise(Vector((math.cos(angle), math.sin(angle), seed * 0.37)))
        buttress = flare * max(0.0, math.cos(lobes * angle + phase + wobble)) ** 3 * math.exp(-h / 1.1)
        ridges = 0.045 * noise.noise(Vector((math.cos(angle) * 6, math.sin(angle) * 6, point.z * 1.2 + seed)))
        return 1.0 + buttress + ridges
    return relief


def branch_relief(seed):
    def relief(point, angle):
        return 1.0 + 0.05 * noise.noise(Vector((math.cos(angle) * 4, math.sin(angle) * 4,
                                                (point.x + point.y + point.z) * 2 + seed)))
    return relief


def add_base_moss(bm, ground_z, fade=1.8, strength=1.0):
    """'base_moss' point attribute: 1 at ground level fading to 0 at fade metres.
    ground_z is a callable (x, y) -> ground height."""
    layer = bm.verts.layers.float.new("base_moss")
    for v in bm.verts:
        h = v.co.z - ground_z(v.co.x, v.co.y)
        v[layer] = strength * max(0.0, min(1.0, 1.0 - h / fade)) ** 1.5


def bark_mesh(name, coll, material, branches, seed, flare=0.35, lobes=5, sink=0.5):
    bm, uv = new_bmesh_with_uv()
    trunk_index = max(range(len(branches)), key=lambda i: branches[i][1][0])
    ground = branches[trunk_index][0][0].z
    for i, (points, radii) in enumerate(branches):
        r0 = radii[0]
        if i == trunk_index:
            points = [points[0] - Vector((0, 0, sink))] + list(points)
            radii = [radii[0]] + list(radii)
            points, radii = resample(points, radii, 0.08)
            relief = trunk_relief(points[0].z + sink, flare, lobes, seed)
        else:
            points, radii = resample(points, radii, min(0.35, max(0.04, r0 * 4)))
            relief = branch_relief(seed + i) if r0 > 0.04 else None
        segments = int(min(36, max(4, 6 + r0 * 80)))
        sweep_tube(bm, points, radii, segments, uv_layer=uv, noise=relief,
                   u_scale=max(1, round(2 * math.pi * r0)))
    add_base_moss(bm, lambda x, y: ground)
    return mesh_object(name, bm, coll, material)


def leaf_instancer_group(leaf_sprays):
    """Geometry Nodes: instance a random leaf spray on each vertex using the
    'leaf_rot' (quaternion) and 'leaf_scale' point attributes."""
    name = "Leaf Instancer"
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    geo_in = ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    geo_out = ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin = node(ng, "NodeGroupInput", "Inputs", (-800, 0))
    gout = node(ng, "NodeGroupOutput", "Output", (800, 0))

    rot = node(ng, "GeometryNodeInputNamedAttribute", "leaf_rot", (-600, -200), data_type="QUATERNION")
    set_input(rot, "Name", "leaf_rot")
    scale = node(ng, "GeometryNodeInputNamedAttribute", "leaf_scale", (-600, -400), data_type="FLOAT")
    set_input(scale, "Name", "leaf_scale")
    sprays = node(ng, "GeometryNodeCollectionInfo", "Leaf sprays", (-600, 300), transform_space="ORIGINAL")
    sprays.inputs["Collection"].default_value = leaf_sprays
    set_input(sprays, "Separate Children", True)
    set_input(sprays, "Reset Children", True)
    pick = node(ng, "FunctionNodeRandomValue", "Random spray", (-300, 300), data_type="INT")
    set_input(pick, "Max", len(leaf_sprays.objects) - 1)

    place = node(ng, "GeometryNodeInstanceOnPoints", "Instance", (0, 0))
    link(ng, gin, geo_in.identifier, place, "Points")
    link(ng, sprays, "Instances", place, "Instance")
    set_input(place, "Pick Instance", True)
    link(ng, pick, "Value", place, "Instance Index")
    link(ng, rot, "Attribute", place, "Rotation")
    link(ng, scale, "Attribute", place, "Scale")

    rand = node(ng, "FunctionNodeRandomValue", "Instance random", (200, -300), data_type="FLOAT")
    store = node(ng, "GeometryNodeStoreNamedAttribute", "Store rand", (400, 0), data_type="FLOAT",
                 domain="INSTANCE")
    set_input(store, "Name", "rand")
    link(ng, place, "Instances", store, "Geometry")
    link(ng, rand, "Value", store, "Value")
    link(ng, store, "Geometry", gout, geo_out.identifier)
    assert_links_valid(ng)
    return ng


def leaf_host(name, coll, frames, leaf_sprays, seed, scale=(0.9, 1.4)):
    """Vertex-only mesh carrying leaf frames, instanced by 'Leaf Instancer'."""
    rng = random.Random(seed)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(frames))
    mesh.vertices.foreach_set("co", [c for base, _ in frames for c in base])
    rot = mesh.attributes.new("leaf_rot", "QUATERNION", "POINT")
    rot.data.foreach_set("value", [c for _, q in frames for c in q])
    size = mesh.attributes.new("leaf_scale", "FLOAT", "POINT")
    size.data.foreach_set("value", [rng.uniform(*scale) for _ in frames])
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    modifier = obj.modifiers.new("Leaves", "NODES")
    modifier.node_group = leaf_instancer_group(leaf_sprays)
    return obj


def build_variants(mats, assets, root, per_species=2):
    """Tree variant collections (bark + leaves) for collection instancing."""
    variants = []
    for species, (preset, overrides) in SPECIES.items():
        for i in range(per_species):
            seed = 11 + 7 * i + len(species)
            coll = collection(f"Tree {species} {i}", parent=root)
            branches, leaves = grow_skeleton(preset, overrides, seed)
            bark = bark_mesh(f"{species} {i} Bark", coll, mats.tree_bark, branches, seed)
            leaf_host(f"{species} {i} Leaves", coll, leaves, assets.leaf_sprays, seed)
            trunk_radius = max(radii[0] for _, radii in branches)
            variants.append((coll, trunk_radius))
            print(f"[trees] {coll.name}: {len(branches)} branches, {len(leaves)} leaf sprays, "
                  f"{len(bark.data.polygons)} bark faces, trunk r={trunk_radius:.2f}")
    return variants


def surface_roots(name, coll, material, terrain, centre, trunk_radius, count, seed):
    """Roots that leave the trunk base and snake over the ground before sinking."""
    rng = random.Random(seed)
    bm, uv = new_bmesh_with_uv()
    for k in range(count):
        angle = math.tau * (k + rng.uniform(-0.25, 0.25)) / count
        heading = Vector((math.cos(angle), math.sin(angle), 0))
        side = Vector((-heading.y, heading.x, 0))
        length = rng.uniform(3.0, 6.5)
        r_start = trunk_radius * rng.uniform(0.2, 0.32)
        points, radii = [], []
        for i in range(40):
            t = i / 39
            dist = trunk_radius * 0.8 + length * t
            p = centre + heading * dist + side * (0.5 * math.sin(t * 5 + k) * t)
            radius = r_start * (1 - t) ** 1.2 + 0.02
            ground = terrain.height(p.x, p.y)
            # Rise out of the trunk, hug the surface, then dive under it.
            p.z = ground + radius * (0.5 - 1.3 * max(0.0, t - 0.75)) + 0.6 * max(0.0, 0.15 - t)
            points.append(p)
            radii.append(radius)
        sweep_tube(bm, points, radii, 16, uv_layer=uv, noise=branch_relief(seed + k),
                   u_scale=max(1, round(2 * math.pi * r_start)))
    add_base_moss(bm, terrain.height, fade=0.6, strength=0.8)
    return mesh_object(name, bm, coll, material)


def grow_ivy(trunk, start, seed, length=7.0):
    """Run the IvyGen add-on on the trunk mesh from a point on its surface."""
    props = bpy.context.window_manager.ivy_gen_props
    props.randomSeed = seed
    props.maxIvyLength = length
    props.ivySize = 0.03
    props.maxFloatLength = 0.4
    props.maxAdhesionDistance = 0.8
    props.primaryWeight = 0.6
    props.randomWeight = 0.3
    props.gravityWeight = 0.5
    props.adhesionWeight = 0.3
    props.branchingProbability = 0.08
    props.leafProbability = 0.55
    props.ivyLeafSize = 0.05
    props.ivyBranchSize = 0.0015
    props.growLeaves = True
    bpy.context.scene.cursor.location = start
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    trunk.select_set(True)
    bpy.context.view_layer.objects.active = trunk
    before = set(bpy.data.objects)
    result = bpy.ops.curve.ivy_gen(updateIvy=True)
    if result != {"FINISHED"}:
        raise RuntimeError(f"IvyGen failed: {result}")
    return [o for o in bpy.data.objects if o not in before]


def hero_tree(coll, blockers, terrain, mats, assets, seed=5):
    hx, hy = config.HERO_TREE
    base = terrain.point(hx, hy, -0.15)
    branches, leaves = grow_skeleton(*HERO, seed=seed)
    trunk_radius = max(radii[0] for _, radii in branches)
    placement = Matrix.Translation(base) @ Matrix.Rotation(2.4, 4, "Z")
    branches = [([placement @ p for p in pts], radii) for pts, radii in branches]
    leaves = [(placement @ b, (placement.to_quaternion() @ q)) for b, q in leaves]

    bark = bark_mesh("Ancient Tree", coll, mats.hero_bark, branches, seed, flare=0.9, lobes=6, sink=1.0)
    subdiv = bark.modifiers.new("Adaptive Subdivision", "SUBSURF")
    subdiv.levels = 0
    subdiv.use_adaptive_subdivision = True
    leaf_host("Ancient Tree Leaves", coll, leaves, assets.leaf_sprays, seed)
    roots = surface_roots("Ancient Tree Roots", coll, mats.hero_bark, terrain, base, trunk_radius, 9, seed)

    toward_path = Vector((config.CLEARING_CENTER[0] - hx, config.CLEARING_CENTER[1] - hy, 0)).normalized()
    ivy_start = base + toward_path * (trunk_radius * 1.05) + Vector((0, 0, 0.6))
    for obj in grow_ivy(bark, ivy_start, seed):
        if obj.type == "CURVE":
            obj.data.materials.clear()
            obj.data.materials.append(mats.log_bark)
        else:
            obj.data.materials.clear()
            obj.data.materials.append(mats.ivy)
        obj.name = f"Ancient Tree Ivy {obj.type.title()}"
        move_to_collection(obj, coll)

    bpy.context.view_layer.update()
    add_blocker(bark, blockers)
    add_blocker(roots, blockers)
    print(f"[trees] hero: {len(branches)} branches, {len(leaves)} leaf sprays, "
          f"{len(bark.data.polygons)} bark faces, trunk r={trunk_radius:.2f}")
    return bark


def plant_forest(coll, blockers, terrain, variants, keep_clear, seed=17):
    """Poisson-disk forest of collection instances, clear of paths and landmarks."""
    rng = random.Random(seed)
    half = config.TERRAIN_SIZE / 2 - 1.0
    spacing = config.TREE_MIN_SPACING
    cx, cy = config.CLEARING_CENTER
    cell = spacing / math.sqrt(2)
    grid = {}
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=1.0, radius2=1.0, depth=4.0)
    trunk_proxy = mesh_data("Trunk Proxy", bm, smooth=False)

    planted = 0
    for _ in range(8000):
        x, y = rng.uniform(-half, half), rng.uniform(-half, half)
        if terrain.path_distance(x, y) < config.TREE_PATH_CLEARANCE:
            continue
        if math.hypot(x - cx, y - cy) < config.CLEARING_RADIUS + 1.5:
            continue
        if any(math.hypot(x - kx, y - ky) < kr for kx, ky, kr in keep_clear):
            continue
        gx, gy = int((x + half) / cell), int((y + half) / cell)
        neighbours = (grid.get((gx + i, gy + j)) for i in range(-2, 3) for j in range(-2, 3))
        if any(n and math.hypot(x - n[0], y - n[1]) < spacing for n in neighbours):
            continue
        grid[(gx, gy)] = (x, y)

        variant, trunk_radius = rng.choice(variants)
        scale = rng.uniform(0.85, 1.2)
        tree = bpy.data.objects.new(f"Tree {planted:03d}", None)
        tree.instance_type = "COLLECTION"
        tree.instance_collection = variant
        tree.location = terrain.point(x, y, -0.1)
        tree.rotation_euler.z = rng.uniform(0, math.tau)
        tree.scale = (scale,) * 3
        coll.objects.link(tree)

        proxy = bpy.data.objects.new(f"Tree {planted:03d} Blocker", trunk_proxy)
        proxy.location = tree.location
        proxy.scale = (trunk_radius * scale * 1.6,) * 2 + (1.0,)
        blockers.objects.link(proxy)
        planted += 1
    print(f"[trees] planted {planted} forest trees")
