"""Regression coverage for HSD MObj render flags that are not shader semantics."""

from types import SimpleNamespace

from importer.phases.describe.helpers.materials import describe_material
from importer.phases.plan.helpers.materials import plan_material as import_plan_material
from exporter.phases.plan.helpers.materials import plan_material as export_plan_material
from exporter.phases.compose.helpers.materials import compose_material
from shared.Constants.hsd import (
    RENDER_DIFFUSE,
    RENDER_DIFFUSE_MAT,
    RENDER_DIFFUSE_VTX,
    RENDER_ALPHA_MAT,
    RENDER_NO_ZUPDATE,
    RENDER_XLU,
)


class _Color:
    def __init__(self, rgba):
        self.rgba = tuple(c / 255.0 for c in rgba)

    def asRGBAList(self):
        return list(self.rgba)


def _mobj(render_mode):
    material = SimpleNamespace(
        ambient=_Color((128, 128, 128, 255)),
        diffuse=_Color((179, 179, 179, 255)),
        specular=_Color((255, 255, 255, 255)),
        alpha=1.0,
        shininess=50.0,
    )
    return SimpleNamespace(
        address=0x100,
        render_mode=render_mode,
        material=material,
        texture=None,
        pixel_engine_data=None,
    )


def test_no_zupdate_survives_ir_br_ir_compose_round_trip():
    source_mode = (
        RENDER_DIFFUSE | RENDER_DIFFUSE_MAT | RENDER_ALPHA_MAT
        | RENDER_XLU | RENDER_NO_ZUPDATE
    )

    source_ir = describe_material(_mobj(source_mode))
    assert source_ir.is_translucent is True
    assert source_ir.no_depth_update is True

    br = import_plan_material(source_ir, name="BottleTop")
    assert br.source_no_depth_update is True

    rebuilt_ir = export_plan_material(br)
    assert rebuilt_ir.no_depth_update is True

    # XLU reconstruction from a Blender graph is covered separately; this
    # regression isolates the source NO_ZUPDATE bit we are preserving.
    rebuilt_ir.is_translucent = True
    rebuilt = compose_material(rebuilt_ir)
    assert rebuilt.render_mode & RENDER_XLU
    assert rebuilt.render_mode & RENDER_NO_ZUPDATE


def test_translucency_does_not_imply_no_zupdate():
    source_mode = (
        RENDER_DIFFUSE | RENDER_DIFFUSE_MAT | RENDER_ALPHA_MAT | RENDER_XLU
    )

    source_ir = describe_material(_mobj(source_mode))
    assert source_ir.is_translucent is True
    assert source_ir.no_depth_update is False

    rebuilt = compose_material(source_ir)

    assert rebuilt.render_mode & RENDER_XLU
    assert not (rebuilt.render_mode & RENDER_NO_ZUPDATE)


def test_vertex_only_source_diffuse_survives_pristine_round_trip():
    """Inactive Material.diffuse bytes are still source data.

    Chibi-Robo uses many VERTEX-only materials. Blender has no editable
    diffuse-color node for the unlit form, so a pristine round trip must
    restore the original Material.diffuse field from source metadata.
    """
    mobj = _mobj(RENDER_DIFFUSE_VTX | RENDER_ALPHA_MAT)
    mobj.material.diffuse = _Color((89, 255, 47, 255))

    source_ir = describe_material(mobj)
    assert source_ir.color_source.value == "VERTEX"

    br = import_plan_material(source_ir, name="VertexDiffuse")
    assert br.source_diffuse_color == source_ir.diffuse_color

    # The real Blender describe phase sets this only when the imported graph
    # fingerprint still matches. Mark the pure BR fixture equivalently.
    br.source_routing_pristine = True
    rebuilt_ir = export_plan_material(br)

    for actual, expected in zip(rebuilt_ir.diffuse_color, source_ir.diffuse_color):
        assert abs(actual - expected) < 1e-9


def test_vertex_only_source_diffuse_is_not_forced_after_routing_edit():
    """Once routing is edited, stale source metadata must stop overriding it."""
    mobj = _mobj(RENDER_DIFFUSE_VTX | RENDER_ALPHA_MAT)
    mobj.material.diffuse = _Color((89, 255, 47, 255))

    source_ir = describe_material(mobj)
    br = import_plan_material(source_ir, name="EditedVertexDiffuse")
    br.source_routing_pristine = False

    rebuilt_ir = export_plan_material(br)
    assert rebuilt_ir.diffuse_color != source_ir.diffuse_color
