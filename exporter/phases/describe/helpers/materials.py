"""Snapshot Blender materials into BRMaterial dataclasses.

The shader node tree is serialised faithfully into a BRNodeGraph: every
node becomes a BRNode (node_type = bl_idname, input defaults captured by
socket identifier, type-specific attributes captured into ``properties``,
texture nodes carry a BRImage on ``image_ref``); every wire becomes a
BRLink keyed by socket identifier (see ``BRLink``). Plan
(`plan_material`) reads the graph and produces an IRMaterial — the
"is this material LIT, what does each texture layer mean, what blend
mode applies" interpretation lives entirely on the plan side.
"""
import base64
import binascii
import hashlib
import bpy

try:
    from .....shared.BR.materials import (
        BRMaterial, BRNodeGraph, BRNode, BRLink, BRImage,
    )
    from .....shared.helpers.logger import StubLogger
except (ImportError, SystemError):
    from shared.BR.materials import (
        BRMaterial, BRNodeGraph, BRNode, BRLink, BRImage,
    )
    from shared.helpers.logger import StubLogger


# Node attributes the plan-side decoder reads — captured into BRNode.properties
# so the decoder doesn't need a bpy node reference. Each entry is the bpy
# attribute name; the BR property uses the same key.
_NODE_PROPERTY_KEYS = {
    'ShaderNodeMath': ('operation',),
    'ShaderNodeMixRGB': ('blend_type',),
    'ShaderNodeVectorMath': ('operation',),
    'ShaderNodeTexImage': ('extension', 'interpolation'),
    'ShaderNodeAttribute': ('attribute_name',),
    'ShaderNodeUVMap': ('uv_map',),
}


def describe_material(blender_mat, logger=StubLogger(),
                      cache=None, image_cache=None):
    """Read one Blender material into a BRMaterial.

    In: blender_mat (bpy.types.Material with use_nodes=True); logger;
        cache (dict id(blender_mat) → BRMaterial; reuses the same
        instance for repeated calls so downstream dedup collapses
        DObjects sharing the material); image_cache (dict id(bpy_image)
        → BRImage; shared across materials so one image produces one
        BRImage instance).
    Out: BRMaterial, or None if the material lacks a node tree.
    """
    if not blender_mat or not blender_mat.use_nodes:
        return None

    cache_key = id(blender_mat)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    if image_cache is None:
        image_cache = {}

    node_graph = _serialise_node_graph(blender_mat.node_tree, image_cache)
    br = BRMaterial(
        name=blender_mat.name,
        node_graph=node_graph,
        use_backface_culling=blender_mat.use_backface_culling,
        blend_method=getattr(blender_mat, 'blend_method', None),
        dedup_key=(id(blender_mat),),
        source_color_source=blender_mat.get("dat_hsd_color_source"),
        source_alpha_source=blender_mat.get("dat_hsd_alpha_source"),
    )

    if cache is not None:
        cache[cache_key] = br
    return br


def _serialise_node_graph(node_tree, image_cache):
    nodes = [_serialise_node(n, image_cache) for n in node_tree.nodes]
    links = [
        BRLink(
            from_node=link.from_node.name,
            from_output=link.from_socket.identifier,
            to_node=link.to_node.name,
            to_input=link.to_socket.identifier,
        )
        for link in node_tree.links
    ]
    return BRNodeGraph(nodes=nodes, links=links)


