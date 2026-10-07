"""Stable fingerprints for imported Blender armatures and Actions.

These fingerprints are used only as change detectors for source-preservation
metadata. They are deliberately independent of Blender object identity and
custom properties: if the editable bone rest data or pose F-curves change,
the digest changes and the exporter falls back to rebuilding HSD data.
"""
import hashlib
import struct

from ..Constants.hsd import JOBJ_SKELETON, JOBJ_SKELETON_ROOT


_NORMAL_COORD_HSD_FLAG_MASK = JOBJ_SKELETON | JOBJ_SKELETON_ROOT


def _put_text(h, value):
    data = str(value).encode("utf-8", "surrogatepass")
    h.update(struct.pack(">I", len(data)))
    h.update(data)


def _put_float(h, value):
    h.update(struct.pack(">d", float(value)))


def armature_rest_fingerprint(armature):
    """Fingerprint the editable rest skeleton of a Blender armature."""
    h = hashlib.sha256()
    bones = list(armature.data.bones)
    h.update(struct.pack(">I", len(bones)))
    for bone in bones:
        _put_text(h, bone.name)
        _put_text(h, bone.parent.name if bone.parent else "")
        matrix = bone.matrix_local
        for r in range(4):
            for c in range(4):
                _put_float(h, matrix[r][c])
        _put_text(h, getattr(bone, "inherit_scale", ""))
        h.update(b"\x01" if getattr(bone, "use_connect", False) else b"\x00")
    return h.hexdigest()


def pose_action_fingerprint(action):
    """Fingerprint pose-bone F-curves of one Blender Action.

    Material/camera curves are intentionally excluded: source HSD bone
    animation can remain byte-preserved even if a paired material animation
    is edited.
    """
    h = hashlib.sha256()
    curves = [
        fc for fc in action.fcurves
        if getattr(fc, "data_path", "").startswith('pose.bones[')
    ]
    curves.sort(key=lambda fc: (fc.data_path, int(fc.array_index)))
    h.update(struct.pack(">I", len(curves)))

    for fc in curves:
        _put_text(h, fc.data_path)
        h.update(struct.pack(">i", int(fc.array_index)))
        _put_text(h, getattr(fc, "extrapolation", ""))
        modifiers = list(getattr(fc, "modifiers", ()) or ())
        h.update(struct.pack(">I", len(modifiers)))
        for mod in modifiers:
            _put_text(h, getattr(mod, "type", ""))

        points = list(fc.keyframe_points)
        h.update(struct.pack(">I", len(points)))
        for kp in points:
            _put_float(h, kp.co[0])
            _put_float(h, kp.co[1])
            _put_text(h, getattr(kp, "interpolation", ""))
            _put_text(h, getattr(kp, "handle_left_type", ""))
            _put_text(h, getattr(kp, "handle_right_type", ""))
            _put_float(h, kp.handle_left[0])
            _put_float(h, kp.handle_left[1])
            _put_float(h, kp.handle_right[0])
            _put_float(h, kp.handle_right[1])

    return h.hexdigest()


