# Chibi-Robo NTSC-U DAT Structure Audit

Source: clean NTSC-U `qp.bin` extraction supplied for the PIA Plus project.
The audit scans HAL DAT structure only (SceneData → ModelSet → JOBJ → DObject
→ PObject). It does not infer rendering correctness from filenames.

## Corpus results

- 1,086 `.dat` files scanned; all 1,086 use a single `scene_data` root.
- 9,818 traversed PObjects.
  - 9,764 rigid PObjects (`property == 0`).
  - 54 shape-animation PObjects.
  - 0 `POBJ_SKIN` single-bound PObjects.
  - 0 `POBJ_ENVELOPE` weighted PObjects.
- 928 files with geometry are entirely rigid.
- 533 files are entirely rigid **and** have no ModelSet animation pointers.
  - 134 of those have exactly one JOBJ.
  - 399 retain a multi-JOBJ static hierarchy.
- 395 files are all-rigid but animated.
- 151 files have no traversed PObjects; this includes animation/effect/resource
  DATs such as the numbered `cb_robo_*.dat` files.
- Shape-animation PObjects occur in 7 files:
  `fx_gicco_twinb01.dat`, `chibi_h_maku.dat`, `cb_book.dat`,
  `tonpy_item_m.dat`, `blindhandle_l.dat`, `t_kage.dat`, and
  `shortplay_title.dat`.

## Exporter implication

Chibi-Robo's character/object system is overwhelmingly **rigid segmented
geometry attached to JOBJs**, not conventional weighted Blender skinning.
An animated rigid character still needs its JOBJ hierarchy because the animation
moves those rigid segments. "No envelope weights" therefore does **not** mean
"safe to remove the armature."

The first armatureless export implementation intentionally targets only a static
Blender mesh scene. The exporter synthesizes one format-level root JOBJ and
attaches all exported PObjects rigidly to it. Blender object transforms are
baked into the geometry, so the user does not need a fake one-bone armature.

This first path is directly representative of the 134 stock static-rigid DATs
whose model hierarchy is already one JOBJ. The 399 static-rigid multi-JOBJ DATs
are the next structural extension: supporting them without an Armature requires
an explicit Blender-side hierarchy representation (for example object/Empty
parenting) rather than silently flattening meaningful JOBJ transforms.

## Reproduction

Run:

```bash
python scripts/audit_chibi_dat_structure.py qp_bin_NTSC-U.zip
```

The script is intentionally independent of Blender and the full DAT parser so
the topology survey can be repeated cheaply when another region/corpus is
provided.
