"""Chibi-Robo-specific round-trip metadata regressions."""

from shared.BR.armature import BRArmature, BRBone
from shared.BR.meshes import BRVertexGroup
from shared.IR.enums import SkinType, ScaleInheritance
from shared.IR.skeleton import IRBone
from shared.IR.geometry import IRMesh
from shared.Constants.hsd import (
    JOBJ_TEXGEN, JOBJ_SPECULAR, JOBJ_XLU, JOBJ_ROOT_XLU,
    JOBJ_LIGHTING, JOBJ_OPA, JOBJ_ROOT_OPA,
)
from exporter.phases.plan.helpers.armature import plan_armature
from exporter.phases.plan.helpers.meshes import _pack_bone_weights
from exporter.phases.plan.helpers.scene import refine_bone_flags


IDENTITY = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def _ir_bone(flags):
    return IRBone(
        name="root",
        parent_index=None,
        position=(0.0, 0.0, 0.0),
        rotation=(0.0, 0.0, 0.0),
        scale=(1.0, 1.0, 1.0),
        inverse_bind_matrix=None,
        flags=flags,
        is_hidden=False,
        inherit_scale=ScaleInheritance.ALIGNED,
        ik_shrink=False,
        world_matrix=IDENTITY,
        local_matrix=IDENTITY,
        normalized_world_matrix=IDENTITY,
        normalized_local_matrix=IDENTITY,
        scale_correction=IDENTITY,
        accumulated_scale=(1.0, 1.0, 1.0),
        source_hsd_flags=flags,
    )


def test_plan_armature_keeps_source_jobj_flags():
    source = JOBJ_TEXGEN | JOBJ_SPECULAR | JOBJ_XLU | JOBJ_ROOT_XLU
    br = BRArmature(
        name="rig",
        bones=[BRBone(
            name="root",
            parent_index=None,
            edit_matrix=IDENTITY,
            tail_offset=(0.0, 1.0, 0.0),
            inherit_scale="ALIGNED",
            source_hsd_flags=source,
        )],
        matrix_basis=IDENTITY,
    )

    bone = plan_armature(br)[0]

    assert bone.source_hsd_flags == source
    assert bone.flags & JOBJ_TEXGEN
    assert bone.flags & JOBJ_SPECULAR
    assert bone.flags & JOBJ_XLU


def test_refine_flags_does_not_drop_chibi_render_flags():
    source = JOBJ_TEXGEN | JOBJ_SPECULAR | JOBJ_XLU | JOBJ_ROOT_XLU
    bone = _ir_bone(source)
    bone.mesh_indices = [0]
    mesh = IRMesh(
        name="m",
        vertices=[(0.0, 0.0, 0.0)],
        faces=[],
        parent_bone_index=0,
    )

    refine_bone_flags([bone], [mesh])

    assert bone.flags == source


def test_sample_reflective_joint_flags_survive_exactly():
    # Stock sample.dat reflective mesh owners use this combination:
    # ROOT_OPA | OPA | SPECULAR | TEXGEN | LIGHTING = 0x10050180.
    source = (
        JOBJ_ROOT_OPA | JOBJ_OPA | JOBJ_SPECULAR |
        JOBJ_TEXGEN | JOBJ_LIGHTING
    )
    assert source == 0x10050180

    bone = _ir_bone(source)
    bone.mesh_indices = [0]
    mesh = IRMesh(
        name="sample_reflective_body",
        vertices=[(0.0, 0.0, 0.0)],
        faces=[],
        parent_bone_index=0,
    )

    refine_bone_flags([bone], [mesh])
    assert bone.flags == 0x10050180


def test_rigid_source_skin_type_survives_full_weight_vertex_group():
    groups = [BRVertexGroup(
        name="Bone_02",
        assignments=[(0, 1.0), (1, 1.0), (2, 1.0)],
    )]

    weights = _pack_bone_weights(
        groups,
        source_skin_type=SkinType.RIGID.value,
        parent_bone_name="Bone_02",
    )

    assert weights.type == SkinType.RIGID
    assert weights.bone_name == "Bone_02"
    assert weights.assignments is None


def test_unannotated_vertex_groups_remain_weighted():
    groups = [BRVertexGroup(name="Bone_02", assignments=[(0, 1.0)])]
    weights = _pack_bone_weights(groups)

    assert weights.type == SkinType.WEIGHTED
