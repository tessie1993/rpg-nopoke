"""Geometry Nodes scatter system: instances a collection over the terrain,
steered by the terrain's path/clearing/detail masks, a noise patch mask and blockers."""
import bpy

from .util import assert_links_valid, link, node, set_input, socket

GROUP_NAME = "Forest Scatter"

# (name, socket type, default, min, max)
INPUTS = (
    ("Surface", "NodeSocketObject", None, None, None),
    ("Instances", "NodeSocketCollection", None, None, None),
    ("Blockers", "NodeSocketCollection", None, None, None),
    ("Density", "NodeSocketFloat", 1.0, 0.0, 10000.0),
    ("Seed", "NodeSocketInt", 0, 0, 100000),
    ("Scale Min", "NodeSocketFloat", 0.8, 0.0, 100.0),
    ("Scale Max", "NodeSocketFloat", 1.2, 0.0, 100.0),
    ("Off Path", "NodeSocketFloat", 1.0, 0.0, 1.0),
    ("On Path", "NodeSocketFloat", 0.0, 0.0, 1.0),
    ("Out Clearing", "NodeSocketFloat", 1.0, 0.0, 1.0),
    ("In Clearing", "NodeSocketFloat", 1.0, 0.0, 1.0),
    ("Patch Scale", "NodeSocketFloat", 0.15, 0.0, 100.0),
    ("Patch Coverage", "NodeSocketFloat", 1.0, 0.0, 1.0),
    ("Normal Align", "NodeSocketFloat", 0.3, 0.0, 1.0),
    ("Max Tilt", "NodeSocketFloat", 0.12, 0.0, 3.2),
    ("Sink", "NodeSocketFloat", 0.0, -10.0, 10.0),
    ("Block Radius", "NodeSocketFloat", 0.4, 0.0, 100.0),
)


