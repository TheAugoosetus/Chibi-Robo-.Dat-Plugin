"""Lossless Chibi-Robo source-animation preservation regressions."""

from types import SimpleNamespace

from exporter.phases.compose.helpers.animations import _compose_source_anim_set
from shared.helpers.blender_fingerprint import (
    armature_rest_fingerprint, pose_action_fingerprint,
)
from importer.phases.post_process.post_process import (
    _stamp_source_skeleton_fingerprints,
)


class _Logger:
    def warning(self, *args, **kwargs):
        pass
    def debug(self, *args, **kwargs):
        pass


def test_compose_source_animation_keeps_raw_fobj_bytes():
    source = {
        "loop": True,
        "bones": [
            {
                "aj_flags": 0x1234,
                "animation": {
                    "flags": 1,
                    "end_frame": 39.0,
                    "has_joint_target": False,
                    "frames": [
                        {
                            "type": 2,
                            "start_frame": 0.0,
                            "frac_value": 0x66,
                            "frac_slope": 0x87,
                            "raw_ad": b"\x11\x22\x33\x44",
                        },
                        {
                            "type": 11,
                            "start_frame": -1.0,
                            "frac_value": 0x80,
                            "frac_slope": 0,
                            "raw_ad": b"\x55\x66",
                        },
                    ],
                },
            },
            {"aj_flags": 0, "animation": None},
        ],
    }
    bones = [
        SimpleNamespace(parent_index=None),
        SimpleNamespace(parent_index=0),
    ]

    root = _compose_source_anim_set(source, bones, _Logger())

    assert root.flags == 0x1234
    assert root.animation.flags == 1
    assert root.animation.end_frame == 39.0
    assert root.animation.frame.type == 2
    assert root.animation.frame.frac_value == 0x66
    assert root.animation.frame.frac_slope == 0x87
    assert root.animation.frame.raw_ad == b"\x11\x22\x33\x44"
    assert root.animation.frame.next.type == 11
    assert root.animation.frame.next.raw_ad == b"\x55\x66"
    assert root.child is not None
    assert root.child.animation is None


class _Point:
    def __init__(self, frame, value):
        self.co = (frame, value)
        self.interpolation = "LINEAR"
        self.handle_left_type = "FREE"
        self.handle_right_type = "FREE"
        self.handle_left = (frame - 0.25, value)
        self.handle_right = (frame + 0.25, value)


class _FCurve:
    def __init__(self, path, index, points):
        self.data_path = path
        self.array_index = index
        self.extrapolation = "CONSTANT"
        self.modifiers = []
        self.keyframe_points = points


class _Action:
    def __init__(self, curves):
        self.fcurves = curves


def test_pose_action_fingerprint_changes_when_pose_key_changes():
    action = _Action([
        _FCurve('pose.bones["Root"].rotation_euler', 0,
                [_Point(0.0, 0.0), _Point(10.0, 1.0)])
    ])
    before = pose_action_fingerprint(action)
    action.fcurves[0].keyframe_points[1].co = (10.0, 1.25)
    after = pose_action_fingerprint(action)
    assert before != after


def test_pose_action_fingerprint_ignores_non_pose_curves():
    pose = _FCurve('pose.bones["Root"].location', 0, [_Point(0.0, 0.0)])
    material = _FCurve('nodes["DiffuseColor"].outputs[0].default_value', 0,
                       [_Point(0.0, 0.5)])
    a = _Action([pose, material])
    baseline = pose_action_fingerprint(a)
    material.keyframe_points[0].co = (0.0, 0.9)
    assert pose_action_fingerprint(a) == baseline


class _ArmatureProps:
    def __init__(self, bones, game="CHIBI_ROBO"):
        self.type = "ARMATURE"
        self.data = SimpleNamespace(bones=bones)
        self._props = {"dat_game_origin": game}

    def get(self, key, default=None):
        return self._props.get(key, default)

    def __getitem__(self, key):
        return self._props[key]

    def __setitem__(self, key, value):
        self._props[key] = value


def _fingerprint_bone():
    return SimpleNamespace(
        name="Root",
        parent=None,
        matrix_local=[
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        inherit_scale="ALIGNED",
        use_connect=False,
    )


def test_post_process_refreshes_source_skeleton_fingerprint_after_rest_bake():
    bone = _fingerprint_bone()
    arm = _ArmatureProps([bone])
    original = armature_rest_fingerprint(arm)
    arm["dat_hsd_source_skeleton_fingerprint"] = original

    # Mirror the material fact that Armature.transform() changes the
    # armature-space rest matrix even when the user made no edit.
    bone.matrix_local[1][3] = 12.0
    current = armature_rest_fingerprint(arm)
    assert current != original

    _stamp_source_skeleton_fingerprints([arm])

    assert arm["dat_hsd_source_skeleton_fingerprint"] == current


def test_post_process_does_not_create_source_fingerprint_for_unmarked_armature():
    bone = _fingerprint_bone()
    arm = _ArmatureProps([bone])
    assert arm.get("dat_hsd_source_skeleton_fingerprint") is None

    _stamp_source_skeleton_fingerprints([arm])

    assert arm.get("dat_hsd_source_skeleton_fingerprint") is None


def test_post_process_does_not_restamp_non_chibi_armature():
    bone = _fingerprint_bone()
    arm = _ArmatureProps([bone], game="COLO_XD")
    arm["dat_hsd_source_skeleton_fingerprint"] = "sentinel"

    _stamp_source_skeleton_fingerprints([arm])

    assert arm["dat_hsd_source_skeleton_fingerprint"] == "sentinel"
