"""Stable fingerprints for imported Blender armatures and Actions.

These fingerprints are used only as change detectors for source-preservation
metadata. They are deliberately independent of Blender object identity and
custom properties: if the editable bone rest data or pose F-curves change,
the digest changes and the exporter falls back to rebuilding HSD data.
"""
import hashlib
import struct


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
