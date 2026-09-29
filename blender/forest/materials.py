"""Node-based materials. Photo-scanned textures come from Poly Haven (CC0)."""
import math
from types import SimpleNamespace

import bpy

from . import config
from .util import assert_links_valid, link, node, set_input, socket

COLOR_MAPS = {"diff"}


def image(asset, map_name):
    path = config.TEXTURE_ROOT / asset / f"{map_name}.jpg"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run tools/fetch_textures.py first")
    img = bpy.data.images.load(str(path), check_existing=True)
    img.colorspace_settings.name = "sRGB" if map_name in COLOR_MAPS else "Non-Color"
    return img


def new_material(name):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", "Output", (900, 0))
    bsdf = node(nt, "ShaderNodeBsdfPrincipled", "BSDF", (500, 0))
    link(nt, bsdf, "BSDF", out, "Surface")
    return mat, nt, bsdf, out


def texture_set(nt, asset, vector, x, y, projection="FLAT", blend=0.0, maps=("diff", "rough", "nor_gl", "disp")):
    """Image nodes for one Poly Haven asset sharing a vector input."""
    sockets = {}
    for i, map_name in enumerate(maps):
        tex = node(nt, "ShaderNodeTexImage", f"{asset}:{map_name}", (x, y - i * 280),
                   image=image(asset, map_name), projection=projection, projection_blend=blend)
        nt.links.new(vector, socket(tex, "Vector"))
        sockets[map_name] = socket(tex, "Color", output=True)
    return sockets


def mapping(nt, coord_output, scale, x, y, rotation_z=0.0):
    coord = node(nt, "ShaderNodeTexCoord", None, (x - 400, y))
    mapper = node(nt, "ShaderNodeMapping", None, (x - 200, y))
    set_input(mapper, "Scale", scale)
    set_input(mapper, "Rotation", (0.0, 0.0, rotation_z))
    link(nt, coord, coord_output, mapper, "Vector")
    return socket(mapper, "Vector", output=True)


def mix(nt, factor, a, b, x, y, data_type="RGBA", blend="MIX"):
    """Mix node; returns its result socket for the chosen data type."""
    suffix = {"RGBA": "Color", "FLOAT": "Float", "VECTOR": "Vector"}[data_type]
    m = node(nt, "ShaderNodeMix", None, (x, y), data_type=data_type, blend_type=blend)
    for ident, value in (("Factor_Float", factor), (f"A_{suffix}", a), (f"B_{suffix}", b)):
        if isinstance(value, bpy.types.NodeSocket):
            nt.links.new(value, socket(m, ident))
        else:
            set_input(m, ident, value)
    return socket(m, f"Result_{suffix}", output=True)


def math_op(nt, op, a, b=None, x=0, y=0, clamp=False):
    m = node(nt, "ShaderNodeMath", None, (x, y), operation=op, use_clamp=clamp)
    for ident, value in (("Value", a), ("Value_001", b)):
        if value is None:
            continue
        if isinstance(value, bpy.types.NodeSocket):
            nt.links.new(value, socket(m, ident))
        else:
            set_input(m, ident, value)
    return socket(m, "Value", output=True)


def luminance(nt, color, x, y):
    sep = node(nt, "ShaderNodeRGBToBW", None, (x, y))
    nt.links.new(color, socket(sep, "Color"))
    return socket(sep, "Val", output=True)


def height_blend(nt, mask, h_bottom, h_top, contrast, x, y):
    """Blend factor that lets the higher surface win near the mask edge:
    clamp((mask + 0.9 * (h_top - h_bottom) - 0.5) * contrast + 0.5)."""
    diff = math_op(nt, "SUBTRACT", h_top, h_bottom, x, y)
    shifted = math_op(nt, "MULTIPLY_ADD", diff, 0.9, x + 160, y)
    nt.links.new(mask, socket(shifted.node, "Value_002"))
    centred = math_op(nt, "SUBTRACT", shifted, 0.5, x + 320, y)
    return _mul_add_clamped(nt, centred, contrast, 0.5, x + 480, y)


def _mul_add_clamped(nt, value, mul, add, x, y):
    m = node(nt, "ShaderNodeMath", None, (x, y), operation="MULTIPLY_ADD", use_clamp=True)
    nt.links.new(value, socket(m, "Value"))
    set_input(m, "Value_001", mul)
    set_input(m, "Value_002", add)
    return socket(m, "Value", output=True)


def attribute(nt, name, x, y, kind="GEOMETRY"):
    attr = node(nt, "ShaderNodeAttribute", None, (x, y), attribute_name=name, attribute_type=kind)
    return attr


