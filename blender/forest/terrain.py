"""Forest terrain: A.N.T. Landscape base noise, a carved path, a flattened
clearing, and per-vertex masks that the materials and scatter systems read."""
import math

import bpy
import numpy as np
from mathutils import Vector, noise

from . import config


def catmull_rom(points, spacing=0.25):
    """Sample a uniform Catmull-Rom spline through points at ~spacing metres."""
    pts = [np.array(p, dtype=float) for p in points]
    pts = [2 * pts[0] - pts[1]] + pts + [2 * pts[-1] - pts[-2]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        steps = max(2, int(math.ceil(np.linalg.norm(p2 - p1) / spacing)))
        for t in np.linspace(0.0, 1.0, steps, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t
                              + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-2])
    return np.array(out)


def smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def noise2(x, y, scale, offset=0.0):
    """Perlin noise in [-1, 1] evaluated on arrays of coordinates."""
    return np.array([noise.noise(Vector((a / scale + offset, b / scale - offset, offset)))
                     for a, b in zip(x, y)])


class Terrain:
    """Regular height grid plus masks, with bilinear sampling helpers."""

    def __init__(self, obj, z, path_mask, path_distance, clearing_mask):
        self.obj = obj
        self.z = z
        self.path_mask_grid = path_mask
        self.path_distance_grid = path_distance
        self.clearing_grid = clearing_mask
        self.n = z.shape[0]
        self.half = config.TERRAIN_SIZE / 2.0
        self.step = config.TERRAIN_SIZE / (self.n - 1)

    def _sample(self, grid, x, y):
        fx = np.clip((x + self.half) / self.step, 0, self.n - 1.001)
        fy = np.clip((y + self.half) / self.step, 0, self.n - 1.001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        return float((grid[i, j] * (1 - tx) + grid[i + 1, j] * tx) * (1 - ty)
                     + (grid[i, j + 1] * (1 - tx) + grid[i + 1, j + 1] * tx) * ty)

    def height(self, x, y):
        return self._sample(self.z, x, y)

    def normal(self, x, y, eps=0.3):
        dx = self.height(x + eps, y) - self.height(x - eps, y)
        dy = self.height(x, y + eps) - self.height(x, y - eps)
        return Vector((-dx, -dy, 2 * eps)).normalized()

    def path_mask(self, x, y):
        return self._sample(self.path_mask_grid, x, y)

    def path_distance(self, x, y):
        return self._sample(self.path_distance_grid, x, y)

    def clearing(self, x, y):
        return self._sample(self.clearing_grid, x, y)

    def point(self, x, y, lift=0.0):
        return Vector((x, y, self.height(x, y) + lift))


def _path_segments(heights_at):
    """Segments of every path with smoothed centre-line heights and arc length."""
    starts, ends, h0, h1, s0, s1 = [], [], [], [], [], []
    for control in (config.PATH_MAIN, config.PATH_BRANCH):
        samples = catmull_rom(control)
        h = np.array([heights_at(x, y) for x, y in samples])
        kernel = np.ones(15) / 15.0
        h = np.convolve(np.pad(h, 7, mode="edge"), kernel, mode="valid")
        arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(samples, axis=0), axis=1))])
        starts.append(samples[:-1]); ends.append(samples[1:])
        h0.append(h[:-1]); h1.append(h[1:])
        s0.append(arc[:-1]); s1.append(arc[1:])
    return (np.concatenate(starts), np.concatenate(ends), np.concatenate(h0),
            np.concatenate(h1), np.concatenate(s0), np.concatenate(s1))


def _nearest_on_segments(xy, a, b, chunk=12000):
    """For each point, distance to the nearest segment, its index and parameter."""
    ab = b - a
    ab_len2 = np.maximum((ab ** 2).sum(axis=1), 1e-9)
    dist = np.empty(len(xy)); seg = np.empty(len(xy), dtype=int); par = np.empty(len(xy))
    for start in range(0, len(xy), chunk):
        p = xy[start:start + chunk, None, :]
        t = np.clip(((p - a[None]) * ab[None]).sum(axis=2) / ab_len2[None], 0.0, 1.0)
        closest = a[None] + t[..., None] * ab[None]
        d2 = ((p - closest) ** 2).sum(axis=2)
        idx = d2.argmin(axis=1)
        rows = np.arange(len(idx))
        dist[start:start + chunk] = np.sqrt(d2[rows, idx])
        seg[start:start + chunk] = idx
        par[start:start + chunk] = t[rows, idx]
    return dist, seg, par


