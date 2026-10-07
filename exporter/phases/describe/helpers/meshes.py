"""Snapshot Blender mesh objects into BRMesh dataclasses.

bpy lives here. Pure transformation (BR → IR) lives in
`exporter/phases/plan/helpers/meshes.py`. The Blender Z-up → GameCube
Y-up coordinate rotation is also pushed into plan — describe captures
positions in Blender frame.

Materials are deduped here: identical Blender materials produce one
BRMaterial in the parallel list that BRMesh.material_index points into.
"""
import math
import re
import json
import base64
import binascii
import struct
import zlib
import bpy
from mathutils import Matrix

try:
    from .....shared.BR.meshes import (
        BRMesh, BRMeshInstance, BRUVLayer, BRColorLayer, BRVertexGroup,
    )
    from .....shared.helpers.logger import StubLogger
    from .....shared.helpers.blender_fingerprint import mesh_normal_fingerprint
    from .materials import describe_material
    from ...plan.helpers.materials import plan_material
except (ImportError, SystemError):
    from shared.BR.meshes import (
        BRMesh, BRMeshInstance, BRUVLayer, BRColorLayer, BRVertexGroup,
    )
    from shared.helpers.logger import StubLogger
    from shared.helpers.blender_fingerprint import mesh_normal_fingerprint
    from exporter.phases.describe.helpers.materials import describe_material
    from exporter.phases.plan.helpers.materials import plan_material


def describe_meshes(armature, br_armature, logger=StubLogger(), image_cache=None):
    """Read mesh objects parented to an armature into a BRMesh list.

    In: armature (bpy.types.Object, type='ARMATURE'); br_armature
        (BRArmature, used to validate parent_bone_name); logger;
        image_cache (dict|None, id(bpy_image) → BRImage, passed by
        describe_scene so image datablocks shared across armatures
        serialise once).
    Out: (br_meshes, br_instances, br_materials, blender_materials).
        br_meshes / blender_materials are parallel lists.
        br_materials is the deduped pool BRMesh.material_index points into.
    """
    bone_names = {b.name for b in br_armature.bones}

    mesh_objects = sorted(
        [obj for obj in bpy.data.objects
         if obj.type == 'MESH' and obj.parent is armature],
        key=_mesh_sort_key,
    )

    material_cache = {}
    if image_cache is None:
        image_cache = {}
    br_materials = []
    material_dedup = {}  # id(BRMaterial) → index into br_materials

    br_meshes = []
    blender_materials = []

    for mesh_obj in mesh_objects:
        meshes_for_obj, mats_for_obj = _describe_mesh_object(
            mesh_obj, bone_names, logger,
            material_cache, image_cache,
        )
        for br_mesh, br_mat in zip(meshes_for_obj, mats_for_obj):
            if br_mat is None:
                br_mesh.material_index = None
            else:
                key = id(br_mat)
                if key not in material_dedup:
                    material_dedup[key] = len(br_materials)
                    br_materials.append(br_mat)
                br_mesh.material_index = material_dedup[key]
            br_meshes.append(br_mesh)
            blender_materials.append(_blender_material_for(mesh_obj, br_mesh))

    # Stamp mesh_id in the importer's synthetic `mesh_NN_<bone>` format.
    # The format is load-bearing — `exporter/phases/compose/helpers/
    # material_animations.py:_parse_mesh_index` parses the digit out of
    # `IRMaterialTrack.material_mesh_name` to bind animations to meshes,
    # and the importer's plan + build_blender use the same key shape on
    # their side. Mirroring the format here keeps BBB round-trip parity
    # without needing a deeper refactor of the IR material-anim binding.
    digit_width = len(str(max(len(br_meshes) - 1, 0)))
    for i, br_mesh in enumerate(br_meshes):
        bone_label = br_mesh.parent_bone_name or 'unknown'
        br_mesh.id = "mesh_%s_%s" % (str(i).zfill(digit_width), bone_label)

    total_verts = sum(len(m.vertices) for m in br_meshes)
    total_faces = sum(len(m.faces) for m in br_meshes)
    weighted = sum(1 for m in br_meshes if m.vertex_groups)
    logger.info("  Described %d meshes from armature '%s': %d verts, %d faces "
                "(%d weighted, %d materials)",
                len(br_meshes), armature.name, total_verts, total_faces,
                weighted, len(br_materials))
    return br_meshes, [], br_materials, blender_materials


