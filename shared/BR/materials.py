from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class BRImage:
    """Image data ready to populate ``bpy.data.images``.

    Build uses ``cache_key`` to dedup across materials — multiple BRMaterials
    can reference the same image via their BRNode.image_ref, and only one
    bpy image is created.
    """
    name: str
    width: int
    height: int
    pixels: bytes                      # raw RGBA uint8
    cache_key: tuple                   # (image_id, palette_id) — dedup identity
    alpha_mode: str = 'CHANNEL_PACKED'
    pack: bool = True
    gx_format_override: str | None = None  # stored on bpy_image.dat_gx_format
    palette_format_override: str | None = None  # stored on bpy_image.dat_palette_format
    source_raw_image_data: bytes | None = None
    source_raw_palette_data: bytes | None = None
    source_format_id: int | None = None
    source_palette_format_id: int | None = None
    source_palette_entry_count: int = 0
    source_pixel_hash: str | None = None


@dataclass
class BRNode:
    """One shader node spec — a direct mirror of a bpy shader node.

    ``node_type`` is the Blender bl_idname (e.g. ``ShaderNodeMath``).
    ``properties`` are type-specific attributes set via ``setattr`` on the
    bpy node (e.g. ``{'operation': 'ADD', 'use_clamp': True}``).
    ``input_defaults`` sets the ``default_value`` of input sockets, keyed
    by socket identifier (see ``BRLink``). Linked inputs override defaults
    at evaluation. ``image_ref`` is populated only for ``ShaderNodeTexImage``
    nodes.
    """
    node_type: str
    name: str
    properties: dict[str, object] = field(default_factory=dict)
    input_defaults: dict[object, object] = field(default_factory=dict)
    image_ref: BRImage | None = None
    location: tuple[float, float] | None = None


@dataclass
class BRLink:
    """One graph link — socket-to-socket connection between two BRNodes.

    Sockets are referenced by their Blender socket *identifier* (a string)
    — the single convention. The identifier is unique within a node even
    when display names collide (a Math node's three inputs are 'Value' /
    'Value_001' / 'Value_002'), so it's the only collision-free key.
    ``build_blender`` resolves it via ``socket.identifier``; the importer
    plan's ``BRGraphBuilder`` maps construction-time integer indices to it.
    """
    from_node: str           # BRNode.name
    from_output: str         # output socket identifier on from_node
    to_node: str
    to_input: str            # input socket identifier on to_node


@dataclass
class BRNodeGraph:
    """A shader node graph: nodes + links. No implicit output — the
    ShaderNodeOutputMaterial is an explicit node in ``nodes``."""
    nodes: list[BRNode] = field(default_factory=list)
    links: list[BRLink] = field(default_factory=list)


@dataclass
class BRMaterial:
    """One Blender material spec: name + graph + material-level Blender
    properties. Every decision about how to construct the shader is
    baked in; the build phase is a mechanical walker.
    """
    name: str
    node_graph: BRNodeGraph
    use_backface_culling: bool = False
    blend_method: str | None = None       # 'OPAQUE' / 'HASHED' / 'BLEND'
    # Dedup key used by build to share one bpy material between meshes.
    # A plan-time constructed tuple like (id(ir_material), cull_f, cull_b).
    dedup_key: object = None
    # Original HSD MObj color/alpha routing. Blender's node graph can be
    # semantically ambiguous (especially a lit VERTEX source represented by
    # a white helper RGB node), so imported materials carry this hint.
    source_color_source: str | None = None
    source_alpha_source: str | None = None
    source_routing_pristine: bool = False
