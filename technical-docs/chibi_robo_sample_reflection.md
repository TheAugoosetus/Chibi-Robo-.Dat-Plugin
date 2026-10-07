# Chibi-Robo Sample Reflection Round-Trip

This note records the comparison between the stock Chibi-Robo `sample.dat`
and the Deluxe-era `title_icon/icon_sample.dat` produced with the older,
pre-fork Blender importer/exporter.

The goal is not to make exported files byte-identical in every respect. It is
to identify which HSD semantics caused Sample's reflective body to disappear
and make those semantics survive the Chibi-Robo profile.

## High-level structural difference

| Property | stock sample.dat | old icon_sample.dat |
| --- | ---: | ---: |
| file size | 84,523 bytes | 130,383 bytes |
| JOBJ count | 20 | 40 |
| mesh-owning JOBJ count | 20 | 20 |
| skinning | rigid | envelope |
| synthetic mesh-holder JOBJs | 0 | 20 |
| embedded camera | present | absent |
| embedded lights | 2 | 0 |

The old exporter moved the meshes away from their original rigid JOBJs and
onto synthetic envelope/holder JOBJs. This is the same generic-exporter
conversion seen in the Deluxe Army3/4/5 title icons.

## Reflective JOBJ state

A representative stock reflective Sample mesh owner uses:

```
0x10050180
```

which contains:

```
JOBJ_ROOT_OPA
JOBJ_OPA
JOBJ_SPECULAR
JOBJ_TEXGEN
JOBJ_LIGHTING
```

The corresponding old-export mesh holders use:

```
0x10040084
```

which contains opaque/root-opaque/lighting plus envelope-model state, but no
`JOBJ_SPECULAR` or `JOBJ_TEXGEN`.

This is the strongest structural explanation for the lost reflective body.
The older exporter discarded renderer-level JOBJ metadata when it rebuilt the
Blender hierarchy.

The Chibi-Robo fork now preserves the exact source JOBJ flag word for imported
DAT joints. For new Blender-authored Chibi models, it also derives:

- `JOBJ_SPECULAR` when the material enables specular lighting.
- `JOBJ_TEXGEN` when a texture layer uses generated coordinates such as
  reflection instead of ordinary mesh UVs.

## Material and reflection texture state

The old exporter did *not* completely remove the reflective material.

The compared files retain the important MObj/TObj semantics:

- specular render mode remains enabled;
- specular colour remains white;
- Sample shininess values remain present;
- the reflection TObj remains `TEX_COORD_REFLECTION`;
- the principal reflection layer retains its 0.5 blend value;
- the 64x64 CMPR reflection image remains present.

Therefore the failure was not simply "reflection texture deleted." It was a
combination of lost JOBJ state and additional round-trip conversion errors.

## Reflection transform error

Stock Sample reflection TObjs use an X rotation of 0.

The old `icon_sample.dat` contains approximately:

```
X = -pi / 2
Y = 0
Z = 0
```

The importer intentionally subtracts pi/2 from reflection X rotation to map
HSD reflection coordinates into Blender's Reflection-vector convention. The
old exporter read that Blender adjustment back as though it were game data.

The Chibi exporter now adds pi/2 back when reconstructing a reflection TObj,
making the import-side display transform reversible.

## Texture-repeat error

At least one stock Sample texture layer uses:

```
repeat_s = 3
repeat_t = 1
```

The old export changed this to 1 x 1.

The importer represents repeat as:

```
UV / Reflection
    -> VectorMath(MULTIPLY)
    -> Mapping
    -> Image Texture
```

The old exporter only inspected the Image Texture's immediate Vector input.
Because the immediate node is Mapping, it never saw the upstream multiplier.

The Chibi exporter now searches upstream of Mapping and recovers the original
repeat values.

## Texture recompression

The stock Sample 64x64 CMPR reflection image and the old exported image decode
to the same intended artwork, but their compressed GX byte streams differ.
The old workflow decoded the image into Blender pixels and recompressed it
during export.

The Chibi fork now stores the source GX image/TLUT payload beside the editable
Blender image. If the pixels and format remain unchanged, export reuses the
exact source compressed blocks. If the user edits the image or changes its
format, normal re-encoding is used.

## Camera and lights

Stock `sample.dat` contains a camera and two lights. The old
`icon_sample.dat` contains neither.

This omission is common across the Deluxe-era title icons created with the old
addon. It is a fidelity difference, but it is not currently identified as the
primary cause of Sample's lost reflection:

- the Deluxe-era title icons function in-game without their embedded
  camera/light objects;
- reflection-coordinate generation is present in the model material itself;
- the old Sample export demonstrably lost the stock TEXGEN/SPECULAR JOBJ flags
  and altered the reflection TObj transform.

The current fork already imports and exports SceneData cameras and lights, so
stock files can retain them. No Sample-specific camera/light workaround is
needed.

## Regression coverage

The Chibi branch now has regressions for:

- exact preservation of Sample's source reflective JOBJ flags;
- derivation of TEXGEN/SPECULAR for newly-authored reflective Chibi materials;
- reversal of the Blender -pi/2 reflection rotation adjustment;
- recovery of texture-repeat multipliers upstream of Mapping;
- lossless reuse of unchanged GX texture payloads;
- preservation of rigid skin semantics and compact source GX vertex formats.

These tests protect both stock Sample round-trips and future PIA+ reflective
models.
