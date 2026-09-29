"""Render a camera of an opened forest .blend.

Usage:
    blender -b forest.blend -P blender/render.py -- --camera Cam_Path \
        --out renders/path.png --width 1920 --height 1080 --samples 256
"""
import argparse
import sys
import time

import bpy


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", default="Cam_Path")
    parser.add_argument("--out", required=True)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=256)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    scene = bpy.context.scene
    scene.camera = bpy.data.objects[args.camera]
    scene.cycles.dicing_camera = scene.camera
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"[render] {args.camera} -> {args.out} in {time.time() - start:.0f}s")


main()
