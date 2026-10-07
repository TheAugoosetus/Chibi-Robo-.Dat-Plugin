"""Regression tests for exact DAT normal preservation fingerprints."""

from types import SimpleNamespace

from shared.Constants.hsd import JOBJ_LIGHTING, JOBJ_SKELETON
from shared.helpers.blender_fingerprint import mesh_normal_fingerprint


def _identity():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


class _Props:
    def __init__(self, **props):
        self._props = dict(props)

    def get(self, key, default=None):
        return self._props.get(key, default)


class _Bone(_Props):
    def __init__(self, name="root", parent=None, matrix_local=None,
                 flags=0):
        super().__init__(dat_hsd_flags=flags)
        self.name = name
        self.parent = parent
        self.matrix_local = matrix_local or _identity()
        self.inherit_scale = "ALIGNED"
        self.use_connect = False


class _MeshObject(_Props):
    def __init__(self):
        super().__init__(dat_hsd_skin_type="WEIGHTED")

        self._assignment = SimpleNamespace(group=0, weight=1.0)
        vertex = SimpleNamespace(
            co=(1.0, 2.0, 3.0),
            groups=[self._assignment],
        )
        polygon = SimpleNamespace(vertices=(0,))
        corner = SimpleNamespace(vector=(0.0, 0.0, 1.0))
        self.data = SimpleNamespace(
            vertices=[vertex],
            polygons=[polygon],
            corner_normals=[corner],
        )

        self.vertex_groups = [
            SimpleNamespace(index=0, name="root"),
        ]
        self.matrix_world = _identity()
        self.parent_bone = "root"

        self.bone = _Bone()
        self.parent = SimpleNamespace(
            type="ARMATURE",
            data=SimpleNamespace(bones=[self.bone]),
        )


def test_normal_fingerprint_is_stable_when_state_is_unchanged():
    obj = _MeshObject()
    assert mesh_normal_fingerprint(obj) == mesh_normal_fingerprint(obj)


def test_normal_fingerprint_changes_when_owner_bone_changes():
    obj = _MeshObject()
    before = mesh_normal_fingerprint(obj)
    obj.parent_bone = "other"
    assert mesh_normal_fingerprint(obj) != before


def test_normal_fingerprint_changes_when_skin_type_changes():
    obj = _MeshObject()
    before = mesh_normal_fingerprint(obj)
    obj._props["dat_hsd_skin_type"] = "RIGID"
    assert mesh_normal_fingerprint(obj) != before


def test_normal_fingerprint_changes_when_vertex_weight_changes():
    obj = _MeshObject()
    before = mesh_normal_fingerprint(obj)
    obj._assignment.weight = 0.75
    assert mesh_normal_fingerprint(obj) != before


def test_normal_fingerprint_changes_when_rest_bone_matrix_changes():
    obj = _MeshObject()
    before = mesh_normal_fingerprint(obj)
    obj.bone.matrix_local[0][3] = 4.0
    assert mesh_normal_fingerprint(obj) != before


def test_normal_fingerprint_changes_when_hsd_skeleton_flags_change():
    obj = _MeshObject()
    before = mesh_normal_fingerprint(obj)
    obj.bone._props["dat_hsd_flags"] = JOBJ_SKELETON
    assert mesh_normal_fingerprint(obj) != before


def test_normal_fingerprint_ignores_render_only_hsd_flag_changes():
    obj = _MeshObject()
    before = mesh_normal_fingerprint(obj)
    obj.bone._props["dat_hsd_flags"] = JOBJ_LIGHTING
    assert mesh_normal_fingerprint(obj) == before
