"""Regression coverage for HSD MObj render flags that are not shader semantics."""

from types import SimpleNamespace

from importer.phases.describe.helpers.materials import describe_material
from importer.phases.plan.helpers.materials import plan_material as import_plan_material
from exporter.phases.plan.helpers.materials import plan_material as export_plan_material
from exporter.phases.compose.helpers.materials import compose_material
from shared.Constants.hsd import (
    RENDER_DIFFUSE,
    RENDER_DIFFUSE_MAT,
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

    br = import_plan_material(source_ir, name="DepthWritingXLU")
    rebuilt_ir = export_plan_material(br)
    rebuilt = compose_material(rebuilt_ir)

    assert rebuilt.render_mode & RENDER_XLU
    assert not (rebuilt.render_mode & RENDER_NO_ZUPDATE)
