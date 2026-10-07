"""Chibi-Robo source vertex-color preservation regressions."""

from shared.IR.geometry import IRMesh, IRColorLayer
from shared.Constants.gx import (
    GX_VA_CLR0, GX_INDEX8, GX_RGBA8,
)
from exporter.phases.compose.helpers.meshes import _build_pobj


class _Logger:
    def warning(self, *args, **kwargs):
        pass
    def debug(self, *args, **kwargs):
        pass


def _mesh(source_color=False):
    formats = []
    if source_color:
        formats.append({
            "attribute": GX_VA_CLR0,
            "attribute_type": GX_INDEX8,
            "component_count": 1,
            "component_type": GX_RGBA8,
            "component_frac": 0,
            "stride": 4,
        })
    return IRMesh(
        name="bird_constant_color",
        vertices=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        faces=[[0, 1, 2]],
        color_layers=[
            IRColorLayer(
                name="color_0",
                colors=[(195 / 255, 121 / 255, 121 / 255, 1.0)] * 3,
            )
        ],
        source_vertex_formats=formats,
    )


def _attributes(pobj):
    return {v.attribute: v for v in pobj.vertex_list.vertices}


def test_uniform_source_clr0_is_preserved():
    pobjs = _build_pobj(_mesh(True), [], [], {}, _Logger())
    attrs = _attributes(pobjs[0])
    assert GX_VA_CLR0 in attrs
    assert attrs[GX_VA_CLR0].attribute_type == GX_INDEX8
    assert attrs[GX_VA_CLR0].component_type == GX_RGBA8
    assert attrs[GX_VA_CLR0].stride == 4
    assert attrs[GX_VA_CLR0].raw_vertex_data == bytes((195, 121, 121, 255))


def test_uniform_new_blender_color_can_still_be_material_default():
    pobjs = _build_pobj(_mesh(False), [], [], {}, _Logger())
    assert GX_VA_CLR0 not in _attributes(pobjs[0])