def node_group():
    existing = bpy.data.node_groups.get(GROUP_NAME)
    if existing:
        return existing
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    geometry_out = ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, kind, default, lo, hi in INPUTS:
        item = ng.interface.new_socket(name=name, in_out="INPUT", socket_type=kind)
        if default is not None:
            item.default_value = default
            item.min_value, item.max_value = lo, hi

    gin = node(ng, "NodeGroupInput", "Inputs", (-2200, 0))
    gout = node(ng, "NodeGroupOutput", "Output", (1600, 0))

    def inp(name):
        return next(s for s in gin.outputs if s.name == name)

    def math_op(op, a, b, x, y, clamp=False):
        m = node(ng, "ShaderNodeMath", None, (x, y), operation=op, use_clamp=clamp)
        for ident, value in (("Value", a), ("Value_001", b)):
            if isinstance(value, bpy.types.NodeSocket):
                ng.links.new(value, socket(m, ident))
            else:
                set_input(m, ident, value)
        return socket(m, "Value", output=True)

    def lerp_mask(mask, outside, inside, x, y):
        """outside * (1 - mask) + inside * mask"""
        delta = math_op("SUBTRACT", inside, outside, x, y)
        m = node(ng, "ShaderNodeMath", None, (x + 180, y), operation="MULTIPLY_ADD")
        ng.links.new(mask, socket(m, "Value"))
        ng.links.new(delta, socket(m, "Value_001"))
        ng.links.new(outside, socket(m, "Value_002"))
        return socket(m, "Value", output=True)

    surface = node(ng, "GeometryNodeObjectInfo", "Surface", (-1900, 400), transform_space="RELATIVE")
    ng.links.new(inp("Surface"), socket(surface, "Object"))

    # Density factor: path term * clearing term * patch term.
    path_attr = node(ng, "GeometryNodeInputNamedAttribute", "path_mask", (-1900, -100), data_type="FLOAT")
    set_input(path_attr, "Name", "path_mask")
    clear_attr = node(ng, "GeometryNodeInputNamedAttribute", "clearing_mask", (-1900, -300), data_type="FLOAT")
    set_input(clear_attr, "Name", "clearing_mask")
    path_term = lerp_mask(socket(path_attr, "Attribute", output=True), inp("Off Path"), inp("On Path"), -1600, -100)
    clear_term = lerp_mask(socket(clear_attr, "Attribute", output=True), inp("Out Clearing"), inp("In Clearing"), -1600, -300)

    position = node(ng, "GeometryNodeInputPosition", None, (-1900, -500))
    patch_noise = node(ng, "ShaderNodeTexNoise", "Patch noise", (-1700, -500))
    set_input(patch_noise, "Detail", 3.0)
    link(ng, position, "Position", patch_noise, "Vector")
    ng.links.new(inp("Patch Scale"), socket(patch_noise, "Scale"))
    # threshold = 0.72 - 0.44 * coverage; ramp +-0.05 around it.
    threshold = node(ng, "ShaderNodeMath", None, (-1700, -750), operation="MULTIPLY_ADD")
    ng.links.new(inp("Patch Coverage"), socket(threshold, "Value"))
    set_input(threshold, "Value_001", -0.44)
    set_input(threshold, "Value_002", 0.72)
    thr = socket(threshold, "Value", output=True)
    patch = node(ng, "ShaderNodeMapRange", "Patch ramp", (-1450, -550), interpolation_type="SMOOTHSTEP")
    link(ng, patch_noise, "Fac", patch, "Value")
    ng.links.new(math_op("SUBTRACT", thr, 0.05, -1500, -800), socket(patch, "From Min"))
    ng.links.new(math_op("ADD", thr, 0.05, -1500, -950), socket(patch, "From Max"))

    detail_attr = node(ng, "GeometryNodeInputNamedAttribute", "detail", (-1900, -1100), data_type="FLOAT")
    set_input(detail_attr, "Name", "detail")

    factor = math_op("MULTIPLY", path_term, clear_term, -1200, -200)
    factor = math_op("MULTIPLY", factor, socket(patch, "Result", output=True), -1050, -300)
    factor = math_op("MULTIPLY", factor, socket(detail_attr, "Attribute", output=True), -1050, -450)

    distribute = node(ng, "GeometryNodeDistributePointsOnFaces", "Distribute", (-900, 300),
                      distribute_method="RANDOM")
    link(ng, surface, "Geometry", distribute, "Mesh")
    # In RANDOM mode the Density socket itself is the per-face field.
    ng.links.new(math_op("MULTIPLY", inp("Density"), factor, -900, 0), socket(distribute, "Density"))
    ng.links.new(inp("Seed"), socket(distribute, "Seed"))

    # Remove points too close to blockers (rocks, trunks, props).
    blockers = node(ng, "GeometryNodeCollectionInfo", "Blockers", (-900, -300), transform_space="RELATIVE")
    ng.links.new(inp("Blockers"), socket(blockers, "Collection"))
    realize = node(ng, "GeometryNodeRealizeInstances", None, (-700, -300))
    link(ng, blockers, "Instances", realize, "Geometry")
    proximity = node(ng, "GeometryNodeProximity", "Blocker distance", (-500, -300), target_element="FACES")
    link(ng, realize, "Geometry", proximity, "Target")
    near = math_op("LESS_THAN", socket(proximity, "Distance", output=True), inp("Block Radius"), -300, -300)
    blocked = node(ng, "FunctionNodeBooleanMath", None, (-150, -300), operation="AND")
    link(ng, proximity, "Is Valid", blocked, "Boolean")
    ng.links.new(near, socket(blocked, "Boolean_001"))
    cull = node(ng, "GeometryNodeDeleteGeometry", "Cull blocked", (0, 300), domain="POINT")
    link(ng, distribute, "Points", cull, "Geometry")
    link(ng, blocked, "Boolean", cull, "Selection")

    sink = node(ng, "ShaderNodeCombineXYZ", None, (0, 0))
    ng.links.new(math_op("MULTIPLY", inp("Sink"), -1.0, -150, 0), socket(sink, "Z"))
    lower = node(ng, "GeometryNodeSetPosition", "Sink", (200, 300))
    link(ng, cull, "Geometry", lower, "Geometry")
    link(ng, sink, "Vector", lower, "Offset")

    # Rotation: partially align to the surface normal, then random tilt + yaw.
    align = node(ng, "FunctionNodeAlignRotationToVector", "Align to normal", (200, -100), axis="Z")
    ng.links.new(inp("Normal Align"), socket(align, "Factor"))
    link(ng, distribute, "Normal", align, "Vector")
    tilt_neg = math_op("MULTIPLY", inp("Max Tilt"), -1.0, 0, -400)
    euler_min = node(ng, "ShaderNodeCombineXYZ", None, (150, -400))
    ng.links.new(tilt_neg, socket(euler_min, "X"))
    ng.links.new(tilt_neg, socket(euler_min, "Y"))
    euler_max = node(ng, "ShaderNodeCombineXYZ", None, (150, -550))
    ng.links.new(inp("Max Tilt"), socket(euler_max, "X"))
    ng.links.new(inp("Max Tilt"), socket(euler_max, "Y"))
    set_input(euler_max, "Z", 6.2832)
    rand_euler = node(ng, "FunctionNodeRandomValue", "Random tilt/yaw", (350, -450), data_type="FLOAT_VECTOR")
    link(ng, euler_min, "Vector", rand_euler, "Min")
    link(ng, euler_max, "Vector", rand_euler, "Max")
    ng.links.new(math_op("ADD", inp("Seed"), 11, 200, -700), socket(rand_euler, "Seed"))
    to_rot = node(ng, "FunctionNodeEulerToRotation", None, (550, -450))
    link(ng, rand_euler, "Value", to_rot, "Euler")
    rotate = node(ng, "FunctionNodeRotateRotation", None, (750, -200), rotation_space="LOCAL")
    link(ng, align, "Rotation", rotate, "Rotation")
    link(ng, to_rot, "Rotation", rotate, "Rotate By")

    rand_scale = node(ng, "FunctionNodeRandomValue", "Random scale", (750, -500), data_type="FLOAT")
    ng.links.new(inp("Scale Min"), socket(rand_scale, "Min"))
    ng.links.new(inp("Scale Max"), socket(rand_scale, "Max"))
    ng.links.new(math_op("ADD", inp("Seed"), 23, 550, -700), socket(rand_scale, "Seed"))

    # Pick a random child object of the instance collection.
    instances = node(ng, "GeometryNodeCollectionInfo", "Instance collection", (400, 600), transform_space="ORIGINAL")
    ng.links.new(inp("Instances"), socket(instances, "Collection"))
    set_input(instances, "Separate Children", True)
    set_input(instances, "Reset Children", True)
    count = node(ng, "GeometryNodeAttributeDomainSize", None, (600, 800), component="INSTANCES")
    link(ng, instances, "Instances", count, "Geometry")
    rand_index = node(ng, "FunctionNodeRandomValue", "Random pick", (800, 800), data_type="INT")
    ng.links.new(math_op("SUBTRACT", socket(count, "Instance Count", output=True), 1, 700, 950), socket(rand_index, "Max"))
    ng.links.new(math_op("ADD", inp("Seed"), 37, 700, 1100), socket(rand_index, "Seed"))

    place = node(ng, "GeometryNodeInstanceOnPoints", "Instance", (1000, 300))
    link(ng, lower, "Geometry", place, "Points")
    link(ng, instances, "Instances", place, "Instance")
    set_input(place, "Pick Instance", True)
    link(ng, rand_index, "Value", place, "Instance Index")
    link(ng, rotate, "Rotation", place, "Rotation")
    link(ng, rand_scale, "Value", place, "Scale")

    # Per-instance random value for shader variation (Attribute node, Instancer).
    rand_attr = node(ng, "FunctionNodeRandomValue", "Instance random", (1100, -100), data_type="FLOAT")
    ng.links.new(math_op("ADD", inp("Seed"), 53, 950, -300), socket(rand_attr, "Seed"))
    store = node(ng, "GeometryNodeStoreNamedAttribute", "Store rand", (1300, 300),
                 data_type="FLOAT", domain="INSTANCE")
    set_input(store, "Name", "rand")
    link(ng, place, "Instances", store, "Geometry")
    link(ng, rand_attr, "Value", store, "Value")
    link(ng, store, "Geometry", gout, geometry_out.identifier)
    assert_links_valid(ng)
    return ng


def scatter(name, coll, surface, instances, blockers=None, **values):
    """Create an empty host object carrying the scatter modifier."""
    mesh = bpy.data.meshes.new(name)
    host = bpy.data.objects.new(name, mesh)
    coll.objects.link(host)
    group = node_group()
    modifier = host.modifiers.new("Scatter", "NODES")
    modifier.node_group = group
    settings = dict(values, Surface=surface, Instances=instances, Blockers=blockers)
    by_name = {item.name: item.identifier for item in group.interface.items_tree
               if item.item_type == "SOCKET" and item.in_out == "INPUT"}
    for key, value in settings.items():
        key = key.replace("_", " ")
        if key not in by_name:
            raise KeyError(f"Scatter input {key!r} not in {sorted(by_name)}")
        if value is not None:
            getattr(modifier.properties.inputs, by_name[key]).value = value
    return host
