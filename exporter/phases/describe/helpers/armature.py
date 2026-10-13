"""Snapshot a Blender armature into a BRArmature.

bpy lives here. Pure transformation (BR → IR) lives in
`exporter/phases/plan/helpers/armature.py`.
"""
import bpy

try:
    from .....shared.BR.armature import BRArmature, BRBone, BRBoneSpline
    from .....shared.helpers.logger import StubLogger
except (ImportError, SystemError):
    from shared.BR.armature import BRArmature, BRBone, BRBoneSpline
    from shared.helpers.logger import StubLogger


# Blender edit-space matrix whose GameCube conversion is identity.
# plan_armature applies a -90-degree X conversion; this +90-degree X
# matrix cancels it so the synthesized root JOBJ has identity SRT.
_STATIC_ROOT_EDIT_MATRIX = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, -1.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
]


def make_static_root_armature(name="StaticModel"):
    """Build BR data for a one-JOBJ static model with no Blender armature.

    Armatureless Blender scenes still need one HSD Joint because DObjects/PObjects
    attach to a JOBJ at runtime. This creates that format-level root without
    requiring the user to author a meaningless one-bone rig in Blender.
    """
    root = BRBone(
        name="Root",
        parent_index=None,
        edit_matrix=[list(row) for row in _STATIC_ROOT_EDIT_MATRIX],
        tail_offset=(0.0, 0.0, 1.0),
        inherit_scale="ALIGNED",
        rotation_mode="XYZ",
        use_connect=False,
        is_hidden=False,
        source_hsd_flags=None,
    )
    return BRArmature(
        name=name,
        bones=[root],
        display_type="OCTAHEDRAL",
        matrix_basis=[
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        custom_props={},
    )


def _static_object_matrix(matrix):
    return [
        [float(matrix[r][c]) for c in range(4)]
        for r in range(4)
    ]


def _static_bone(name, parent_index, edit_matrix):
    return BRBone(
        name=name,
        parent_index=parent_index,
        edit_matrix=edit_matrix,
        tail_offset=(0.0, 0.0, 1.0),
        inherit_scale="ALIGNED",
        rotation_mode="XYZ",
        use_connect=False,
        is_hidden=False,
        source_hsd_flags=None,
    )


def make_static_hierarchy_armature(objects, name="StaticModel"):
    """Map a static Blender Object/Empty parent tree to HSD JOBJs.

    The input contains every MESH/EMPTY node participating in the desired
    hierarchy. World matrices become BR edit matrices; Plan derives local JOBJ
    SRT from parent/child world matrices without requiring an Armature object.
    """
    objects = list(objects)
    if not objects:
        return make_static_root_armature(name), {}

    object_ids = {id(obj) for obj in objects}
    roots = [
        obj for obj in objects
        if id(getattr(obj, "parent", None)) not in object_ids
    ]

    children = {}
    for obj in objects:
        parent = getattr(obj, "parent", None)
        if id(parent) in object_ids:
            children.setdefault(id(parent), []).append(obj)

    ordered = []

    def walk(obj):
        ordered.append(obj)
        for child in sorted(children.get(id(obj), ()), key=lambda o: o.name):
            walk(child)

    for root in sorted(roots, key=lambda o: o.name):
        walk(root)

    existing_names = {obj.name for obj in objects}
    synthetic_root = len(roots) != 1
    synthetic_name = "Root"
    if synthetic_root and synthetic_name in existing_names:
        synthetic_name = "HSDRoot"
        suffix = 1
        while synthetic_name in existing_names:
            synthetic_name = "HSDRoot.%03d" % suffix
            suffix += 1

    bones = []
    index_by_object_id = {}
    if synthetic_root:
        bones.append(_static_bone(
            synthetic_name, None,
            [list(row) for row in _STATIC_ROOT_EDIT_MATRIX],
        ))

    for obj in ordered:
        parent_obj = getattr(obj, "parent", None)
        if id(parent_obj) in index_by_object_id:
            parent_index = index_by_object_id[id(parent_obj)]
        elif synthetic_root:
            parent_index = 0
        else:
            parent_index = None

        index_by_object_id[id(obj)] = len(bones)
        bones.append(_static_bone(
            obj.name,
            parent_index,
            _static_object_matrix(obj.matrix_world),
        ))

    owner_names = {
        id(obj): obj.name
        for obj in objects
        if getattr(obj, "type", None) == "MESH"
    }
    return BRArmature(
        name=name,
        bones=bones,
        display_type="OCTAHEDRAL",
        matrix_basis=[
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        custom_props={},
    ), owner_names


def describe_armature(armature, logger=StubLogger()):
    """Read a Blender armature into a BRArmature.

    Bones are captured depth-first (parents before children), the order
    the DAT format expects.

    In: armature (bpy.types.Object, type='ARMATURE'); logger.
    Out: BRArmature with edit-bone matrices in Blender frame.
    """
    armature_data = armature.data
    source_flags_by_name = {
        b.name: b.get("dat_hsd_flags")
        for b in armature_data.bones
        if b.get("dat_hsd_flags") is not None
    }
    # Bone.hide is authoritative here. EditBone.hide is not guaranteed to
    # mirror the imported Bone visibility bit after mode switches.
    hidden_by_name = {
        b.name: bool(b.hide)
        for b in armature_data.bones
    }

    prev_active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = armature
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    armature.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')

    roots = [b for b in armature_data.edit_bones if b.parent is None]
    ordered = []
    _collect_depth_first(roots, ordered)
    name_to_index = {b.name: i for i, b in enumerate(ordered)}

    snapshots = []
    for b in ordered:
        snapshots.append({
            'name': b.name,
            'parent_name': b.parent.name if b.parent else None,
            'matrix': [list(row) for row in b.matrix],
            'tail_offset': (
                b.tail.x - b.head.x,
                b.tail.y - b.head.y,
                b.tail.z - b.head.z,
            ),
            'use_connect': b.use_connect,
            'inherit_scale': b.inherit_scale,
            'hide': hidden_by_name.get(b.name, False),
            'source_hsd_flags': source_flags_by_name.get(b.name),
        })

    bpy.ops.object.mode_set(mode='OBJECT')

    pose_rotation_modes = {
        pb.name: pb.rotation_mode for pb in armature.pose.bones
    } if armature.pose else {}

    # JOBJ_SPLINE curves are separate Curve objects bone-parented to this
    # armature. Map each back to its bone via parent_bone.
    bone_splines = _collect_bone_splines(armature)

    bpy.context.view_layer.objects.active = prev_active

    bones = []
    for snap in snapshots:
        parent_index = (
            name_to_index.get(snap['parent_name'])
            if snap['parent_name'] else None
        )
        bones.append(BRBone(
            name=snap['name'],
            parent_index=parent_index,
            edit_matrix=snap['matrix'],
            tail_offset=snap['tail_offset'],
            inherit_scale=snap['inherit_scale'],
            rotation_mode=pose_rotation_modes.get(snap['name'], 'XYZ'),
            use_connect=snap['use_connect'],
            is_hidden=snap['hide'],
            spline=bone_splines.get(snap['name']),
            source_hsd_flags=snap['source_hsd_flags'],
        ))

    custom_props = {k: armature[k] for k in armature.keys()}

    logger.info("  Described armature '%s': %d bone(s)", armature.name, len(bones))
    return BRArmature(
        name=armature.name,
        bones=bones,
        display_type=armature_data.display_type,
        matrix_basis=[list(row) for row in armature.matrix_basis],
        custom_props=custom_props,
    )


def _collect_bone_splines(armature):
    """Map bone name → BRBoneSpline for every Curve object bone-parented here.

    The importer builds one Curve object per JOBJ_SPLINE bone, parented via
    parent_type='BONE' + parent_bone. Read each curve's control points and
    type back; the coordinates are the curve's local spline points.
    """
    out = {}
    for obj in bpy.data.objects:
        if obj.type != 'CURVE':
            continue
        if obj.parent is not armature or obj.parent_type != 'BONE':
            continue
        if not obj.parent_bone or not obj.data.splines:
            continue
        sp = obj.data.splines[0]
        if sp.type == 'BEZIER':
            points = [[p.co[0], p.co[1], p.co[2]] for p in sp.bezier_points]
        else:
            points = [[p.co[0], p.co[1], p.co[2]] for p in sp.points]
        out[obj.parent_bone] = BRBoneSpline(
            curve_type=sp.type,
            control_points=points,
        )
    return out


def _collect_depth_first(siblings, result):
    for bone in siblings:
        result.append(bone)
        if bone.children:
            _collect_depth_first(bone.children, result)
