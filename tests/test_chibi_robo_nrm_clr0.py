"""Chibi-Robo NRM+CLR0 geometry regressions."""

from shared.IR.geometry import IRMesh, IRUVLayer, IRColorLayer
from shared.Constants.gx import (
    GX_VA_POS, GX_VA_NRM, GX_VA_CLR0, GX_VA_TEX0,
)
from exporter.phases.compose.helpers.meshes import _build_pobj


class _Logger:
    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


def _mesh():
    return IRMesh(
        name="nrm_clr0_tex0",
        vertices=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
        ],
        faces=[[0, 1, 2]],
        normals=[
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0),
            (0.0, 0.0, 1.0),
        ],
        color_layers=[
            IRColorLayer(
                name="color_0",
                colors=[
                    (1.0, 0.0, 0.0, 1.0),
                    (0.0, 1.0, 0.0, 1.0),
                    (0.0, 0.0, 1.0, 1.0),
                ],
            ),
        ],
        uv_layers=[
            IRUVLayer(
                name="uvtex_0",
                uvs=[
                    (0.0, 0.0),
                    (1.0, 0.0),
                    (0.0, 1.0),
                ],
            ),
        ],
    )


def test_nrm_clr0_tex0_uses_canonical_gx_attribute_order():
    pobjs = _build_pobj(_mesh(), [], [], {}, _Logger())
    attrs = [v.attribute for v in pobjs[0].vertex_list.vertices]

    assert attrs == [
        GX_VA_POS,
        GX_VA_NRM,
        GX_VA_CLR0,
        GX_VA_TEX0,
    ]
