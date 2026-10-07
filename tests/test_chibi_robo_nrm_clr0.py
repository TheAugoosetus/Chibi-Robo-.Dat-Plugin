"""Chibi-Robo NRM+CLR0 geometry regressions."""

from shared.IR.geometry import IRMesh, IRUVLayer, IRColorLayer
from shared.Constants.gx import (
    GX_VA_POS, GX_VA_NRM, GX_VA_CLR0, GX_VA_TEX0,
    GX_INDEX8, GX_S8, GX_NRM_XYZ,
)
from shared.BR.materials import BRMaterial, BRNode, BRNodeGraph, BRLink
from shared.IR.enums import ColorSource
from importer.phases.describe.helpers.meshes import _extract_normals
from exporter.phases.plan.helpers.materials import (
    _GraphView, _detect_color_sources, plan_material,
)
from exporter.phases.compose.helpers.meshes import _encode_indexed_source_numeric
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


def test_source_fixed_point_normal_is_not_destroyed_by_blender_normalization_path():
    source = [(31 / 64, -10 / 64, 54 / 64)]
    face_list = [[0]]
    faces = [[0]]

    exact = _extract_normals(
        source, face_list, faces, normalize=False)
    display = _extract_normals(
        source, face_list, faces, normalize=True)

    assert exact == source
    assert display != source

    fmt = {
        "attribute": GX_VA_NRM,
        "attribute_type": GX_INDEX8,
        "component_count": GX_NRM_XYZ,
        "component_type": GX_S8,
        "component_frac": 6,
        "stride": 3,
    }
    encoded = _encode_indexed_source_numeric(exact, fmt, 3)
    assert encoded is not None
    _unique, indices, raw = encoded
    assert indices == [0]
    assert raw == bytes((31, 246, 54))


def _routing_view(diffuse=(1.0, 1.0, 1.0, 1.0), alpha=1.0):
    nodes = [
        BRNode(
            node_type="ShaderNodeRGB",
            name="DiffuseColor",
            properties={"color": diffuse},
        ),
        BRNode(
            node_type="ShaderNodeValue",
            name="AlphaValue",
            properties={"value": alpha},
        ),
        BRNode(
            node_type="ShaderNodeAttribute",
            name="color_attr",
            properties={"attribute_name": "color_0"},
        ),
        BRNode(
            node_type="ShaderNodeAttribute",
            name="alpha_attr",
            properties={"attribute_name": "alpha_0"},
        ),
        BRNode(
            node_type="ShaderNodeMixRGB",
            name="color_mix",
        ),
        BRNode(
            node_type="ShaderNodeMixRGB",
            name="alpha_mix",
        ),
    ]
    links = [
        BRLink("color_attr", "Color", "color_mix", "Color1"),
        BRLink("DiffuseColor", "Color", "color_mix", "Color2"),
        BRLink("alpha_attr", "Color", "alpha_mix", "Color1"),
        BRLink("AlphaValue", "Value", "alpha_mix", "Color2"),
    ]
    return _GraphView(BRNodeGraph(nodes=nodes, links=links))


def test_imported_vertex_only_routing_does_not_become_both():
    color_source, alpha_source = _detect_color_sources(
        _routing_view(),
        source_color_source="VERTEX",
        source_alpha_source="VERTEX",
    )
    assert color_source == ColorSource.VERTEX
    assert alpha_source == ColorSource.VERTEX


def test_editing_vertex_only_material_helper_falls_back_to_both():
    color_source, alpha_source = _detect_color_sources(
        _routing_view(diffuse=(0.5, 0.5, 0.5, 1.0), alpha=0.5),
        source_color_source="VERTEX",
        source_alpha_source="VERTEX",
    )
    assert color_source == ColorSource.BOTH
    assert alpha_source == ColorSource.BOTH


def _routing_material(pristine, diffuse=(1.0, 1.0, 1.0, 1.0), alpha=1.0):
    view = _routing_view(diffuse=diffuse, alpha=alpha)
    return BRMaterial(
        name="routing",
        node_graph=view.graph,
        source_color_source="VERTEX",
        source_alpha_source="VERTEX",
        source_routing_pristine=pristine,
    )


def test_plan_uses_vertex_only_source_hint_only_while_routing_is_pristine():
    ir = plan_material(_routing_material(True), logger=_Logger())
    assert ir.color_source == ColorSource.VERTEX
    assert ir.alpha_source == ColorSource.VERTEX


def test_plan_ignores_stale_vertex_only_source_hint_after_graph_edit():
    ir = plan_material(
        _routing_material(
            False,
            diffuse=(0.5, 0.5, 0.5, 1.0),
            alpha=0.5,
        ),
        logger=_Logger(),
    )
    assert ir.color_source == ColorSource.BOTH
    assert ir.alpha_source == ColorSource.BOTH