# Blender Z-up → GameCube Y-up. Vertices/normals stay in Blender frame in
# BR; plan applies this on the way to IR.
_COORD_ROTATION_INV = Matrix.Rotation(math.pi / 2, 4, [1.0, 0.0, 0.0]).inverted()


def _normal_matrix_for_transform(vertex_xform):
    """Return the inverse-transpose 3x3 for transforming surface normals."""
    return vertex_xform.to_3x3().inverted().transposed()


def _describe_mesh_object(mesh_obj, bone_names, logger,
                          material_cache, image_cache):
    """Extract one Blender mesh into one or more BRMesh (split per material).

    Multi-material meshes (common in GLB/FBX rips) are split into one BRMesh
    per used material slot. Each sub-mesh carries its own remapped vertex
    indices, per-loop UV/colour/normal arrays, and filtered vertex groups.
    """
    mesh_data = mesh_obj.data
    mesh_data.calc_loop_triangles()

    # Compose the mesh's own world transform with the Z-up → Y-up
    # coordinate rotation. For a baked scene `matrix_world` is identity
    # so this collapses to just the coord rotation; for an unbaked
    # importer-built scene the matrix_world carries the Y-up→Z-up
    # viewing rotation, and `_COORD_ROTATION_INV @ matrix_world` cancels
    # it back out. Either way the captured vertices land in GameCube
    # Y-up world space.
    vertex_xform = _COORD_ROTATION_INV @ mesh_obj.matrix_world
    # Normals are directions, not positions. Under non-uniform object scale
    # they must use inverse(vertex_xform)^T; multiplying by the raw 3x3 would
    # skew lighting and reflection coordinates toward the stretched axis.
    normal_xform = _normal_matrix_for_transform(vertex_xform)

    all_vertices = [tuple(vertex_xform @ v.co) for v in mesh_data.vertices]
    if not all_vertices:
        return [], []

    all_polys = list(mesh_data.polygons)
    if not all_polys:
        return [], []

    all_uv_data = [
        (uv_layer.name, [(d.uv[0], d.uv[1]) for d in uv_layer.data])
        for uv_layer in mesh_data.uv_layers
    ]
    all_color_data = [
        (attr.name, [tuple(cd.color) for cd in attr.data])
        for attr in mesh_data.color_attributes
    ]
    # Keep Blender's editable/display normals and the untouched exact DAT
    # normals as separate channels. The former are in GC-world presentation
    # space; the latter remain in the source PObject's bind/local space.
    all_normals = _extract_normals(mesh_data, normal_xform)
    all_source_normals = _pristine_source_normals(mesh_obj, logger)

    per_vertex_groups = _extract_vertex_groups(mesh_obj, bone_names)
    parent_bone_name = _determine_parent_bone_name(
        mesh_obj, per_vertex_groups, bone_names,
    )
    is_hidden = mesh_obj.hide_render or mesh_obj.hide_viewport or mesh_obj.hide_get()

    num_materials = len(mesh_data.materials)
    if num_materials <= 1:
        material_groups = [(0, list(range(len(all_polys))))]
    else:
        groups_by_mat = {}
        for pi, poly in enumerate(all_polys):
            groups_by_mat.setdefault(poly.material_index, []).append(pi)
        material_groups = sorted(groups_by_mat.items())

    out_meshes = []
    out_materials = []
    for mat_index, poly_indices in material_groups:
        if not poly_indices:
            continue
        br_mesh, ir_mat = _build_submesh(
            mesh_obj.name, mat_index, num_materials,
            all_vertices, all_polys, poly_indices,
            all_uv_data, all_color_data, all_normals,
            all_source_normals,
            per_vertex_groups, parent_bone_name, is_hidden,
            mesh_data.materials, logger,
            material_cache, image_cache,
        )
        if br_mesh is not None:
            # Preserve the imported HSD skin semantic stored on the Blender
            # object. _build_submesh deliberately does not know about bpy
            # objects, so attach this metadata here at the object boundary.
            br_mesh.source_skin_type = mesh_obj.get("dat_hsd_skin_type")
            raw_formats = mesh_obj.get("dat_hsd_vertex_formats")
            if isinstance(raw_formats, str) and raw_formats:
                try:
                    parsed_formats = json.loads(raw_formats)
                    if isinstance(parsed_formats, list):
                        br_mesh.source_vertex_formats = [
                            dict(fmt) for fmt in parsed_formats
                            if isinstance(fmt, dict)
                        ]
                except (ValueError, TypeError):
                    logger.warning(
                        "  Mesh '%s' has invalid dat_hsd_vertex_formats metadata; "
                        "using generic GX formats", mesh_obj.name)
            out_meshes.append(br_mesh)
            out_materials.append(ir_mat)

    return out_meshes, out_materials