def normal_map(nt, color, strength, x, y):
    nm = node(nt, "ShaderNodeNormalMap", None, (x, y))
    set_input(nm, "Strength", strength)
    nt.links.new(color, socket(nm, "Color"))
    return socket(nm, "Normal", output=True)


def displacement(nt, mat, out, height, scale, x, y, method="BOTH"):
    disp = node(nt, "ShaderNodeDisplacement", None, (x, y))
    set_input(disp, "Scale", scale)
    set_input(disp, "Midlevel", 0.5)
    nt.links.new(height, socket(disp, "Height"))
    link(nt, disp, "Displacement", out, "Displacement")
    mat.displacement_method = method


# --------------------------------------------------------------------------
# Terrain


def noise_mask(nt, scale, low, high, x, y, detail=3.0, w=0.0):
    """Object-space noise remapped so values in [low, high] ramp from 0 to 1."""
    coord = node(nt, "ShaderNodeTexCoord", None, (x - 400, y))
    tex = node(nt, "ShaderNodeTexNoise", None, (x - 200, y), noise_dimensions="4D")
    set_input(tex, "Scale", scale)
    set_input(tex, "Detail", detail)
    set_input(tex, "W", w)
    link(nt, coord, "Object", tex, "Vector")
    ramp = node(nt, "ShaderNodeMapRange", None, (x, y), interpolation_type="SMOOTHSTEP")
    link(nt, tex, "Fac", ramp, "Value")
    set_input(ramp, "From Min", low)
    set_input(ramp, "From Max", high)
    return socket(ramp, "Result", output=True)


def rotate_normal_map_90(nt, color, x, y):
    """Tangent-space normal colour for a texture sampled with a +90 degree
    Mapping rotation: (r, g, b) -> (g, 1 - r, b)."""
    sep = node(nt, "ShaderNodeSeparateColor", None, (x, y))
    nt.links.new(color, socket(sep, "Color"))
    flipped = math_op(nt, "SUBTRACT", 1.0, socket(sep, "Red", output=True), x + 180, y - 60)
    comb = node(nt, "ShaderNodeCombineColor", None, (x + 360, y))
    link(nt, sep, "Green", comb, "Red")
    nt.links.new(flipped, socket(comb, "Green"))
    link(nt, sep, "Blue", comb, "Blue")
    return socket(comb, "Color", output=True)


def anti_tiled_set(nt, asset, tile_m, x, y, seed):
    """Sample a ground scan twice - the second time at an incommensurate scale,
    offset and rotated 90 degrees - and blend by noise, so neither the tile
    period nor gradients baked into the scan line up into visible stripes."""
    size = config.TERRAIN_SIZE
    vec_a = mapping(nt, "UV", (size / tile_m, size / tile_m, 1), x - 100, y)
    scale_b = size / (tile_m * 1.61)
    vec_b = mapping(nt, "UV", (scale_b, scale_b, 1), x - 100, y - 1150, rotation_z=math.pi / 2)
    set_input(vec_b.node, "Location", (0.37 + seed, 0.71, 0.0))
    a = texture_set(nt, asset, vec_a, x, y)
    b = texture_set(nt, asset, vec_b, x, y - 1150)
    b["nor_gl"] = rotate_normal_map_90(nt, b["nor_gl"], x + 300, y - 1400)
    fac = noise_mask(nt, 0.22, 0.42, 0.58, x + 500, y - 600, w=seed)
    return {key: mix(nt, fac, a[key], b[key], x + 700, y - 150 * i)
            for i, key in enumerate(("diff", "rough", "nor_gl", "disp"))}


