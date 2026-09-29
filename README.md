# rpg-nopoke: magical forest

A procedural magical forest for an RPG, built in Blender 5.2 from Python and
textured with photo-scanned CC0 materials. The scripts are the source of
truth: one command builds the whole scene into a `.blend` file (about 40 s on
4 CPU cores).

## Setup

```sh
tools/install.sh                  # Blender 5.2.2 LTS, Godot 4.7.2, Blender extensions
python3 tools/fetch_textures.py   # 12 Poly Haven texture scans (2K; --res 1k|2k|4k)
```

`install.sh` installs into `/opt/tools` and links the binaries into
`/usr/local/bin` (override with `PREFIX` and `BIN_DIR`). It is safe to re-run.
It also installs these extensions from extensions.blender.org:

| Extension | Used for |
|---|---|
| A.N.T. Landscape | base terrain noise |
| Sapling Tree Gen | tree skeletons |
| IvyGen | ivy on the ancient tree |

`fetch_textures.py` checks every file against the MD5 published by the Poly
Haven API and skips files that are already correct. Textures go to
`assets/textures/`, which git ignores.

Godot 4.7.2 is installed, but nothing is exported to Godot yet.

## Build and render

```sh
blender -b -P blender/build_forest.py -- --out forest.blend
blender -b forest.blend -P blender/render.py -- --camera Cam_Path \
    --out renders/path.png --width 1920 --height 1080 --samples 256
blender -b -P blender/material_previews.py -- --out renders/materials.png
```

`material_previews.py` renders every scene material on a labelled 0.8 m
sphere and saves them as one contact sheet.

Cameras:

| Camera | Shows |
|---|---|
| `Cam_Path` | the forest path towards the clearing |
| `Cam_Clearing` | the clearing, stone circle and ancient tree |
| `Cam_Aerial` | the whole map from above |
| `Cam_Detail_Chest` | the open treasure chest and potions |
| `Cam_Detail_Roots` | roots, ivy and glowcaps of the ancient tree |
| `Cam_Detail_Runestone` | a carved rune stone |
| `Cam_Detail_FairyRing` | the toadstool fairy ring |
| `Cam_Detail_Log` | the fallen log with bracket fungi |
| `Cam_Detail_Lantern` | the lantern post |
| `Cam_Detail_Sword` | the sword in the stone |

## Scene contents

- **Terrain:** a 110 m A.N.T. landscape with a carved main path and a side
  path, a flattened clearing and a mound for the ancient tree. The ground
  material blends three ground scans (forest floor, damp mud, trodden path)
  and adds moss patches. Each scan is sampled twice to hide tiling. The
  terrain uses adaptive displacement.
- **Trees:**
  - Sapling Tree Gen grows the skeletons.
  - The bark meshes have root flare, buttresses and moss at the base.
  - Leaves are instanced leaf sprays.
  - There are two species with two variants each, and 204 trees placed with
    Poisson-disk spacing.
  - The ancient hero tree also has surface roots and ivy.
- **Ground cover:** 11 Geometry Nodes scatter layers. Each layer has its own
  path, clearing and patch masks, and trunks and props block scattering:
  - grass, tall grass and dry grass
  - ferns, bluebells and star flowers
  - toadstools and glowing mushrooms
  - twigs, pebbles and fallen leaves
- **Props:** mossy boulders, a fallen log with bracket fungi, and tree stumps.
- **Magic:**
  - a stone circle with Elder Futhark runes carved into the stones
  - a crystal altar and crystal clusters in the tree roots
  - a fairy ring
  - wisps and fireflies
  - ground mist
- **RPG items:** an open treasure chest full of coins, a lantern post, a
  sword in the stone, and potions.

## Code layout

| File | Contents |
|---|---|
| `blender/build_forest.py` | entry point, build order |
| `blender/render.py` | renders one camera |
| `blender/material_previews.py` | material contact sheet |
| `blender/forest/config.py` | layout, sizes, camera positions |
| `blender/forest/terrain.py` | landscape, paths, clearing, height queries |
| `blender/forest/materials.py` | all shader node materials |
| `blender/forest/trees.py` | tree skeletons, bark meshes, leaves, planting |
| `blender/forest/plants.py` | grass, ferns, flowers, mushrooms, twigs, leaves |
| `blender/forest/scatter.py` | Geometry Nodes scatter group |
| `blender/forest/ground_cover.py` | scatter layers and densities |
| `blender/forest/props.py` | boulders, fallen log, stumps |
| `blender/forest/magic.py` | rune stones, crystals, fairy ring, wisps, fireflies |
| `blender/forest/items.py` | chest, lantern, sword, potions |
| `blender/forest/scene.py` | sky, sun, mist, cameras, render settings |
| `blender/forest/shapes.py`, `util.py` | shared mesh and node helpers |

## Credits

All textures are CC0 scans from [Poly Haven](https://polyhaven.com). The list
of assets is in `tools/fetch_textures.py`.
