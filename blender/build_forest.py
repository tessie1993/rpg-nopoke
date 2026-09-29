"""Build the magical forest scene and save it as a .blend file.

Usage:
    blender -b -P blender/build_forest.py -- --out forest.blend
"""
import argparse
import sys
import time
from pathlib import Path

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))

from forest import (config, ground_cover, items, magic, materials, plants, props,  # noqa: E402
                    scene, terrain, trees)
from forest.util import collection  # noqa: E402

REQUIRED_ADDONS = ("bl_ext.blender_org.antlandscape",
                   "bl_ext.blender_org.sapling_tree_gen",
                   "bl_ext.blender_org.ivygen")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="forest.blend")
    return parser.parse_args(argv)


def enable_addons():
    for module in REQUIRED_ADDONS:
        addon_utils.enable(module, default_set=True)
        if not addon_utils.check(module)[1]:
            raise RuntimeError(f"Add-on {module} is not available - run tools/install.sh")


def step(label, func, *args, **kwargs):
    start = time.time()
    result = func(*args, **kwargs)
    print(f"[forest] {label}: {time.time() - start:.1f}s", flush=True)
    return result


def keep_clear_zones(boulders):
    """(x, y, radius) circles where forest trees must not be planted."""
    zones = [(*config.HERO_TREE, 9.0), (*config.CHEST, 3.0), (*config.LANTERN_POST, 2.5),
             (*config.SWORD_STONE, 3.0), (*config.FALLEN_LOG, 4.5)]
    for spec in (config.CAMERA_PATH, config.CAMERA_CLEARING):
        zones.append((spec[0][0], spec[0][1], 2.5))
    zones += [(b.location.x, b.location.y, max(b.scale) + 1.5) for b in boulders]
    return zones


def main():
    args = parse_args()
    enable_addons()
    scene.clear_scene()

    mats = step("materials", materials.library)
    ground = step("terrain", terrain.build, mats.terrain)
    asset_root = collection("Assets", hidden=True)
    blockers = collection("Blockers", hidden=True)
    assets = step("plant assets", plants.build_assets, mats, asset_root)
    variants = step("tree variants", trees.build_variants, mats, assets, asset_root)

    nature = collection("Props")
    step("props", props.build, nature, blockers, ground, mats)
    step("hero tree", trees.hero_tree, collection("Ancient Tree"), blockers, ground, mats, assets)
    step("magic", magic.build, collection("Magic"), blockers, ground, mats, assets)
    step("items", items.build, collection("Items"), blockers, ground, mats)
    boulders = [o for o in nature.objects if o.name.startswith("Boulder")]
    step("forest", trees.plant_forest, collection("Forest"), blockers, ground, variants,
         keep_clear_zones(boulders))
    step("ground cover", ground_cover.build, collection("Ground Cover"), ground.obj, assets, blockers)

    step("mist", scene.mist_volume, mats.mist)
    step("world", scene.world_and_sun)
    step("cameras", scene.cameras, ground)
    scene.render_settings()

    out = Path(args.out).resolve()
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
    print(f"[forest] saved {out}")


main()
