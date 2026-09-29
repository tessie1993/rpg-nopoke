"""Ground-cover scatter layers over the terrain."""
from .scatter import scatter

# name: (asset attribute, scatter settings). Density is instances per m^2
# before masks; see scatter.INPUTS for every setting.
LAYERS = {
    "Grass": ("grass", dict(Density=9.0, Seed=1, Patch_Scale=0.11, Patch_Coverage=0.55,
                            Out_Clearing=0.75, Scale_Min=0.7, Scale_Max=1.3, Normal_Align=0.4)),
    "Tall Grass": ("tall_grass", dict(Density=1.2, Seed=2, Patch_Scale=0.2, Patch_Coverage=0.35,
                                      In_Clearing=0.3, Scale_Min=0.8, Scale_Max=1.2)),
    "Dry Grass": ("dry_grass", dict(Density=1.5, Seed=3, Patch_Scale=0.16, Patch_Coverage=0.35,
                                    Scale_Min=0.7, Scale_Max=1.1)),
    "Ferns": ("ferns", dict(Density=0.45, Seed=4, Patch_Scale=0.08, Patch_Coverage=0.6,
                            In_Clearing=0.1, Scale_Min=0.75, Scale_Max=1.6, Normal_Align=0.5,
                            Block_Radius=0.6)),
    "Bluebells": ("bluebells", dict(Density=3.0, Seed=5, Patch_Scale=0.22, Patch_Coverage=0.28,
                                    Out_Clearing=0.6, Scale_Min=0.8, Scale_Max=1.2)),
    "Star Flowers": ("star_flowers", dict(Density=2.5, Seed=6, Patch_Scale=0.3, Patch_Coverage=0.3,
                                          Out_Clearing=0.25, Scale_Min=0.8, Scale_Max=1.3)),
    "Toadstools": ("toadstools", dict(Density=0.06, Seed=7, Patch_Scale=0.12, Patch_Coverage=0.5,
                                      Scale_Min=0.7, Scale_Max=1.3, Block_Radius=0.25)),
    "Glowcaps": ("glowcaps", dict(Density=0.12, Seed=8, Patch_Scale=0.1, Patch_Coverage=0.45,
                                  In_Clearing=0.6, Scale_Min=0.8, Scale_Max=1.6, Block_Radius=0.25)),
    "Twigs": ("twigs", dict(Density=1.4, Seed=9, On_Path=0.35, Normal_Align=1.0, Max_Tilt=0.05,
                            Scale_Min=0.6, Scale_Max=1.5, Block_Radius=0.1)),
    "Pebbles": ("pebbles", dict(Density=3.5, Seed=10, Off_Path=0.2, On_Path=1.0, Normal_Align=1.0,
                                Max_Tilt=0.4, Scale_Min=0.3, Scale_Max=1.4, Sink=0.01, Block_Radius=0.05)),
    "Fallen Leaves": ("fallen_leaves", dict(Density=28.0, Seed=11, On_Path=0.45, Normal_Align=1.0,
                                            Max_Tilt=0.35, Scale_Min=0.7, Scale_Max=1.3, Block_Radius=0.05)),
}


def build(coll, terrain_obj, assets, blockers):
    return [scatter(f"Scatter {name}", coll, terrain_obj, getattr(assets, attr), blockers, **settings)
            for name, (attr, settings) in LAYERS.items()]
