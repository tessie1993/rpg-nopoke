"""Scene layout and global settings. All distances are in metres."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEXTURE_ROOT = REPO_ROOT / "assets" / "textures"

SEED = 7

# Terrain -------------------------------------------------------------------
TERRAIN_SIZE = 110.0
TERRAIN_VERTS = 641          # per side -> 0.17 m grid spacing
DETAIL_HALF_SIZE = 34.0      # full ground-cover density inside this square
DETAIL_FADE = 18.0           # ...fading to DETAIL_EDGE over this distance
DETAIL_EDGE = 0.2
TERRAIN_RELIEF = 3.2         # height range of the A.N.T. noise after normalising
TERRAIN_BOWL = 0.0016        # extra rise per m^2 away from the clearing

# Paths: control points of Catmull-Rom splines (x, y).
PATH_MAIN = [(-1.5, -40.0), (1.8, -30.0), (-1.4, -20.0), (1.3, -11.0),
             (-0.5, -3.0), (0.0, 5.0)]
PATH_BRANCH = [(1.5, 12.5), (4.5, 17.0), (8.5, 23.5), (10.5, 31.0), (14.0, 40.0)]
PATH_HALF_WIDTH = 0.95
PATH_DEPTH = 0.07

CLEARING_CENTER = (0.0, 9.0)
CLEARING_RADIUS = 7.5

# Landmarks -----------------------------------------------------------------
HERO_TREE = (-3.0, 18.5)
STONE_CIRCLE_RADIUS = 4.3
STONE_COUNT = 7
CHEST = (2.3, 1.2)
LANTERN_POST = (-1.9, -7.0)
SWORD_STONE = (5.8, 12.8)
FALLEN_LOG = (3.4, -13.5)

# Forest trees are kept this far from the path centre and clearing edge.
TREE_PATH_CLEARANCE = 3.8
TREE_MIN_SPACING = 8.5          # wide enough for sunlit gaps between crowns

# Sun: golden hour, low in the south-south-east, behind most cameras.
SUN_ELEVATION_DEG = 7.0
SUN_AZIMUTH_DEG = 150.0         # clockwise from +Y (north)
SUN_TEMPERATURE = 3200.0        # Kelvin
# No forest trees within this distance of the line from the ancient tree
# towards the sun, so the low sun reaches the clearing and the tree.
SUN_LANE_HALF_WIDTH = 6.0

# Cameras: name -> ((x, y, height above ground), (target x, y, height above ground), lens mm)
CAMERA_PATH = ((1.0, -17.0, 1.75), (-0.4, 12.0, 2.15), 24.0)
CAMERA_CLEARING = ((5.5, 2.0, 1.9), (-1.2, 13.5, 1.35), 22.0)
CAMERA_AERIAL = ((46.0, -60.0, 58.0), (0.0, 4.0, 0.0), 30.0)
DETAIL_CAMERAS = {
    "Cam_Detail_Chest": ((0.8, -0.7, 0.95), (2.3, 1.2, 0.3), 35.0),
    "Cam_Detail_Roots": ((1.7, 14.15, 1.3), (-2.2, 16.4, 1.1), 24.0),
    "Cam_Detail_Runestone": ((0.4, 10.3, 1.35), (0.0, 13.3, 1.2), 30.0),
    "Cam_Detail_FairyRing": ((2.6, 3.7, 0.55), (4.3, 5.6, 0.1), 28.0),
    "Cam_Detail_Log": ((1.1, -15.4, 1.0), (3.4, -13.5, 0.4), 28.0),
    "Cam_Detail_Lantern": ((0.5, -9.4, 1.6), (-1.9, -7.0, 2.1), 32.0),
    "Cam_Detail_Sword": ((4.1, 10.7, 1.25), (5.8, 12.8, 0.9), 32.0),
}
