"""World lighting, mist, cameras and Cycles render settings."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from . import config
from .util import link, node, set_input

SUN_ELEVATION = math.radians(config.SUN_ELEVATION_DEG)
SUN_AZIMUTH = math.radians(config.SUN_AZIMUTH_DEG)


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.node_groups,
                  bpy.data.curves, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for item in list(block):
            block.remove(item)


def render_settings(samples=128, resolution=(1920, 1080)):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    cycles = scene.cycles
    cycles.device = "CPU"
    cycles.samples = samples
    cycles.use_adaptive_sampling = True
    cycles.adaptive_threshold = 0.02
    cycles.use_denoising = True
    cycles.max_bounces = 12
    cycles.diffuse_bounces = 6     # light filters leaf -> leaf -> floor
    cycles.glossy_bounces = 4
    cycles.transmission_bounces = 6
    cycles.volume_bounces = 1
    cycles.transparent_max_bounces = 8
    cycles.sample_clamp_indirect = 8.0
    cycles.dicing_rate = 1.5
    cycles.offscreen_dicing_scale = 8.0
    cycles.dicing_camera = scene.camera
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 1.0


def sun_direction():
    return Vector((math.cos(SUN_ELEVATION) * math.sin(SUN_AZIMUTH),
                   math.cos(SUN_ELEVATION) * math.cos(SUN_AZIMUTH),
                   math.sin(SUN_ELEVATION)))


def world_and_sun(sky_strength=0.35, sun_strength=14.0):
    world = bpy.data.worlds.get("Forest Sky") or bpy.data.worlds.new("Forest Sky")
    bpy.context.scene.world = world
    nt = world.node_tree
    nt.nodes.clear()
    out = node(nt, "ShaderNodeOutputWorld", "Output", (400, 0))
    bg = node(nt, "ShaderNodeBackground", "Background", (200, 0))
    sky = node(nt, "ShaderNodeTexSky", "Sky", (0, 0), sky_type="MULTIPLE_SCATTERING",
               sun_elevation=SUN_ELEVATION, sun_rotation=SUN_AZIMUTH, sun_disc=False,
               air_density=1.0, aerosol_density=2.5)
    link(nt, sky, "Color", bg, "Color")
    set_input(bg, "Strength", sky_strength)
    link(nt, bg, "Background", out, "Surface")

    light = bpy.data.lights.new("Sun", "SUN")
    light.energy = sun_strength
    light.angle = math.radians(1.2)
    light.use_temperature = True
    light.temperature = config.SUN_TEMPERATURE
    sun = bpy.data.objects.new("Sun", light)
    bpy.context.scene.collection.objects.link(sun)
    sun.rotation_euler = (-sun_direction()).to_track_quat("-Z", "Y").to_euler()
    return sun


def camera(name, spec, terrain, coll):
    (x, y, above), (tx, ty, t_above), lens = spec
    location = terrain.point(x, y, above)
    target = terrain.point(tx, ty, t_above)
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = 0.05
    data.clip_end = 400.0
    cam = bpy.data.objects.new(name, data)
    coll.objects.link(cam)
    cam.location = location
    cam.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    return cam


def cameras(terrain):
    coll = bpy.data.collections.new("Cameras")
    bpy.context.scene.collection.children.link(coll)
    path_cam = camera("Cam_Path", config.CAMERA_PATH, terrain, coll)
    path_cam.data.dof.use_dof = True
    path_cam.data.dof.focus_distance = 12.0
    path_cam.data.dof.aperture_fstop = 5.6
    camera("Cam_Clearing", config.CAMERA_CLEARING, terrain, coll)
    camera("Cam_Aerial", config.CAMERA_AERIAL, terrain, coll)
    for name, spec in config.DETAIL_CAMERAS.items():
        cam = camera(name, spec, terrain, coll)
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = (terrain.point(*spec[1][:2], spec[1][2]) - cam.location).length
        cam.data.dof.aperture_fstop = 4.0
    bpy.context.scene.camera = path_cam
    return path_cam


def mist_volume(material, height=20.0):
    """Box of ground-hugging mist over the whole terrain (catches god rays)."""
    bm = bmesh.new()
    size = config.TERRAIN_SIZE
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, height / 2 - 1.0))
                          @ Matrix.Diagonal((size, size, height, 1.0)))
    mesh = bpy.data.meshes.new("Mist")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new("Mist", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj
