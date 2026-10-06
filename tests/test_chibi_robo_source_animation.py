"""Lossless Chibi-Robo source-animation preservation regressions."""

from types import SimpleNamespace

from exporter.phases.compose.helpers.animations import _compose_source_anim_set
from shared.helpers.blender_fingerprint import pose_action_fingerprint


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