def terrain_material():
    mat, nt, bsdf, out = new_material("Forest Floor")
    # Tile sizes follow the real-world dimensions of each scan.
    base = anti_tiled_set(nt, "forest_leaves_02", 3.0, -2600, 2600, 0.0)
    var = anti_tiled_set(nt, "brown_mud_leaves_01", 1.3, -2600, 200, 1.3)
    path = anti_tiled_set(nt, "forest_ground_04", 2.4, -2600, -2200, 2.6)

    # Large-scale noise decides where damp, muddy ground replaces leaf litter.
    var_mask = noise_mask(nt, 0.09, 0.35, 0.75, -1200, 500, detail=4.0, w=4.0)
    var_h = luminance(nt, var["disp"], -800, 0)
    # The leaf-litter scan has a strong low-frequency height swing per tile;
    # compress it so displacement does not turn tiles into ridges.
    base_h = _mul_add_clamped(nt, luminance(nt, base["disp"], -1000, 1000), 0.4, 0.3, -800, 1000)
    var_fac = height_blend(nt, var_mask, base_h, var_h, 5.0, -400, 700)

    # The clearing floor is worn down: dirt patches show through the litter.
    path_attr = attribute(nt, "path_mask", -1200, -500)
    clearing_attr = attribute(nt, "clearing_mask", -1200, -800)
    trodden = math_op(nt, "MULTIPLY", socket(clearing_attr, "Fac", output=True),
                   noise_mask(nt, 0.35, 0.4, 0.65, -1000, -1000, w=7.0), -800, -800)
    worn = math_op(nt, "MAXIMUM", socket(path_attr, "Fac", output=True),
                math_op(nt, "MULTIPLY", trodden, 0.75, -650, -800), -500, -650)
    path_h = luminance(nt, path["disp"], -800, -900)
    ground_h = mix(nt, var_fac, base_h, var_h, -200, 300, "FLOAT")
    path_fac = height_blend(nt, worn, ground_h, path_h, 4.0, -400, -600)
    obj_coord = node(nt, "ShaderNodeTexCoord", None, (-1400, 1600))

    # Macro value variation breaks up visible texture repetition.
    macro = node(nt, "ShaderNodeTexNoise", "Macro variation", (-800, 1600))
    set_input(macro, "Scale", 0.03)
    set_input(macro, "Detail", 3.0)
    link(nt, obj_coord, "Object", macro, "Vector")
    macro_val = node(nt, "ShaderNodeMapRange", None, (-600, 1600))
    link(nt, macro, "Fac", macro_val, "Value")
    set_input(macro_val, "To Min", 0.75)
    set_input(macro_val, "To Max", 1.15)

    # Cushions of moss on undisturbed ground, never on the worn path.
    moss_patch = noise_mask(nt, 0.3, 0.52, 0.66, -1000, 2100, detail=6.0, w=9.0)
    untrodden = math_op(nt, "SUBTRACT", 1.0, path_fac, -800, 2000)
    moss_fac = math_op(nt, "MULTIPLY", moss_patch, untrodden, -650, 2000)
    moss_color = moss_color_ramp(nt, obj_coord, -800, 2300)

    color = mix(nt, var_fac, base["diff"], var["diff"], 0, 900)
    color = mix(nt, path_fac, color, path["diff"], 180, 900)
    color = mix(nt, moss_fac, color, moss_color, 270, 900)
    color = mix(nt, 1.0, color, socket(macro_val, "Result", output=True), 360, 900, blend="MULTIPLY")
    rough = mix(nt, var_fac, luminance(nt, base["rough"], -800, 1200), luminance(nt, var["rough"], -800, 200), 0, 600, "FLOAT")
    rough = mix(nt, path_fac, rough, luminance(nt, path["rough"], -800, -700), 180, 600, "FLOAT")
    rough = mix(nt, moss_fac, rough, 0.9, 270, 600, "FLOAT")
    nor = mix(nt, var_fac, base["nor_gl"], var["nor_gl"], 0, 300)
    nor = mix(nt, path_fac, nor, path["nor_gl"], 180, 300)
    height = mix(nt, path_fac, ground_h, path_h, 180, 0, "FLOAT")

    nt.links.new(color, socket(bsdf, "Base Color"))
    nt.links.new(rough, socket(bsdf, "Roughness"))
    nt.links.new(normal_map(nt, nor, 1.0, 360, 300), socket(bsdf, "Normal"))
    set_input(bsdf, "Specular IOR Level", 0.35)
    displacement(nt, mat, out, height, 0.05, 600, -300)
    return mat


# --------------------------------------------------------------------------
# Bark, wood, stone


def moss_color_ramp(nt, coord, x, y):
    """Mottled moss colour: deep green hollows to bright yellow-green tips."""
    tex = node(nt, "ShaderNodeTexNoise", "Moss mottling", (x, y), noise_dimensions="3D")
    set_input(tex, "Scale", 9.0)
    set_input(tex, "Detail", 10.0)
    set_input(tex, "Roughness", 0.7)
    link(nt, coord, "Object", tex, "Vector")
    ramp = node(nt, "ShaderNodeValToRGB", "Moss colour", (x + 200, y))
    link(nt, tex, "Fac", ramp, "Fac")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.02, 0.05, 0.008, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (0.2, 0.3, 0.035, 1)
    return socket(ramp, "Color", output=True)


