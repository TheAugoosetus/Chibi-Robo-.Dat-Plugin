"""Static armatureless DAT-export regressions."""

from types import SimpleNamespace

import pytest

from exporter.phases.describe.describe import (
    _collect_static_hierarchy_objects,
    _validate_armatureless_static_meshes,
)
from exporter.phases.describe.helpers.armature import (
    make_static_root_armature,
    make_static_hierarchy_armature,
)
from exporter.phases.plan.helpers.armature import plan_armature
from exporter.phases.plan.helpers.meshes import plan_meshes
from exporter.phases.plan.plan import plan_scene
from exporter.phases.compose.compose import compose_scene
from exporter.phases.serialize.serialize import serialize
from shared.BR.meshes import BRMesh
from shared.BR.scene import BRModel, BRScene
from shared.Constants.hsd import JOBJ_LIGHTING, JOBJ_OPA, JOBJ_ROOT_OPA
from shared.IR.enums import SkinType


def _static_mesh():
    return BRMesh(
        name="Cube",
        id="mesh_0_Root",
        vertices=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        faces=[[0, 1, 2]],
        parent_bone_name="Root",
        source_skin_type="RIGID",
    )


def test_synthetic_static_root_plans_to_identity_gc_joint():
    arm = make_static_root_armature()
    bones = plan_armature(arm)

    assert len(bones) == 1
    root = bones[0]
    assert root.parent_index is None
    assert root.name == "Root"
    assert root.position == pytest.approx((0.0, 0.0, 0.0), abs=1e-7)
    assert root.rotation == pytest.approx((0.0, 0.0, 0.0), abs=1e-7)
    assert root.scale == pytest.approx((1.0, 1.0, 1.0), abs=1e-7)


def test_armatureless_mesh_plans_as_rigid_root_owned_pobj():
    bones = plan_armature(make_static_root_armature())
    meshes = plan_meshes([_static_mesh()], [], bones)

    assert len(meshes) == 1
    assert meshes[0].parent_bone_index == 0
    assert meshes[0].bone_weights.type == SkinType.RIGID
    assert meshes[0].bone_weights.bone_name == "Root"


def test_synthetic_static_model_serializes_valid_scene_data_dat():
    model = BRModel(
        name="StaticModel",
        armature=make_static_root_armature(),
        meshes=[_static_mesh()],
        materials=[],
    )
    ir_scene = plan_scene(
        BRScene(models=[model]),
        options={"merge_meshes": False},
    )

    root = ir_scene.models[0].bones[0]
    assert root.flags & JOBJ_LIGHTING
    assert root.flags & JOBJ_OPA
    assert root.flags & JOBJ_ROOT_OPA

    roots, names = compose_scene(
        ir_scene,
        options={"include_bound_box": False},
    )
    raw = serialize(roots, names)

    assert names == ["scene_data"]
    assert len(raw) >= 0x20
    assert int.from_bytes(raw[0:4], "big") == len(raw)
    assert int.from_bytes(raw[0x0C:0x10], "big") == 1
    assert raw.endswith(b"scene_data\x00")


