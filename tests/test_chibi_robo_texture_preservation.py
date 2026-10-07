"""Chibi-Robo lossless GX texture preservation regressions."""

from shared.IR.material import IRImage
from shared.IR.enums import GXTextureFormat, GXPaletteFormat
from shared.Constants.gx import GX_TF_CMPR, GX_TF_RGBA8
from exporter.phases.compose.helpers.materials import _build_image_node


class _Logger:
    def debug(self, *args, **kwargs):
        pass


def _image(**overrides):
    defaults = dict(
        name="tex",
        width=4,
        height=4,
        pixels=bytes([120, 80, 40, 255] * 16),
        image_id=1,
        palette_id=0,
        gx_format_override=GXTextureFormat.CMPR,
        palette_format_override=GXPaletteFormat.AUTO,
        source_raw_image_data=b"original-compressed-gx-blocks",
        source_raw_palette_data=None,
        source_format_id=GX_TF_CMPR,
        source_palette_format_id=None,
        source_palette_entry_count=0,
        source_pixel_hash="unused-at-compose",
    )
    defaults.update(overrides)
    return IRImage(**defaults)


def test_unchanged_source_texture_reuses_exact_gx_bytes():
    img, result = _build_image_node(_image(), logger=_Logger())
    assert img.format == GX_TF_CMPR
    assert img.raw_image_data == b"original-compressed-gx-blocks"
    assert result["image_data"] == b"original-compressed-gx-blocks"


def test_format_change_disables_source_gx_byte_reuse():
    ir = _image(gx_format_override=GXTextureFormat.RGBA8)
    img, result = _build_image_node(ir, logger=_Logger())
    assert img.format == GX_TF_RGBA8
    assert result["image_data"] != b"original-compressed-gx-blocks"
    assert len(result["image_data"]) > 0