def moss_overlay(nt, color, rough, x, y, amount=0.55):
    """Blend moss onto upward-facing surfaces and, via the optional 'base_moss'
    mesh attribute (1 at the ground, 0 higher up), onto trunk bases."""
    geo = node(nt, "ShaderNodeNewGeometry", None, (x, y + 400))
    sep = node(nt, "ShaderNodeSeparateXYZ", None, (x + 180, y + 400))
    link(nt, geo, "Normal", sep, "Vector")
    up = math_op(nt, "MULTIPLY_ADD", socket(sep, "Z", output=True), 1.4, x + 360, y + 400)
    socket(up.node, "Value_002").default_value = -0.35
    base = attribute(nt, "base_moss", x + 180, y + 600)
    grow_zone = math_op(nt, "MAXIMUM", up, socket(base, "Fac", output=True), x + 540, y + 500)
    coord = node(nt, "ShaderNodeTexCoord", None, (x, y + 200))
    moss_noise = node(nt, "ShaderNodeTexNoise", "Moss noise", (x + 180, y + 200))
    set_input(moss_noise, "Scale", 1.6)
    set_input(moss_noise, "Detail", 8.0)
    set_input(moss_noise, "Roughness", 0.65)
    link(nt, coord, "Object", moss_noise, "Vector")
    grow = math_op(nt, "MULTIPLY", grow_zone, socket(moss_noise, "Fac", output=True), x + 700, y + 300)
    fac = _mul_add_clamped(nt, grow, 3.0 * amount, -0.45, x + 860, y + 300)
    moss = moss_color_ramp(nt, coord, x + 360, y + 100)
    return (mix(nt, fac, color, moss, x + 1000, y + 100),
            mix(nt, fac, rough, 0.9, x + 1000, y - 100, "FLOAT"))


def bark_material(name, asset, scale_u, scale_v, moss=0.55, disp_scale=0.0, tint=None):
    """Bark on meshes with UVs: u wraps around the branch, v runs along it (metres)."""
    mat, nt, bsdf, out = new_material(name)
    vec = mapping(nt, "UV", (scale_u, scale_v, 1), -1100, 300)
    tex = texture_set(nt, asset, vec, -900, 500)
    color = tex["diff"]
    if tint:
        color = mix(nt, 1.0, color, tint, -600, 600, blend="MULTIPLY")
    rough = luminance(nt, tex["rough"], -600, 200)
    if moss:
        color, rough = moss_overlay(nt, color, rough, -600, -500, amount=moss)
    nt.links.new(color, socket(bsdf, "Base Color"))
    nt.links.new(rough, socket(bsdf, "Roughness"))
    nt.links.new(normal_map(nt, tex["nor_gl"], 1.2, 300, -300), socket(bsdf, "Normal"))
    set_input(bsdf, "Specular IOR Level", 0.3)
    if disp_scale:
        displacement(nt, mat, out, luminance(nt, tex["disp"], 300, -600), disp_scale, 600, -500)
    return mat


def box_projected(nt, asset, scale, maps):
    """Object-space box projection for meshes without meaningful UVs.
    scale is texture repeats per metre."""
    vec = mapping(nt, "Object", (scale, scale, scale), -1100, 300)
    return texture_set(nt, asset, vec, -900, 500, projection="BOX", blend=0.3, maps=maps)


def height_bump(nt, height, strength, distance, bsdf, x, y):
    """Bump from a height map (tangent-space normal maps do not suit box projection)."""
    bump = node(nt, "ShaderNodeBump", None, (x, y))
    set_input(bump, "Strength", strength)
    set_input(bump, "Distance", distance)
    nt.links.new(luminance(nt, height, x - 200, y), socket(bump, "Height"))
    link(nt, bump, "Normal", bsdf, "Normal")


def scan_material(name, asset, scale, moss=0.0, bump=0.6, bump_distance=0.02, specular=0.4):
    """Box-projected photo scan: stone, leather."""
    mat, nt, bsdf, out = new_material(name)
    tex = box_projected(nt, asset, scale, ("diff", "rough", "disp"))
    color, rough = tex["diff"], luminance(nt, tex["rough"], -600, 200)
    if moss:
        color, rough = moss_overlay(nt, color, rough, -600, -700, amount=moss)
    height_bump(nt, tex["disp"], bump, bump_distance, bsdf, 300, -300)
    nt.links.new(color, socket(bsdf, "Base Color"))
    nt.links.new(rough, socket(bsdf, "Roughness"))
    set_input(bsdf, "Specular IOR Level", specular)
    return mat