def _build_submesh(mesh_name, mat_index, num_materials,
                   all_vertices, all_polys, poly_indices,
                   all_uv_data, all_color_data, all_normals,
                   all_source_normals,
                   per_vertex_groups, parent_bone_name, is_hidden,
                   bpy_materials, logger,
                   material_cache, image_cache):
    used_verts = set()
    for pi in poly_indices:
        for vi in all_polys[pi].vertices:
            used_verts.add(vi)
    sorted_verts = sorted(used_verts)
    vert_remap = {old: new for new, old in enumerate(sorted_verts)}
    vertices = [all_vertices[vi] for vi in sorted_verts]

    faces = []
    loop_indices = []
    for pi in poly_indices:
        poly = all_polys[pi]
        faces.append([vert_remap[vi] for vi in poly.vertices])
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            loop_indices.append(li)

    if not faces:
        return None, None

    uv_layers = [
        BRUVLayer(name=name, uvs=[data[li] for li in loop_indices])
        for name, data in all_uv_data
    ]
    color_layers = [
        BRColorLayer(name=name, colors=[data[li] for li in loop_indices])
        for name, data in all_color_data
    ]
    normals = (
        [all_normals[li] for li in loop_indices] if all_normals else None
    )
    source_normals = (
        [all_source_normals[li] for li in loop_indices]
        if all_source_normals else None
    )

    vertex_groups = []
    for vg_name, vg_assignments in per_vertex_groups:
        filtered = [
            (vert_remap[vi], w)
            for (vi, w) in vg_assignments
            if vi in vert_remap
        ]
        if filtered:
            vertex_groups.append(BRVertexGroup(name=vg_name, assignments=filtered))

    br_material = None
    cull_front = False
    cull_back = False
    if bpy_materials and mat_index < len(bpy_materials) and bpy_materials[mat_index]:
        bpy_mat = bpy_materials[mat_index]
        cull_back = bpy_mat.use_backface_culling
        br_material = describe_material(
            bpy_mat, logger=logger,
            cache=material_cache, image_cache=image_cache,
        )

    name = mesh_name if num_materials <= 1 else "%s_%03d" % (mesh_name, mat_index)
    # Final `mesh_id` is stamped by the outer `describe_meshes` loop
    # once the post-split mesh index is known.
    mesh_id = name

    br_mesh = BRMesh(
        name=name,
        id=mesh_id,
        vertices=vertices,
        faces=faces,
        uv_layers=uv_layers,
        color_layers=color_layers,
        normals=normals,
        source_normals=source_normals,
        vertex_groups=vertex_groups,
        parent_bone_name=parent_bone_name,
        is_hidden=is_hidden,
        material_index=None,  # filled by caller
    )
    # Stash extras the IRMesh needs but BRMesh doesn't model yet.
    br_mesh._cull_front = cull_front
    br_mesh._cull_back = cull_back
    return br_mesh, br_material


