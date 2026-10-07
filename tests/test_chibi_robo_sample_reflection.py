"""Regressions derived from stock sample.dat vs Deluxe icon_sample.dat.

The pre-fork importer/exporter kept Sample's reflection TObj and specular
material but changed three pieces of HSD state:
  * JOBJ TEXGEN/SPECULAR flags were lost on mesh-owning joints;
  * reflection TObj X rotation gained an unintended -pi/2;
  * a stock repeat_s=3 UV layer came back as repeat_s=1.

These tests guard the two material-graph conversion errors. JOBJ flag
preservation is covered in test_chibi_robo_roundtrip_metadata.py.
"""
import math

from shared.BR.materials import BRImage, BRNode, BRNodeGraph, BRLink
from shared.IR.enums import CoordType
from exporter.phases.plan.helpers.materials import (
    _GraphView, _describe_texture_node,
)


def _image():
    return BRImage(
        name="sample_tex",
        width=4,
        height=4,
        pixels=bytes([255, 255, 255, 255] * 16),
        cache_key=("sample", 0),
    )


def _view(nodes, links):
    return _GraphView(BRNodeGraph(nodes=nodes, links=links))


def test_sample_reflection_mapping_undoes_blender_minus_pi_over_two():
    texcoord = BRNode(
        node_type="ShaderNodeTexCoord",
        name="coord",
    )
    mapping = BRNode(
        node_type="ShaderNodeMapping",
        name="mapping",
        input_defaults={
            "Location": (0.0, 0.0, 0.0),
            "Rotation": (-math.pi / 2, 0.0, 0.0),
            "Scale": (1.0, 1.0, 1.0),
        },
    )
    tex = BRNode(
        node_type="ShaderNodeTexImage",
        name="tex",
        properties={"extension": "EXTEND"},
        image_ref=_image(),
    )
    links = [
        BRLink("coord", "Reflection", "mapping", "Vector"),
        BRLink("mapping", "Vector", "tex", "Vector"),
    ]

    layer = _describe_texture_node(
        _view([texcoord, mapping, tex], links),
        tex,
        0,
        {},
        [],
    )

    assert layer.coord_type == CoordType.REFLECTION
    assert math.isclose(layer.rotation[0], 0.0, abs_tol=1e-6)
    assert math.isclose(layer.rotation[1], 0.0, abs_tol=1e-6)
    assert math.isclose(layer.rotation[2], 0.0, abs_tol=1e-6)


def test_sample_repeat_multiplier_is_found_before_mapping_node():
    uv = BRNode(
        node_type="ShaderNodeUVMap",
        name="uv",
        properties={"uv_map": "uvtex_0"},
    )
    repeat = BRNode(
        node_type="ShaderNodeVectorMath",
        name="repeat",
        properties={"operation": "MULTIPLY"},
        input_defaults={
            "Vector": (0.0, 0.0, 0.0),
            "Vector_001": (3.0, 1.0, 1.0),
        },
    )
    mapping = BRNode(
        node_type="ShaderNodeMapping",
        name="mapping",
        input_defaults={
            "Location": (0.0, 0.0, 0.0),
            "Rotation": (0.0, 0.0, 0.0),
            "Scale": (1.0, 1.0, 1.0),
        },
    )
    tex = BRNode(
        node_type="ShaderNodeTexImage",
        name="tex",
        properties={"extension": "REPEAT"},
        image_ref=_image(),
    )
    links = [
        BRLink("uv", "UV", "repeat", "Vector"),
        BRLink("repeat", "Vector", "mapping", "Vector"),
        BRLink("mapping", "Vector", "tex", "Vector"),
    ]

    layer = _describe_texture_node(
        _view([uv, repeat, mapping, tex], links),
        tex,
        0,
        {},
        ["uvtex_0"],
    )

    assert layer.repeat_s == 3
    assert layer.repeat_t == 1
