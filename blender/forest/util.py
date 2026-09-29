"""Small helpers shared by every builder module."""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def socket(node, identifier, output=False):
    """Return a node socket by its unique identifier (names are not unique)."""
    sockets = node.outputs if output else node.inputs
    for sock in sockets:
        if sock.identifier == identifier:
            return sock
    raise KeyError(f"{node.bl_idname} has no {'output' if output else 'input'} "
                   f"{identifier!r}; available: {[s.identifier for s in sockets]}")


def link(tree, from_node, from_id, to_node, to_id):
    tree.links.new(socket(from_node, from_id, output=True), socket(to_node, to_id))


def node(tree, bl_idname, label=None, location=(0, 0), **props):
    """Create a node, set its properties and return it."""
    new = tree.nodes.new(bl_idname)
    new.location = location
    if label:
        new.label = label
        new.name = label
    for key, value in props.items():
        setattr(new, key, value)
    return new


def assert_links_valid(tree):
    """Fail loudly on links Blender marks invalid (e.g. to a disabled socket)."""
    bad = [f"{l.from_node.name}.{l.from_socket.identifier} -> {l.to_node.name}.{l.to_socket.identifier}"
           for l in tree.links if not l.is_valid]
    if bad:
        raise RuntimeError(f"Invalid links in {tree.name}: {bad}")


def set_input(node_, identifier, value):
    socket(node_, identifier).default_value = value


def collection(name, parent=None, hidden=False):
    """Get or create a collection linked under parent (scene root by default)."""
    coll = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    parent_coll = parent or bpy.context.scene.collection
    if coll.name not in parent_coll.children:
        parent_coll.children.link(coll)
    if hidden:
        layer_coll = find_layer_collection(bpy.context.view_layer.layer_collection, coll.name)
        layer_coll.exclude = True
    return coll


def find_layer_collection(layer_coll, name):
    if layer_coll.collection.name == name:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, name)
        if found:
            return found
    return None


def mesh_data(name, bm, material=None, smooth=True):
    """Turn a bmesh into mesh data (the bmesh is freed)."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    if smooth:
        mesh.shade_smooth()
    if material:
        mesh.materials.append(material)
    return mesh


def mesh_object(name, bm, coll, material=None, smooth=True):
    """Turn a bmesh into a mesh object linked to coll."""
    obj = bpy.data.objects.new(name, mesh_data(name, bm, material, smooth))
    coll.objects.link(obj)
    return obj


def add_blocker(obj, blockers):
    """Invisible copy sharing the mesh, used by scatter layers to keep clear."""
    proxy = bpy.data.objects.new(f"{obj.name} Blocker", obj.data)
    proxy.matrix_world = obj.matrix_world
    blockers.objects.link(proxy)
    return proxy


def move_to_collection(obj, coll):
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    coll.objects.link(obj)


def smoothstep(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def frame_from_direction(direction):
    """Orthonormal (tangent, bitangent) pair perpendicular to direction."""
    d = direction.normalized()
    helper = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
    t = d.cross(helper).normalized()
    b = d.cross(t).normalized()
    return t, b


def sweep_tube(bm, points, radii, segments, uv_layer=None, cap_end=True,
               noise=None, u_scale=1.0, v_scale=1.0):
    """Sweep a circle along a polyline into bm, with UVs (u around, v along).

    points: list of Vector, radii: matching list of floats.
    noise: optional callable(point, angle) -> radial multiplier.
    u_scale: texture repeats around the tube; v_scale: repeats per metre.
    Returns the list of vertex rings.
    """
    rings = []
    prev_t = None
    length = 0.0
    lengths = [0.0]
    for i in range(1, len(points)):
        length += (points[i] - points[i - 1]).length
        lengths.append(length)

    for i, (p, r) in enumerate(zip(points, radii)):
        if i == 0:
            direction = points[1] - points[0]
        elif i == len(points) - 1:
            direction = points[-1] - points[-2]
        else:
            direction = points[i + 1] - points[i - 1]
        direction.normalize()
        # Parallel-transport the frame to avoid twisting.
        if prev_t is None:
            t, _ = frame_from_direction(direction)
        else:
            t = (prev_t - direction * prev_t.dot(direction)).normalized()
        b = direction.cross(t).normalized()
        prev_t = t
        ring = []
        for s in range(segments):
            angle = 2.0 * math.pi * s / segments
            radial = t * math.cos(angle) + b * math.sin(angle)
            rr = r * (noise(p, angle) if noise else 1.0)
            ring.append(bm.verts.new(p + radial * rr))
        rings.append(ring)

    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            face = bm.faces.new((rings[i][s], rings[i][s2], rings[i + 1][s2], rings[i + 1][s]))
            if uv_layer is not None:
                u0, u1 = u_scale * s / segments, u_scale * (s + 1) / segments
                v0, v1 = lengths[i] * v_scale, lengths[i + 1] * v_scale
                for loop, uv in zip(face.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
                    loop[uv_layer].uv = uv
    if cap_end and radii[-1] > 1e-5:
        bm.faces.new(list(reversed(rings[-1])))
    return rings


def apply_transform(obj, matrix):
    obj.data.transform(matrix)
    obj.data.update()


def rotation_z(angle):
    return Matrix.Rotation(angle, 4, 'Z')


def new_bmesh_with_uv():
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    return bm, uv


def box_uv(bm, uv_layer, metres_per_tile=1.0):
    """Project each face onto the plane of its dominant normal axis (metric UVs)."""
    for face in bm.faces:
        n = face.normal
        axis = max(range(3), key=lambda k: abs(n[k]))
        u_axis, v_axis = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co[u_axis] / metres_per_tile, co[v_axis] / metres_per_tile)
