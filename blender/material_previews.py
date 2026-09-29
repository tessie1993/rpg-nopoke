"""Render every material of the forest scene on a labelled sphere (one contact sheet).

Usage:
    blender -b -P blender/material_previews.py -- --out renders/materials.png
"""
import argparse
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forest import config, materials, scene  # noqa: E402
from forest.util import link, node, set_input  # noqa: E402

COLUMNS = 8
RADIUS = 0.4
SPACING = 1.15          # sphere pitch, leaves room for the label
SKIP = {"mist"}         # volume only, nothing to show on a surface
UV_METRES = {"terrain": config.TERRAIN_SIZE}   # terrain UVs span the whole map


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cell", type=int, default=220, help="pixels per sphere")
    parser.add_argument("--samples", type=int, default=64)
    return parser.parse_args(argv)


def sphere(name, material, location, metres_per_uv):
    """UV sphere whose UVs are in metres (u around, v pole to pole), matching
    the swept tubes the bark materials are made for."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=RADIUS, calc_uvs=True)
    for face in bm.faces:
        face.smooth = True
        for loop in face.loops:
            u, v = loop[uv].uv
            loop[uv].uv = (u * 2 * math.pi * RADIUS / metres_per_uv, v * math.pi * RADIUS / metres_per_uv)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    # Keep glowing swatches from lighting or reflecting in their neighbours.
    obj.visible_diffuse = obj.visible_glossy = False
    bpy.context.scene.collection.objects.link(obj)
    return obj


def label(text, location, material):
    curve = bpy.data.curves.new(f"Label {text}", "FONT")
    curve.body = text
    curve.size = 0.085
    curve.align_x = "CENTER"
    curve.materials.append(material)
    obj = bpy.data.objects.new(curve.name, curve)
    obj.location = location
    obj.rotation_euler = (math.pi / 2, 0, 0)     # face the camera on -Y
    bpy.context.scene.collection.objects.link(obj)
    return obj


def studio(width, height):
    """Neutral grey sky, a key light from the upper left and an orthographic
    camera framing a width x height grid (ortho_scale spans the longer side)."""
    world = bpy.data.worlds.new("Studio")
    bpy.context.scene.world = world
    nt = world.node_tree
    nt.nodes.clear()
    bg = node(nt, "ShaderNodeBackground", None, (0, 0))
    set_input(bg, "Color", (0.18, 0.19, 0.2, 1))
    set_input(bg, "Strength", 1.0)
    link(nt, bg, "Background", node(nt, "ShaderNodeOutputWorld", None, (200, 0)), "Surface")

    key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN"))
    key.data.energy = 3.0
    key.data.angle = math.radians(5)
    key.rotation_euler = (Vector((0.6, 1.0, -0.7))).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(key)

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(width, height)
    cam.location = (width / 2 - SPACING / 2, -10.0, -height / 2 + SPACING / 2)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def main():
    args = parse_args()
    scene.clear_scene()
    mats = materials.library()
    text_mat = materials.glow_material("Label", (0.9, 0.9, 0.9), 1.0)

    entries = [(key, mat) for key, mat in vars(mats).items() if key not in SKIP]
    rows = math.ceil(len(entries) / COLUMNS)
    for i, (key, mat) in enumerate(entries):
        x, z = (i % COLUMNS) * SPACING, -(i // COLUMNS) * SPACING
        sphere(f"Swatch {mat.name}", mat, (x, 0, z), UV_METRES.get(key, 1.0))
        label(mat.name, (x, -RADIUS, z - RADIUS - 0.13), text_mat)

    width, height = COLUMNS * SPACING, rows * SPACING
    studio(width, height)
    scene.render_settings(samples=args.samples, resolution=(COLUMNS * args.cell, rows * args.cell))
    bpy.context.scene.view_settings.exposure = 0.0
    bpy.context.scene.render.filepath = str(Path(args.out).resolve())
    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[materials] {len(entries)} swatches -> {args.out} in {time.time() - start:.0f}s")


main()