def metal_material(name, asset, scale, color=None, rough_range=(0.15, 0.4), bump=0.3):
    """Box-projected metal scan. Without color the scan's colour and metal mask
    are used (rusted iron); with color only its roughness and relief are kept,
    remapped to rough_range, as wear on polished metal."""
    mat, nt, bsdf, out = new_material(name)
    maps = ("rough", "disp") if color else ("diff", "rough", "metal", "disp")
    tex = box_projected(nt, asset, scale, maps)
    rough = luminance(nt, tex["rough"], -600, 200)
    if color:
        set_input(bsdf, "Base Color", (*color, 1))
        set_input(bsdf, "Metallic", 1.0)
        remap = node(nt, "ShaderNodeMapRange", None, (-400, 200))
        nt.links.new(rough, socket(remap, "Value"))
        set_input(remap, "To Min", rough_range[0])
        set_input(remap, "To Max", rough_range[1])
        rough = socket(remap, "Result", output=True)
    else:
        nt.links.new(tex["diff"], socket(bsdf, "Base Color"))
        nt.links.new(luminance(nt, tex["metal"], -600, 0), socket(bsdf, "Metallic"))
    nt.links.new(rough, socket(bsdf, "Roughness"))
    height_bump(nt, tex["disp"], bump, 0.003, bsdf, 300, -300)
    return mat


def wood_planks_material():
    mat, nt, bsdf, out = new_material("Chest Planks")
    vec = mapping(nt, "UV", (1.0, 1.0, 1), -1100, 300)
    tex = texture_set(nt, "rough_pine_door", vec, -900, 500)
    nt.links.new(tex["diff"], socket(bsdf, "Base Color"))
    nt.links.new(luminance(nt, tex["rough"], -500, 200), socket(bsdf, "Roughness"))
    nt.links.new(normal_map(nt, tex["nor_gl"], 1.0, 200, -300), socket(bsdf, "Normal"))
    return mat


def end_grain_material(name, base=(0.19, 0.12, 0.07)):
    """Sawn log ends and corks: distorted growth rings (no end-grain scan is
    available on Poly Haven)."""
    mat, nt, bsdf, out = new_material(name)
    coord = node(nt, "ShaderNodeTexCoord", None, (-1000, 0))
    wave = node(nt, "ShaderNodeTexWave", "Rings", (-800, 100), wave_type="RINGS")
    set_input(wave, "Scale", 6.0)
    set_input(wave, "Distortion", 6.0)
    set_input(wave, "Detail", 4.0)
    link(nt, coord, "Object", wave, "Vector")
    ramp = node(nt, "ShaderNodeValToRGB", None, (-550, 100))
    link(nt, wave, "Fac", ramp, "Fac")
    ramp.color_ramp.elements[0].color = (*[c * 0.55 for c in base], 1)
    ramp.color_ramp.elements[1].color = (*base, 1)
    link(nt, ramp, "Color", bsdf, "Base Color")
    set_input(bsdf, "Roughness", 0.8)
    bump = node(nt, "ShaderNodeBump", None, (200, -300))
    set_input(bump, "Strength", 0.3)
    set_input(bump, "Distance", 0.005)
    link(nt, wave, "Fac", bump, "Height")
    link(nt, bump, "Normal", bsdf, "Normal")
    return mat


# --------------------------------------------------------------------------
# Plants