def _pristine_source_normals(mesh_obj, logger):
    """Return exact imported HSD normals when the editable mesh is unchanged.

    Blender stores visible custom normals as unit vectors, so the exact
    fixed-point source magnitudes are kept as compressed object metadata.
    A post-import fingerprint covers topology, positions, effective normals,
    and object transform. Any relevant edit invalidates this passthrough.
    """
    baseline = mesh_obj.get("dat_hsd_source_normal_fingerprint")
    payload = mesh_obj.get("dat_hsd_source_normals_b64")
    count = mesh_obj.get("dat_hsd_source_normal_count")
    if not isinstance(baseline, str) or not baseline:
        return None
    if not isinstance(payload, str) or not payload:
        return None
    try:
        count = int(count)
    except (TypeError, ValueError):
        return None
    if count != len(mesh_obj.data.loops):
        return None

    if mesh_normal_fingerprint(mesh_obj) != baseline:
        logger.debug(
            "  Mesh '%s': source normals invalidated by geometry/normal edit",
            mesh_obj.name)
        return None

    try:
        raw = zlib.decompress(base64.b64decode(payload))
    except (ValueError, binascii.Error, zlib.error):
        logger.warning(
            "  Mesh '%s': invalid source-normal metadata; using Blender normals",
            mesh_obj.name)
        return None

    expected = count * 12
    if len(raw) != expected:
        logger.warning(
            "  Mesh '%s': source-normal metadata size mismatch (%d != %d)",
            mesh_obj.name, len(raw), expected)
        return None

    normals = [
        struct.unpack_from(">fff", raw, i * 12)
        for i in range(count)
    ]
    logger.debug(
        "  Mesh '%s': reusing %d exact source HSD corner normals",
        mesh_obj.name, count)
    return normals


def _extract_normals(mesh_data, normal_xform):
    """Return Blender's effective per-loop normals in the GameCube frame.

    NRM and CLR0 are independent GX attributes and may coexist. Chibi-Robo
    uses that combination extensively: normals feed lighting/reflection while
    CLR0 can independently feed diffuse RGB and/or alpha.

    For imported untouched DATs, _pristine_source_normals() runs first so
    fixed-point source values can round-trip exactly. This function is the
    editable fallback for new or modified meshes.
    """
    if hasattr(mesh_data, 'corner_normals'):
        raw = [cn.vector for cn in mesh_data.corner_normals]
    else:
        mesh_data.calc_normals_split()
        raw = [loop.normal for loop in mesh_data.loops]
    return [tuple(normal_xform @ n) for n in raw]


def _has_varying_vertex_colors(mesh_data):
    """True if any colour attribute has per-vertex variation. Mirrors compose,
    which encodes a CLR layer only when it varies and drops uniform ones."""
    for attr in mesh_data.color_attributes:
        data = attr.data
        if not data:
            continue
        first = tuple(data[0].color)
        if any(tuple(d.color) != first for d in data):
            return True
    return False


def _extract_vertex_groups(mesh_obj, bone_names):
    """Return [(bone_name, [(vertex_index, weight), ...]), ...] for groups
    whose name matches a bone. Vertex groups with names that don't match a
    bone are dropped (Blender often carries extras like "Group" left over
    from rigging or unrelated modifiers)."""
    bone_groups = {
        vg.index: vg.name
        for vg in mesh_obj.vertex_groups
        if vg.name in bone_names
    }
    if not bone_groups:
        return []

    by_bone = {}
    for vertex in mesh_obj.data.vertices:
        for ge in vertex.groups:
            if ge.group in bone_groups and ge.weight > 0.0:
                bone_name = bone_groups[ge.group]
                by_bone.setdefault(bone_name, []).append((vertex.index, ge.weight))
    return [(name, pairs) for name, pairs in by_bone.items()]


def _determine_parent_bone_name(mesh_obj, per_vertex_groups, bone_names):
    """Honour Blender's explicit parent_bone link if it points at a real bone.

    Otherwise leave it None and let plan compute the nearest-common-ancestor
    from the bone names referenced by the mesh's vertex groups.
    """
    if mesh_obj.parent_bone and mesh_obj.parent_bone in bone_names:
        return mesh_obj.parent_bone
    return None


def _blender_material_for(mesh_obj, br_mesh):
    """Return the bpy.types.Material that the given BRMesh was built from.

    The mesh-anim exporter needs this side-channel so it can rebuild the
    `mesh_{idx}_{bone_name}` → material map the importer used.
    """
    mat_index = 0
    if "_" in br_mesh.name:
        m = re.search(r'_(\d+)$', br_mesh.name)
        if m:
            mat_index = int(m.group(1))
    if mat_index < len(mesh_obj.data.materials):
        return mesh_obj.data.materials[mat_index]
    return None


def _mesh_sort_key(mesh_obj):
    name = mesh_obj.name
    match = re.search(r'(\d+)$', name)
    if match:
        return (name[:match.start()], int(match.group(1)))
    return (name, 0)
