"""Chibi-Robo fast source-animation import regressions."""

from types import SimpleNamespace

from importer.phases.build_blender.helpers.animations import (
    _can_preserve_source_animation,
)


def _action(has_joint_target=False):
    return SimpleNamespace(
        source_hsd_animation={
            "bones": [
                None,
                {
                    "aj_flags": 0,
                    "animation": {
                        "has_joint_target": has_joint_target,
                        "frames": [],
                    },
                },
            ]
        }
    )


def test_plain_chibi_animation_can_use_fast_preserve_mode():
    assert _can_preserve_source_animation(_action(False)) is True


def test_targeted_hsd_animation_stays_on_editable_rebuild_path():
    assert _can_preserve_source_animation(_action(True)) is False


def test_authored_action_without_source_snapshot_cannot_use_preserve_mode():
    assert _can_preserve_source_animation(
        SimpleNamespace(source_hsd_animation=None)) is False