def _serialise_node(node, image_cache):
    bl_idname = node.bl_idname

    properties = {}
    for attr in _NODE_PROPERTY_KEYS.get(bl_idname, ()):
        if hasattr(node, attr):
            properties[attr] = getattr(node, attr)

    # ShaderNodeRGB exposes its colour on outputs[0]. Capture it on
    # ``properties['color']`` so the plan-side decoder doesn't need to
    # touch bpy output sockets.
    if bl_idname == 'ShaderNodeRGB':
        properties['color'] = tuple(node.outputs[0].default_value)
    elif bl_idname == 'ShaderNodeValue':
        properties['value'] = float(node.outputs[0].default_value)

    # Unlinked input-socket defaults, keyed by socket identifier (the
    # single BR socket convention — unique even when names collide, e.g.
    # a VectorMath's 'Vector' / 'Vector_001'), so the plan can rebuild
    # e.g. a Mapping node's rotation / scale / translation.
    input_defaults = {}
    for inp in node.inputs:
        if inp.is_linked:
            continue
        try:
            value = inp.default_value
        except (AttributeError, RuntimeError):
            continue
        input_defaults[inp.identifier] = _coerce_default(value)

    image_ref = None
    if bl_idname == 'ShaderNodeTexImage' and node.image is not None:
        image_ref = _serialise_image(node.image, image_cache)

    return BRNode(
        node_type=bl_idname,
        name=node.name,
        properties=properties,
        input_defaults=input_defaults,
        image_ref=image_ref,
        location=tuple(node.location),
    )


def _coerce_default(value):
    """Turn a bpy default_value into a hashable / JSON-friendly Python
    value: floats stay floats, vectors/colours become tuples."""
    if hasattr(value, '__len__') and not isinstance(value, str):
        return tuple(float(c) for c in value)
    if isinstance(value, (int, float, bool, str)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _serialise_image(bpy_image, cache):
    key = id(bpy_image)
    cached = cache.get(key)
    if cached is not None:
        return cached

    width = bpy_image.size[0]
    height = bpy_image.size[1]
    pixel_count = width * height
    if pixel_count == 0:
        pixels = b''
    else:
        # Bulk float→u8 conversion: foreach_get reads the whole pixel
        # buffer in one C call, and the vectorized floor/clip matches the
        # scalar formula min(255, max(0, int(v * 255 + 0.5))) exactly.
        import numpy as np
        flat = np.empty(pixel_count * 4, dtype=np.float32)
        bpy_image.pixels.foreach_get(flat)
        scaled = np.floor(flat.astype(np.float64) * 255.0 + 0.5)
        pixels = np.clip(scaled, 0, 255).astype(np.uint8).tobytes()

    source_hash = bpy_image.get("dat_hsd_source_pixel_hash")
    source_raw_image = None
    source_raw_palette = None
    source_format_id = None
    source_palette_format_id = None
    source_palette_entry_count = 0

    # The custom source payload is valid only while the editable RGBA pixels
    # still reproduce the import-time hash. Any pixel edit automatically drops
    # to the normal GX encoder.
    current_hash = hashlib.sha256(pixels).hexdigest()
    if isinstance(source_hash, str) and source_hash == current_hash:
        try:
            raw_image = bpy_image.get("dat_hsd_source_image_b64")
            if isinstance(raw_image, str) and raw_image:
                source_raw_image = base64.b64decode(raw_image, validate=True)
            raw_palette = bpy_image.get("dat_hsd_source_palette_b64")
            if isinstance(raw_palette, str) and raw_palette:
                source_raw_palette = base64.b64decode(raw_palette, validate=True)
            value = bpy_image.get("dat_hsd_source_format_id")
            if value is not None:
                source_format_id = int(value)
            value = bpy_image.get("dat_hsd_source_palette_format_id")
            if value is not None:
                source_palette_format_id = int(value)
            source_palette_entry_count = int(
                bpy_image.get("dat_hsd_source_palette_entry_count", 0) or 0)
        except (ValueError, TypeError, binascii.Error):
            source_raw_image = None
            source_raw_palette = None
            source_format_id = None
            source_palette_format_id = None
            source_palette_entry_count = 0

    br_image = BRImage(
        name=bpy_image.name,
        width=width,
        height=height,
        pixels=pixels,
        cache_key=(key,),
        gx_format_override=getattr(bpy_image, 'dat_gx_format', 'AUTO') or 'AUTO',
        palette_format_override=getattr(bpy_image, 'dat_palette_format', 'AUTO') or 'AUTO',
        source_raw_image_data=source_raw_image,
        source_raw_palette_data=source_raw_palette,
        source_format_id=source_format_id,
        source_palette_format_id=source_palette_format_id,
        source_palette_entry_count=source_palette_entry_count,
        source_pixel_hash=(source_hash if source_raw_image is not None else None),
    )
    cache[key] = br_image
    return br_image
