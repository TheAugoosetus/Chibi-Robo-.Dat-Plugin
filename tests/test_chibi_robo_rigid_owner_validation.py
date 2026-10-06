"""Chibi-Robo export validation regressions."""

import pytest

from exporter.phases.pre_process.pre_process import _check_mesh_owner_disjoint


class _Bone:
    def __init__(self, name, parent=None):
        self.name = name
        self.parent = parent


class _ArmData:
    def __init__(self, bones):
        self.bones = bones


class _Arm:
    def __init__(self, bones):
        self.data = _ArmData(bones)


class _GroupRef:
    def __init__(self, group, weight):
        self.group = group
        self.weight = weight


class _Vertex:
    def __init__(self, groups):
        self.groups = groups


class _MeshData:
    def __init__(self, vertices):
        self.vertices = vertices


class _VertexGroup:
    def __init__(self, index, name):
        self.index = index
        self.name = name


class _Mesh:
    def __init__(self, source_skin=None):
        self.name = "Mesh"
        self.vertex_groups = [_VertexGroup(0, "Root")]
        self.data = _MeshData([_Vertex([_GroupRef(0, 1.0)])])
        self.parent_type = "BONE"
        self.parent_bone = "Root"
        self._props = {}
        if source_skin is not None:
            self._props["dat_hsd_skin_type"] = source_skin

    def get(self, key, default=None):
        return self._props.get(key, default)


def _scene(source_skin):
    root = _Bone("Root")
    arm = _Arm([root])
    mesh = _Mesh(source_skin)
    return {arm: [mesh]}


def test_imported_rigid_group_is_not_an_envelope_deformer():
    # The importer creates a 1.0 vertex group so Blender can attach a rigid
    # mesh to its source bone. That group is not POBJ_ENVELOPE and must not
    # force a synthetic holder JOBJ.
    _check_mesh_owner_disjoint(_scene("RIGID"))


def test_imported_single_bound_group_is_not_an_envelope_deformer():
    _check_mesh_owner_disjoint(_scene("SINGLE_BONE"))


def test_imported_weighted_group_still_enforces_disjointness():
    with pytest.raises(ValueError, match="Mesh owner bone"):
        _check_mesh_owner_disjoint(_scene("WEIGHTED"))


def test_authored_group_without_source_metadata_still_enforces_disjointness():
    with pytest.raises(ValueError, match="Mesh owner bone"):
        _check_mesh_owner_disjoint(_scene(None))