def foliage_material(name, dark, light, translucency=0.35, uv_gradient=False, hue_jitter=0.04):
    """Leaves and grass: colour varies per instance (instancer attribute 'rand'),
    per leaf or blade (random per mesh island) and optionally along the blade."""
    mat, nt, bsdf, out = new_material(name)
    rand = attribute(nt, "rand", -1300, 300, kind="INSTANCER")
    geo = node(nt, "ShaderNodeNewGeometry", None, (-1300, 600))
    island = socket(geo, "Random Per Island", output=True)
    # Blend instance and island randomness so leaves within one spray differ.
    variation = mix(nt, 0.45, socket(rand, "Fac", output=True), island, -1100, 450, "FLOAT")
    ramp = node(nt, "ShaderNodeValToRGB", "Leaf colour", (-850, 300))
    nt.links.new(variation, socket(ramp, "Fac"))
    ramp.color_ramp.elements[0].color = (*dark, 1)
    ramp.color_ramp.elements[1].color = (*light, 1)
    color = socket(ramp, "Color", output=True)

    uv = node(nt, "ShaderNodeUVMap", None, (-1100, -100))
    sep = node(nt, "ShaderNodeSeparateXYZ", None, (-900, -100))
    link(nt, uv, "UV", sep, "Vector")
    if uv_gradient:
        grad = node(nt, "ShaderNodeValToRGB", "Base to tip", (-650, -100))
        link(nt, sep, "Y", grad, "Fac")
        grad.color_ramp.elements[0].color = (0.25, 0.22, 0.12, 1)
        grad.color_ramp.elements[1].color = (1.1, 1.08, 0.9, 1)
        grad.color_ramp.elements.new(0.3).color = (0.85, 0.85, 0.8, 1)
        color = mix(nt, 1.0, color, socket(grad, "Color", output=True), -400, 200, blend="MULTIPLY")
        # A quarter of the blades have straw-coloured, dried tips.
        tip = math_op(nt, "POWER", socket(sep, "Y", output=True), 3.0, -650, -300)
        dry = math_op(nt, "GREATER_THAN", island, 0.75, -650, -450)
        color = mix(nt, math_op(nt, "MULTIPLY", tip, dry, -500, -350), color, (0.42, 0.34, 0.14, 1), -300, 150)
    else:
        # Midrib: lighter stripe along the centre of the leaf (u = 0.5).
        centre = math_op(nt, "SUBTRACT", socket(sep, "X", output=True), 0.5, -700, -100)
        dist = math_op(nt, "ABSOLUTE", centre, None, -550, -100)
        rib = node(nt, "ShaderNodeMapRange", None, (-400, -100))
        nt.links.new(dist, socket(rib, "Value"))
        set_input(rib, "From Min", 0.0)
        set_input(rib, "From Max", 0.035)
        set_input(rib, "To Min", 0.35)
        set_input(rib, "To Max", 0.0)
        color = mix(nt, socket(rib, "Result", output=True), color, (0.75, 0.8, 0.45, 1), -200, 200)

    hue = node(nt, "ShaderNodeHueSaturation", None, (-200, 450))
    jitter = _mul_add_clamped(nt, socket(rand, "Fac", output=True), hue_jitter * 2, 0.5 - hue_jitter, -450, 500)
    nt.links.new(jitter, socket(hue, "Hue"))
    nt.links.new(color, socket(hue, "Color"))
    color = socket(hue, "Color", output=True)

    nt.links.new(color, socket(bsdf, "Base Color"))
    set_input(bsdf, "Roughness", 0.55)
    set_input(bsdf, "Specular IOR Level", 0.28)

    # Light through a leaf comes out warmer and more yellow than its surface.
    transmitted = mix(nt, 1.0, color, (1.5, 1.45, 0.55, 1), 300, -400, blend="MULTIPLY")
    translucent = node(nt, "ShaderNodeBsdfTranslucent", None, (500, -250))
    nt.links.new(transmitted, socket(translucent, "Color"))
    mix_shader = node(nt, "ShaderNodeMixShader", None, (700, 0))
    set_input(mix_shader, "Fac", translucency)
    link(nt, bsdf, "BSDF", mix_shader, "Shader")
    link(nt, translucent, "BSDF", mix_shader, "Shader_001")
    out_node = nt.nodes["Output"]
    nt.links.new(socket(mix_shader, "Shader", output=True), socket(out_node, "Surface"))
    return mat


def simple_material(name, color, roughness=0.5, metallic=0.0, subsurface=0.0, emission=None,
                    transmission=0.0, ior=1.45):
    mat, nt, bsdf, out = new_material(name)
    set_input(bsdf, "Base Color", (*color, 1))
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Metallic", metallic)
    set_input(bsdf, "Subsurface Weight", subsurface)
    set_input(bsdf, "Transmission Weight", transmission)
    set_input(bsdf, "IOR", ior)
    if emission:
        set_input(bsdf, "Emission Color", (*emission[0], 1))
        set_input(bsdf, "Emission Strength", emission[1])
    return mat


def spotted_cap_material(name, cap, spots, glow=None, spot_scale=70.0):
    """Mushroom cap: Voronoi spots on object coordinates, optional glow.
    spot_scale is cells per metre; caps are only 3-8 cm across."""
    mat, nt, bsdf, out = new_material(name)
    coord = node(nt, "ShaderNodeTexCoord", None, (-900, 0))
    vor = node(nt, "ShaderNodeTexVoronoi", "Spots", (-700, 0))
    set_input(vor, "Scale", spot_scale)
    set_input(vor, "Randomness", 0.8)
    link(nt, coord, "Object", vor, "Vector")
    spot = node(nt, "ShaderNodeMapRange", None, (-500, 0))
    link(nt, vor, "Distance", spot, "Value")
    set_input(spot, "From Min", 0.12)
    set_input(spot, "From Max", 0.18)
    set_input(spot, "To Min", 1.0)
    set_input(spot, "To Max", 0.0)
    fac = socket(spot, "Result", output=True)
    nt.links.new(mix(nt, fac, (*cap, 1), (*spots, 1), -250, 100), socket(bsdf, "Base Color"))
    set_input(bsdf, "Roughness", 0.35)
    set_input(bsdf, "Subsurface Weight", 0.25)
    set_input(bsdf, "Coat Weight", 0.3)
    if glow:
        cap_glow, spot_glow, strength = glow
        nt.links.new(mix(nt, fac, (*cap_glow, 1), (*spot_glow, 1), -250, -200), socket(bsdf, "Emission Color"))
        set_input(bsdf, "Emission Strength", strength)
    return mat


