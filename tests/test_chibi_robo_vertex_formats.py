"""Chibi-Robo GX vertex-format preservation regressions."""

from types import SimpleNamespace

from shared.Constants.gx import (
    GX_VA_POS, GX_VA_NRM, GX_VA_CLR0, GX_VA_TEX0,
    GX_INDEX8, GX_INDEX16,
    GX_S8, GX_S16, GX_POS_XYZ, GX_NRM_XYZ,
)
from shared.IR.enums import LightingModel, CoordType
from exporter.phases.compose.helpers.meshes import (
    _encode_source_numeric_buffer,
    _encode_indexed_source_numeric,
    _make_vertex_desc_from_source,
    _should_export_normal_attribute,
)


def _fmt(attribute, attribute_type, component_count, component_type,
         component_frac, stride):
    return {
        "attribute": attribute,
        "attribute_type": attribute_type,
        "component_count": component_count,
        "component_type": component_type,
        "component_frac": component_frac,
        "stride": stride,
    }


def test_chibi_s16_positions_keep_six_byte_stride():
    fmt = _fmt(GX_VA_POS, GX_INDEX16, GX_POS_XYZ, GX_S16, 12, 6)
    values = [(1.0, -2.0, 0.5), (0.25, 0.0, -0.25)]

    encoded = _encode_source_numeric_buffer(values, fmt, 3)
    assert encoded is not None
    _stored, raw = encoded
    assert len(raw) == len(values) * 6

    desc = _make_vertex_desc_from_source(
        GX_VA_POS, fmt, len(values), GX_POS_XYZ, 4, 12)
    assert desc.component_type == GX_S16
    assert desc.component_frac == 12
    assert desc.stride == 6
    assert desc.attribute_type == GX_INDEX16


def test_chibi_s8_normals_deduplicate_on_quantized_grid():
    fmt = _fmt(GX_VA_NRM, GX_INDEX8, GX_NRM_XYZ, GX_S8, 6, 3)
    # Both values quantize to the same S8:6 normal.
    values = [(1.0, 0.0, 0.0), (0.9999, 0.0, 0.0)]

    encoded = _encode_indexed_source_numeric(values, fmt, 3)
    assert encoded is not None
    unique, indices, raw = encoded
    assert len(unique) == 1
    assert indices == [0, 0]
    assert len(raw) == 3


def test_index8_promotes_when_edited_mesh_exceeds_256_entries():
    fmt = _fmt(GX_VA_NRM, GX_INDEX8, GX_NRM_XYZ, GX_S8, 6, 3)
    desc = _make_vertex_desc_from_source(
        GX_VA_NRM, fmt, 257, GX_NRM_XYZ, 4, 12)
    assert desc.attribute_type == GX_INDEX16


def test_source_fixed_point_falls_back_if_edited_value_overflows():
    fmt = _fmt(GX_VA_NRM, GX_INDEX16, GX_NRM_XYZ, GX_S8, 6, 3)
    # 3.0 * 64 = 192, outside signed 8-bit.
    assert _encode_source_numeric_buffer([(3.0, 0.0, 0.0)], fmt, 3) is None



def _source_fmt(attribute):
    return {
        "attribute": attribute,
        "attribute_type": GX_INDEX16,
        "component_count": 0,
        "component_type": GX_S16,
        "component_frac": 0,
        "stride": 4,
    }


def _material(*, lit=False, specular=False, reflection=False, bump=False):
    layers = []
    if reflection or bump:
        layers.append(SimpleNamespace(
            coord_type=CoordType.REFLECTION if reflection else CoordType.UV,
            is_bump=bump,
        ))
    return SimpleNamespace(
        lighting=LightingModel.LIT if lit else LightingModel.UNLIT,
        enable_specular=specular,
        texture_layers=layers,
    )


def test_source_mesh_without_normal_descriptor_keeps_normals_omitted():
    mesh = SimpleNamespace(
        source_vertex_formats=[
            _source_fmt(GX_VA_POS),
            _source_fmt(GX_VA_CLR0),
            _source_fmt(GX_VA_TEX0),
        ],
        material=_material(),
    )
    assert _should_export_normal_attribute(mesh) is False


def test_source_mesh_without_normals_adds_them_if_material_now_needs_them():
    for mat in (
        _material(lit=True),
        _material(specular=True),
        _material(reflection=True),
        _material(bump=True),
    ):
        mesh = SimpleNamespace(
            source_vertex_formats=[
                _source_fmt(GX_VA_POS),
                _source_fmt(GX_VA_CLR0),
                _source_fmt(GX_VA_TEX0),
            ],
            material=mat,
        )
        assert _should_export_normal_attribute(mesh) is True


def test_new_mesh_without_source_formats_exports_blender_normals():
    mesh = SimpleNamespace(
        source_vertex_formats=[],
        material=_material(),
    )
    assert _should_export_normal_attribute(mesh) is True