def _m4(tx=0.0, ty=0.0, tz=0.0):
    return [
        [1.0, 0.0, 0.0, tx],
        [0.0, 1.0, 0.0, ty],
        [0.0, 0.0, 1.0, tz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def test_object_empty_parenting_becomes_jobj_parenting():
    root = SimpleNamespace(
        name="Stand", type="EMPTY", parent=None, matrix_world=_m4())
    mesh = SimpleNamespace(
        name="Sign", type="MESH", parent=root, matrix_world=_m4(2.0, 0.0, 0.0))

    hierarchy = _collect_static_hierarchy_objects([mesh])
    arm, owners = make_static_hierarchy_armature(hierarchy)
    bones = plan_armature(arm)

    index_by_name = {bone.name: i for i, bone in enumerate(bones)}
    assert bones[index_by_name["Stand"]].parent_index is None
    assert bones[index_by_name["Sign"]].parent_index == index_by_name["Stand"]
    assert owners[id(mesh)] == "Sign"


def test_multiple_object_roots_get_common_identity_hsd_root():
    a = SimpleNamespace(name="A", type="MESH", parent=None, matrix_world=_m4())
    parent = SimpleNamespace(
        name="BParent", type="EMPTY", parent=None, matrix_world=_m4())
    b = SimpleNamespace(
        name="B", type="MESH", parent=parent, matrix_world=_m4())

    hierarchy = _collect_static_hierarchy_objects([a, b])
    arm, owners = make_static_hierarchy_armature(hierarchy)
    bones = plan_armature(arm)

    assert bones[0].parent_index is None
    assert bones[0].position == pytest.approx((0.0, 0.0, 0.0), abs=1e-7)
    assert bones[0].rotation == pytest.approx((0.0, 0.0, 0.0), abs=1e-7)
    index_by_name = {bone.name: i for i, bone in enumerate(bones)}
    assert bones[index_by_name["A"]].parent_index == 0
    assert bones[index_by_name["BParent"]].parent_index == 0
    assert bones[index_by_name["B"]].parent_index == index_by_name["BParent"]
    assert owners[id(a)] == "A"
    assert owners[id(b)] == "B"


def test_static_guard_rejects_animated_hierarchy_empty():
    root = SimpleNamespace(
        name="AnimatedEmpty", type="EMPTY", parent=None,
        matrix_world=_m4(),
        animation_data=SimpleNamespace(
            action=object(), nla_tracks=[], drivers=[]),
    )
    mesh = SimpleNamespace(
        name="Mesh", type="MESH", parent=root, matrix_world=_m4(),
        animation_data=None,
        data=SimpleNamespace(shape_keys=None, materials=[]),
        modifiers=[],
    )
    hierarchy = _collect_static_hierarchy_objects([mesh])
    with pytest.raises(ValueError, match="AnimatedEmpty"):
        _validate_armatureless_static_meshes([mesh], hierarchy)


def test_static_guard_rejects_material_animation():
    mat = SimpleNamespace(
        name="AnimatedMaterial",
        animation_data=SimpleNamespace(
            action=object(), nla_tracks=[], drivers=[]),
    )
    obj = SimpleNamespace(
        name="Mesh", animation_data=None,
        data=SimpleNamespace(shape_keys=None, materials=[mat]),
        modifiers=[],
    )
    with pytest.raises(ValueError, match="Material animation"):
        _validate_armatureless_static_meshes([obj])


def test_static_hierarchy_serializes_mesh_on_child_jobj():
    blender_gc_identity = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    root_obj = SimpleNamespace(
        name="Stand", type="EMPTY", parent=None,
        matrix_world=blender_gc_identity)
    mesh_obj = SimpleNamespace(
        name="Sign", type="MESH", parent=root_obj,
        matrix_world=blender_gc_identity)

    arm, owners = make_static_hierarchy_armature([root_obj, mesh_obj])
    mesh = _static_mesh()
    mesh.parent_bone_name = owners[id(mesh_obj)]
    mesh.id = "mesh_0_Sign"

    ir_scene = plan_scene(
        BRScene(models=[BRModel(
            name="SignModel", armature=arm, meshes=[mesh], materials=[])]),
        options={"merge_meshes": False},
    )
    roots, names = compose_scene(
        ir_scene, options={"include_bound_box": False})

    root_joint = roots[0].models[0].root_joint
    assert root_joint.name == "Stand"
    assert root_joint.child.name == "Sign"
    assert root_joint.child.property is not None

    raw = serialize(roots, names)
    assert int.from_bytes(raw[0:4], "big") == len(raw)


def test_static_guard_rejects_node_tree_material_animation():
    node_tree = SimpleNamespace(
        animation_data=SimpleNamespace(
            action=object(), nla_tracks=[], drivers=[]))
    mat = SimpleNamespace(
        name="NodeAnimatedMaterial", animation_data=None,
        node_tree=node_tree)
    obj = SimpleNamespace(
        name="Mesh", animation_data=None,
        data=SimpleNamespace(shape_keys=None, materials=[mat]),
        modifiers=[],
    )
    with pytest.raises(ValueError, match="Material animation"):
        _validate_armatureless_static_meshes([obj])


def test_static_guard_rejects_object_animation():
    obj = SimpleNamespace(
        name="Animated",
        animation_data=SimpleNamespace(action=object(), nla_tracks=[]),
        modifiers=[],
    )
    with pytest.raises(ValueError, match="static-only"):
        _validate_armatureless_static_meshes([obj])


def test_static_guard_rejects_object_driver():
    obj = SimpleNamespace(
        name="Driven",
        animation_data=SimpleNamespace(
            action=None, nla_tracks=[], drivers=[object()]
        ),
        data=SimpleNamespace(shape_keys=None),
        modifiers=[],
    )
    with pytest.raises(ValueError, match="drivers"):
        _validate_armatureless_static_meshes([obj])


def test_static_guard_rejects_shape_keys():
    obj = SimpleNamespace(
        name="Morph",
        animation_data=None,
        data=SimpleNamespace(
            shape_keys=SimpleNamespace(key_blocks=[object(), object()])
        ),
        modifiers=[],
    )
    with pytest.raises(ValueError, match="shape keys"):
        _validate_armatureless_static_meshes([obj])


def test_static_guard_rejects_armature_modifier():
    obj = SimpleNamespace(
        name="Skinned",
        animation_data=None,
        modifiers=[SimpleNamespace(type="ARMATURE")],
    )
    with pytest.raises(ValueError, match="Armature modifiers"):
        _validate_armatureless_static_meshes([obj])


def test_static_guard_accepts_plain_mesh():
    obj = SimpleNamespace(
        name="Plain", animation_data=None,
        data=SimpleNamespace(shape_keys=None), modifiers=[]
    )
    _validate_armatureless_static_meshes([obj])