# --------------------------------------------------------------------------
# Magic


def glow_material(name, color, strength):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", "Output", (300, 0))
    emit = node(nt, "ShaderNodeEmission", "Emission", (0, 0))
    set_input(emit, "Color", (*color, 1))
    set_input(emit, "Strength", strength)
    link(nt, emit, "Emission", out, "Surface")
    return mat


def crystal_material(name, color, glow_strength):
    """Clear crystal with an inner glow that is brighter where it faces the viewer."""
    mat, nt, bsdf, out = new_material(name)
    set_input(bsdf, "Base Color", (*color, 1))
    set_input(bsdf, "Roughness", 0.06)
    set_input(bsdf, "Transmission Weight", 1.0)
    set_input(bsdf, "IOR", 1.58)
    weight = node(nt, "ShaderNodeLayerWeight", None, (-500, -300))
    set_input(weight, "Blend", 0.35)
    facing = math_op(nt, "SUBTRACT", 1.0, socket(weight, "Facing", output=True), -300, -300)
    strength = math_op(nt, "MULTIPLY", facing, glow_strength, -100, -300)
    emit = node(nt, "ShaderNodeEmission", None, (100, -300))
    set_input(emit, "Color", (*color, 1))
    nt.links.new(strength, socket(emit, "Strength"))
    add = node(nt, "ShaderNodeAddShader", None, (700, 0))
    link(nt, bsdf, "BSDF", add, "Shader")
    link(nt, emit, "Emission", add, "Shader_001")
    nt.links.new(socket(add, "Shader", output=True), socket(nt.nodes["Output"], "Surface"))
    return mat


def potion_material(name, color, glow, density=60.0):
    """Clear liquid coloured by absorption inside it, so the colour deepens with
    thickness like a real coloured liquid, plus a faint glow from within.
    density is per metre; glow is volume emission, so it also scales with thickness."""
    mat, nt, bsdf, out = new_material(name)
    set_input(bsdf, "Base Color", (1.0, 1.0, 1.0, 1))
    set_input(bsdf, "Roughness", 0.02)
    set_input(bsdf, "Transmission Weight", 1.0)
    set_input(bsdf, "IOR", 1.34)
    absorb = node(nt, "ShaderNodeVolumeAbsorption", None, (300, -300))
    set_input(absorb, "Color", (*color, 1))
    set_input(absorb, "Density", density)
    emit = node(nt, "ShaderNodeEmission", None, (300, -450))
    set_input(emit, "Color", (*color, 1))
    set_input(emit, "Strength", glow)
    add = node(nt, "ShaderNodeAddShader", None, (600, -350))
    link(nt, absorb, "Volume", add, "Shader")
    link(nt, emit, "Emission", add, "Shader_001")
    link(nt, add, "Shader", out, "Volume")
    return mat


def fog_material(density, color=(1.0, 0.85, 0.66), anisotropy=0.55, ground_height=2.5):
    """Volumetric mist that thickens near the ground (object-space Z)."""
    mat = bpy.data.materials.new("Forest Mist")
    nt = mat.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputMaterial", "Output", (600, 0))
    vol = node(nt, "ShaderNodeVolumePrincipled", "Mist", (300, 0))
    set_input(vol, "Color", (*color, 1))
    set_input(vol, "Anisotropy", anisotropy)
    geo = node(nt, "ShaderNodeNewGeometry", None, (-600, 0))
    sep = node(nt, "ShaderNodeSeparateXYZ", None, (-400, 0))
    link(nt, geo, "Position", sep, "Vector")
    falloff = node(nt, "ShaderNodeMapRange", "Height falloff", (-200, 0))
    link(nt, sep, "Z", falloff, "Value")
    set_input(falloff, "From Min", 0.0)
    set_input(falloff, "From Max", ground_height * 4)
    set_input(falloff, "To Min", density * 3.0)
    set_input(falloff, "To Max", density * 0.4)
    link(nt, falloff, "Result", vol, "Density")
    link(nt, vol, "Volume", out, "Volume")
    return mat


# --------------------------------------------------------------------------


