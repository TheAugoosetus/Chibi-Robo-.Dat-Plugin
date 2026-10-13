"""Static armatureless DAT-export regressions."""

from types import SimpleNamespace

import pytest

from exporter.phases.describe.describe import _validate_armatureless_static_meshes
from exporter.phases.describe.helpers.armature import make_static_root_armature
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
