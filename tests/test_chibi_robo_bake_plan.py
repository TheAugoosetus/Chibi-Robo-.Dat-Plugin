"""Regression tests for Chibi-Robo's per-action scale bake optimization."""

from shared.BR.actions import BRBakeBone, BRBakeSkeleton
from importer.phases.plan.helpers.animations import compute_bake_plan


I = [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def _bone(name, parent):
    return BRBakeBone(
        name=name,
        parent_index=parent,
        rest_scale=(1.0, 1.0, 1.0),
        rest_rotation=(0.0, 0.0, 0.0),
        rest_position=(0.0, 0.0, 0.0),
        rest_world_matrix=I,
        normalized_rest_matrix=I,
        accumulated_scale=(1.0, 1.0, 1.0),
        classical_scaling=False,
    )


def _skeleton():
    # Model-wide partition says bone 1 and its child 2 need NONE because
    # *some* action scale-animates bone 1.
    return BRBakeSkeleton(
        bones=[_bone("root", None), _bone("child", 0), _bone("leaf", 1)],
        dfs_order=[0, 1, 2],
        scale_baked_indices=[1, 2],
        rest_scale_baked_indices=[],
    )


def test_default_plan_keeps_model_wide_scale_closure():
    bake, _levels = compute_bake_plan(_skeleton(), {2})
    assert bake == [1, 2]


def test_chibi_action_without_scale_does_not_bake_other_action_closure():
    bake, _levels = compute_bake_plan(
        _skeleton(), {2},
        scale_animated_indices=set(),
        per_action_scale=True,
    )
    assert bake == [2]


def test_chibi_action_with_scale_bakes_that_bones_descendants():
    bake, _levels = compute_bake_plan(
        _skeleton(), {1},
        scale_animated_indices={1},
        per_action_scale=True,
    )
    assert bake == [1, 2]