def library():
    """Every material used in the scene, created once."""
    mats = SimpleNamespace(
        terrain=terrain_material(),
        hero_bark=bark_material("Ancient Bark", "bark_brown_02", 1.0, 1.0, moss=0.9, disp_scale=0.03,
                                tint=(0.62, 0.58, 0.52, 1)),
        tree_bark=bark_material("Oak Bark", "jolcham_oak_bark_01", 1.0, 0.5, moss=0.65,
                               tint=(0.5, 0.47, 0.42, 1)),
        log_bark=bark_material("Log Bark", "tree_bark_03", 1.0, 1.0, moss=0.7),
        cut_wood=end_grain_material("Cut Wood"),
        twig=bark_material("Twig", "bark_willow", 2.0, 2.0, moss=0.2),
        boulder=scan_material("Mossy Boulder", "mossy_rock", 0.35, moss=0.85),
        pebble=scan_material("Pebble", "lichen_rock", 3.0, moss=0.15),
        runestone=scan_material("Rune Stone", "lichen_rock", 0.55, moss=0.55),
        chest_wood=wood_planks_material(),
        iron=metal_material("Old Iron", "rusty_metal_04", 1.5),
        gold=metal_material("Gold", "rusty_metal_04", 4.0, color=(1.0, 0.72, 0.3), rough_range=(0.12, 0.35)),
        steel=metal_material("Blade Steel", "rusty_metal_04", 3.0, color=(0.62, 0.63, 0.65),
                             rough_range=(0.12, 0.38)),
        leather=scan_material("Leather", "brown_leather", 2.5, bump=0.4, bump_distance=0.002, specular=0.5),
        glass=simple_material("Glass", (0.95, 0.97, 1.0), roughness=0.02, transmission=1.0, ior=1.45),
        canopy=foliage_material("Oak Leaves", (0.022, 0.065, 0.012), (0.11, 0.19, 0.03), translucency=0.4),
        grass=foliage_material("Grass", (0.03, 0.075, 0.012), (0.12, 0.21, 0.035), translucency=0.4,
                               uv_gradient=True),
        dry_grass=foliage_material("Dry Grass", (0.2, 0.15, 0.06), (0.42, 0.34, 0.14), translucency=0.3,
                                   uv_gradient=True),
        fern=foliage_material("Fern", (0.018, 0.065, 0.012), (0.08, 0.19, 0.03), translucency=0.45),
        fallen_leaf=foliage_material("Fallen Leaves", (0.14, 0.05, 0.012), (0.5, 0.3, 0.05),
                                     translucency=0.2, hue_jitter=0.06),
        ivy=foliage_material("Ivy", (0.012, 0.045, 0.01), (0.05, 0.12, 0.02), translucency=0.3),
        stem=simple_material("Plant Stem", (0.07, 0.14, 0.03), roughness=0.5, subsurface=0.1),
        bluebell=simple_material("Bluebell", (0.22, 0.1, 0.75), roughness=0.4, subsurface=0.3,
                                 emission=((0.35, 0.2, 1.0), 0.3)),
        star_petal=simple_material("Star Petal", (0.9, 0.92, 0.95), roughness=0.45, subsurface=0.4,
                                   emission=((0.8, 0.95, 1.0), 0.1)),
        mushroom_stem=simple_material("Mushroom Stem", (0.8, 0.76, 0.66), roughness=0.6, subsurface=0.3),
        fungus=simple_material("Bracket Fungus", (0.42, 0.24, 0.09), roughness=0.65, subsurface=0.2),
        toadstool=spotted_cap_material("Toadstool Cap", (0.55, 0.04, 0.02), (0.9, 0.88, 0.8)),
        glowcap=spotted_cap_material("Glowcap", (0.04, 0.3, 0.42), (0.4, 0.95, 1.0),
                                     glow=((0.0, 0.5, 0.9), (0.3, 1.0, 0.95), 2.0), spot_scale=60.0),
        glowcap_stem=simple_material("Glowcap Stem", (0.6, 0.8, 0.85), roughness=0.5, subsurface=0.5,
                                     emission=((0.2, 0.8, 1.0), 0.4)),
        crystal=crystal_material("Arcane Crystal", (0.12, 0.6, 0.95), 4.0),
        crystal_violet=crystal_material("Violet Crystal", (0.45, 0.18, 0.95), 3.5),
        rune_glow=glow_material("Rune Glow", (0.2, 0.8, 1.0), 5.0),
        wisp=glow_material("Wisp", (0.35, 0.85, 1.0), 10.0),
        firefly=glow_material("Firefly", (1.0, 0.8, 0.3), 25.0),
        flame=glow_material("Candle Flame", (1.0, 0.5, 0.12), 15.0),
        potion_red=potion_material("Potion Red", (0.9, 0.12, 0.3), 3.0),
        potion_blue=potion_material("Potion Blue", (0.15, 0.4, 0.95), 3.0),
        potion_green=potion_material("Potion Green", (0.3, 0.9, 0.25), 3.0),
        mist=fog_material(0.0018),
    )
    for mat in vars(mats).values():
        assert_links_valid(mat.node_tree)
    return mats