def _base_landscape():
    """Create the A.N.T. Landscape grid and return (object, z grid)."""
    before = set(bpy.data.objects)
    result = bpy.ops.mesh.landscape_add(
        refresh=True, ant_terrain_name="Terrain",
        mesh_size_x=config.TERRAIN_SIZE, mesh_size_y=config.TERRAIN_SIZE,
        subdivision_x=config.TERRAIN_VERTS, subdivision_y=config.TERRAIN_VERTS,
        noise_type="hetero_terrain", basis_type="PERLIN_NEW", random_seed=config.SEED,
        noise_size=22.0, noise_depth=6, dimension=1.0, lacunarity=2.1, offset=0.9,
        height=1.0, maximum=100.0, minimum=-100.0, edge_falloff="0", smooth_mesh=True)
    if result != {"FINISHED"}:
        raise RuntimeError(f"A.N.T. landscape_add failed: {result}")
    obj = next(o for o in bpy.data.objects if o not in before)
    n = config.TERRAIN_VERTS
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", co)
    z = co.reshape(-1, 3)[:, 2].reshape(n, n)
    z = (z - z.min()) / max(z.max() - z.min(), 1e-6) * config.TERRAIN_RELIEF
    return obj, z


def build(material):
    obj, z = _base_landscape()
    n = config.TERRAIN_VERTS
    half = config.TERRAIN_SIZE / 2.0
    axis = np.linspace(-half, half, n)
    gx, gy = np.meshgrid(axis, axis, indexing="ij")  # grid[i, j] -> (x_i, y_j)

    cx, cy = config.CLEARING_CENTER
    r_clear = np.hypot(gx - cx, gy - cy)
    z = z + config.TERRAIN_BOWL * r_clear ** 2

    hx, hy = config.HERO_TREE
    z = z + 0.5 * np.exp(-((np.hypot(gx - hx, gy - hy) / 3.0) ** 2))

    probe = Terrain(obj, z, z * 0, z * 0, z * 0)
    a, b, h0, h1, s0, s1 = _path_segments(probe.height)

    xs, ys = gx.ravel(), gy.ravel()
    dist, seg, par = _nearest_on_segments(np.stack([xs, ys], axis=1), a, b)
    centre_h = h0[seg] + (h1[seg] - h0[seg]) * par
    arc = s0[seg] + (s1[seg] - s0[seg]) * par
    width = config.PATH_HALF_WIDTH * (1.0 + 0.2 * np.array(
        [noise.noise(Vector((s * 0.12, 3.1, 0.7))) for s in arc]))
    ragged = dist + 0.16 * noise2(xs, ys, 0.9, 11.3)

    core = 1.0 - smoothstep(0.55 * width, 1.05 * width, ragged)
    path_mask = 1.0 - smoothstep(0.7 * width, 1.3 * width, ragged)
    berm = 0.05 * np.exp(-((ragged - 1.3 * width) / 0.35) ** 2)

    zf = z.ravel()
    zf = zf + (centre_h - config.PATH_DEPTH - zf) * core + berm

    angle = np.arctan2(ys - cy, xs - cx)
    wobble = 1.0 + 0.12 * np.array([noise.noise(Vector((math.cos(t) * 1.3, math.sin(t) * 1.3, 5.0)))
                                    for t in angle])
    r = r_clear.ravel()
    clearing = 1.0 - smoothstep(0.62 * config.CLEARING_RADIUS * wobble,
                                1.05 * config.CLEARING_RADIUS * wobble, r)
    clear_h = float(zf[r < config.CLEARING_RADIUS * 0.6].mean())
    zf = zf + (clear_h - zf) * 0.85 * clearing

    detail = (0.06 * noise2(xs, ys, 1.3, 2.7) + 0.025 * noise2(xs, ys, 0.45, 5.9))
    zf = zf + detail * (1.0 - 0.6 * core)

    edge = np.maximum(np.abs(xs), np.abs(ys))
    detail = 1.0 - (1.0 - config.DETAIL_EDGE) * smoothstep(
        config.DETAIL_HALF_SIZE, config.DETAIL_HALF_SIZE + config.DETAIL_FADE, edge)

    co = np.stack([xs, ys, zf], axis=1)
    mesh = obj.data
    mesh.vertices.foreach_set("co", co.ravel())
    _store_point_attribute(mesh, "path_mask", path_mask)
    _store_point_attribute(mesh, "clearing_mask", clearing)
    _store_point_attribute(mesh, "detail", detail)
    _planar_uvs(mesh)
    mesh.update()
    mesh.materials.append(material)

    subsurf = obj.modifiers.new("Adaptive Subdivision", "SUBSURF")
    subsurf.levels = 0
    subsurf.render_levels = 1
    subsurf.use_adaptive_subdivision = True

    return Terrain(obj, zf.reshape(n, n), path_mask.reshape(n, n),
                   dist.reshape(n, n), clearing.reshape(n, n))


def _store_point_attribute(mesh, name, values):
    attr = mesh.attributes.get(name) or mesh.attributes.new(name, "FLOAT", "POINT")
    attr.data.foreach_set("value", values.astype(np.float32))


def _planar_uvs(mesh):
    """Top-down UVs in metres / terrain size, needed for tangent-space normals."""
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    co = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    corner_vert = np.empty(len(mesh.loops), dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", corner_vert)
    uvs = co[corner_vert, :2] / config.TERRAIN_SIZE + 0.5
    uv.data.foreach_set("uv", uvs.astype(np.float32).ravel())