def mesh_normal_fingerprint(mesh_obj):
    """Fingerprint editable state that can change an exported normal stream.

    Exact DAT bind/local normals are reusable only while both the mesh and its
    skinning coordinate system are unchanged. The digest therefore covers
    topology, positions, effective corner normals, object transform, source
    skin type, owner bone, vertex-group weights, armature rest data, and
    preserved HSD bone flags. UV/color/material edits intentionally do not
    invalidate it.
    """
    h = hashlib.sha256()
    mesh = mesh_obj.data

    vertices = list(mesh.vertices)
    h.update(struct.pack(">I", len(vertices)))
    for vertex in vertices:
        _put_float(h, vertex.co[0])
        _put_float(h, vertex.co[1])
        _put_float(h, vertex.co[2])

    polygons = list(mesh.polygons)
    h.update(struct.pack(">I", len(polygons)))
    for poly in polygons:
        verts = list(poly.vertices)
        h.update(struct.pack(">I", len(verts)))
        for index in verts:
            h.update(struct.pack(">I", int(index)))

    if hasattr(mesh, "corner_normals"):
        normals = [cn.vector for cn in mesh.corner_normals]
    else:
        mesh.calc_normals_split()
        normals = [loop.normal for loop in mesh.loops]
    h.update(struct.pack(">I", len(normals)))
    for normal in normals:
        _put_float(h, normal[0])
        _put_float(h, normal[1])
        _put_float(h, normal[2])

    matrix = mesh_obj.matrix_world
    for row in range(4):
        for col in range(4):
            _put_float(h, matrix[row][col])

    # Skinning semantics / ownership. A rigid mesh reparented to another JOBJ
    # needs its world-space editable normals re-localised against that new
    # owner; an old exact local payload is no longer authoritative.
    _put_text(h, getattr(mesh_obj, "parent_bone", "") or "")
    try:
        skin_type = mesh_obj.get("dat_hsd_skin_type", "")
    except (AttributeError, TypeError):
        skin_type = ""
    _put_text(h, skin_type or "")

    # Vertex-group names and per-vertex weights define envelope membership.
    # Hash them even for currently-rigid meshes so changing a source mesh into
    # a weighted one cannot leave old exact-normal metadata looking pristine.
    groups = list(getattr(mesh_obj, "vertex_groups", ()) or ())
    group_rows = sorted(
        (
            int(getattr(group, "index", i)),
            str(getattr(group, "name", "")),
        )
        for i, group in enumerate(groups)
    )
    h.update(struct.pack(">I", len(group_rows)))
    for group_index, group_name in group_rows:
        h.update(struct.pack(">i", group_index))
        _put_text(h, group_name)

    h.update(struct.pack(">I", len(vertices)))
    for vertex in vertices:
        assignments = sorted(
            (
                int(getattr(item, "group", -1)),
                float(getattr(item, "weight", 0.0)),
            )
            for item in (getattr(vertex, "groups", ()) or ())
        )
        h.update(struct.pack(">I", len(assignments)))
        for group_index, weight in assignments:
            h.update(struct.pack(">i", group_index))
            _put_float(h, weight)

    # Envelope/local normal space also depends on the rest skeleton. Reuse the
    # existing rest fingerprint, then add preserved HSD flags because
    # SKELETON/SKELETON_ROOT bits participate in envelope coordinate-system
    # selection but are not native Blender rest-matrix state.
    parent = getattr(mesh_obj, "parent", None)
    if parent is not None and getattr(parent, "type", None) == "ARMATURE":
        _put_text(h, armature_rest_fingerprint(parent))
        bones = list(getattr(getattr(parent, "data", None), "bones", ()) or ())
        h.update(struct.pack(">I", len(bones)))
        for bone in bones:
            _put_text(h, getattr(bone, "name", ""))
            try:
                flags = bone.get("dat_hsd_flags")
            except (AttributeError, TypeError):
                flags = None
            _put_text(
                h,
                "" if flags is None
                else int(flags) & _NORMAL_COORD_HSD_FLAG_MASK,
            )
    else:
        _put_text(h, "")
        h.update(struct.pack(">I", 0))

    return h.hexdigest()


def material_routing_fingerprint(material):
    """Fingerprint shader state relevant to HSD color/alpha routing.

    Node positions and image pixel contents are intentionally excluded.
    Structural edits, links, routing-node properties, and socket defaults are
    included so original HSD source hints cannot silently override a modified
    Blender material.
    """
    h = hashlib.sha256()
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return h.hexdigest()

    relevant_props = (
        "operation", "blend_type", "attribute_name", "uv_map",
        "extension", "interpolation",
    )

    nodes = sorted(list(tree.nodes), key=lambda n: (n.name, n.bl_idname))
    h.update(struct.pack(">I", len(nodes)))
    for node in nodes:
        _put_text(h, node.name)
        _put_text(h, node.bl_idname)
        for prop in relevant_props:
            if hasattr(node, prop):
                _put_text(h, prop)
                _put_text(h, getattr(node, prop))

        for socket in list(node.inputs):
            _put_text(h, "I")
            _put_text(h, socket.identifier)
            h.update(b"\x01" if socket.is_linked else b"\x00")
            if not socket.is_linked and hasattr(socket, "default_value"):
                _fingerprint_socket_value(h, socket.default_value)

        # RGB and Value nodes store their editable constant on outputs.
        if node.bl_idname in ("ShaderNodeRGB", "ShaderNodeValue"):
            for socket in list(node.outputs):
                _put_text(h, "O")
                _put_text(h, socket.identifier)
                if hasattr(socket, "default_value"):
                    _fingerprint_socket_value(h, socket.default_value)

    links = sorted(
        list(tree.links),
        key=lambda link: (
            link.from_node.name, link.from_socket.identifier,
            link.to_node.name, link.to_socket.identifier,
        ),
    )
    h.update(struct.pack(">I", len(links)))
    for link in links:
        _put_text(h, link.from_node.name)
        _put_text(h, link.from_socket.identifier)
        _put_text(h, link.to_node.name)
        _put_text(h, link.to_socket.identifier)

    return h.hexdigest()


def _fingerprint_socket_value(h, value):
    if isinstance(value, (str, bool, int)):
        _put_text(h, value)
        return
    if isinstance(value, float):
        _put_float(h, value)
        return
    if hasattr(value, "__len__"):
        try:
            seq = list(value)
        except TypeError:
            _put_text(h, repr(value))
            return
        h.update(struct.pack(">I", len(seq)))
        for item in seq:
            try:
                _put_float(h, item)
            except (TypeError, ValueError):
                _put_text(h, item)
        return
    try:
        _put_float(h, value)
    except (TypeError, ValueError):
        _put_text(h, repr(value))
