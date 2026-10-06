"""Chibi-Robo animation alias and source-channel regressions."""

from types import SimpleNamespace

from importer.phases.describe.describe import _deduplicate_chibi_animation_slots
from importer.phases.plan.helpers.animations import _source_channel_mask
from exporter.phases.compose.helpers.animations import compose_bone_animations


class _Logger:
    def info(self, *args, **kwargs):
        pass


def test_chibi_animation_slots_collapse_repeated_roots():
    a = SimpleNamespace(address=0x100)
    b = SimpleNamespace(address=0x200)
    c = SimpleNamespace(address=0x300)
    model_set = SimpleNamespace(
        root_joint=object(),
        animated_joints=[a, b, a, a, c],
        animated_material_joints=[],
        animated_shape_joints=[],
    )

    dedup, slot_map = _deduplicate_chibi_animation_slots(model_set, _Logger())

    assert dedup.animated_joints == [a, b, c]
    assert slot_map == [0, 1, 0, 0, 2]


def test_chibi_alias_collapse_skips_parallel_material_animation_roots():
    a = SimpleNamespace(address=0x100)
    m = SimpleNamespace(address=0x500)
    model_set = SimpleNamespace(
        root_joint=object(),
        animated_joints=[a, a],
        animated_material_joints=[m],
        animated_shape_joints=[],
    )

    dedup, slot_map = _deduplicate_chibi_animation_slots(model_set, _Logger())

    assert dedup is model_set
    assert slot_map == []


def test_source_channel_mask_tracks_only_authored_axes():
    track = SimpleNamespace(
        bone_name="Bone_01",
        rotation=[[object()], [], [object()]],
        location=[[], [object()], []],
        scale=[[], [], [object()]],
    )

    # R.X bit0, R.Z bit2, L.Y bit4, S.Z bit8
    assert _source_channel_mask(track) == (
        (1 << 0) | (1 << 2) | (1 << 4) | (1 << 8)
    )


def test_compose_animation_slot_map_reuses_node_identity():
    anim = SimpleNamespace(tracks=[], loop=False)
    bones = [SimpleNamespace(parent_index=None)]
    roots = compose_bone_animations(
        [anim], joints=[object()], bones=bones, logger=_Logger(),
        slot_map=[0, 0, 0],
    )

    assert len(roots) == 3
    assert roots[0] is roots[1]
    assert roots[1] is roots[2]
