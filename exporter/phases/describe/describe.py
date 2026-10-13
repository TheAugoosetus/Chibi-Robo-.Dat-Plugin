"""Phase 1 (Export): Read Blender scene into a BRScene.

The only export phase that touches `bpy`. Walks every armature in the
scene, snapshots its bones / meshes / materials / actions / constraints
into BR dataclasses, and collects scene-level lights and cameras. PKX
header and shiny filter parameters are extracted from armature custom
properties as side outputs.

Per-domain BR producers live under ``helpers/``. Animation unbaking and
constraint walking need already-converted IR bones / merged IR meshes
while a live Blender context is available, so describe computes a private
copy via the pure ``plan_*`` helpers. Those copies are not handed to the
plan phase — plan re-derives IR from BR itself, keeping BR → IR a
self-contained transform that works on any BRScene.
"""
import json
import bpy

try:
    from ....shared.BR.scene import BRScene, BRModel
    from ....shared.BR.fog import BRFog
    from ....shared.helpers.logger import StubLogger
    from .helpers.armature import (
        describe_armature, make_static_root_armature,
        make_static_hierarchy_armature,
    )
    from .helpers.meshes import describe_meshes, describe_static_meshes
    from .helpers.animations import describe_actions
    from .helpers.constraints import describe_constraints
    from .helpers.lights import describe_lights
    from .helpers.cameras import describe_cameras
    from .helpers.scene import (
        collect_pkx_referenced_actions,
        extract_shiny_params,
        extract_pkx_header,
        maybe_dump_diagnostic,
    )
    from ..plan.helpers.armature import plan_armature
    from ..plan.helpers.meshes import plan_meshes
    from ..plan.helpers.merge_meshes import merge_meshes
except (ImportError, SystemError):
    from shared.BR.scene import BRScene, BRModel
    from shared.BR.fog import BRFog
    from shared.helpers.logger import StubLogger
    from exporter.phases.describe.helpers.armature import (
        describe_armature, make_static_root_armature,
        make_static_hierarchy_armature,
    )
    from exporter.phases.describe.helpers.meshes import describe_meshes, describe_static_meshes
    from exporter.phases.describe.helpers.animations import describe_actions
    from exporter.phases.describe.helpers.constraints import describe_constraints
    from exporter.phases.describe.helpers.lights import describe_lights
    from exporter.phases.describe.helpers.cameras import describe_cameras
    from exporter.phases.describe.helpers.scene import (
        collect_pkx_referenced_actions,
        extract_shiny_params,
        extract_pkx_header,
        maybe_dump_diagnostic,
    )
    from exporter.phases.plan.helpers.armature import plan_armature
    from exporter.phases.plan.helpers.meshes import plan_meshes
    from exporter.phases.plan.helpers.merge_meshes import merge_meshes


def describe_scene(context, options=None, logger=StubLogger(), output_ext=''):
    """Read the active Blender scene and produce a BRScene.

    In: context (bpy.types.Context); options (dict|None, reads
        ``sparsify_bezier``); logger; output_ext (str, e.g. 'dat'/'pkx',
        passed through to compose decisions like bound-box inclusion).
    Out: (BRScene, ShinyParams|None, PKXHeader|None).
    """
    if options is None:
        options = {}

    logger.info("=== Export Phase 1: Describe Blender Scene ===")

    armatures = [obj for obj in context.scene.objects if obj.type == 'ARMATURE']
    static_mesh_objects = (
        [obj for obj in context.scene.objects if obj.type == 'MESH']
        if not armatures else []
    )
    static_hierarchy_objects = []
    if not armatures:
        if output_ext == 'pkx':
            raise ValueError(
                "Armatureless export supports static DAT models only; PKX output "
                "still requires an armature with PKX metadata."
            )
        if not static_mesh_objects:
            raise ValueError(
                "No armatures or mesh objects in the scene. Nothing can be exported."
            )
        static_hierarchy_objects = _collect_static_hierarchy_objects(
            static_mesh_objects)
        _validate_armatureless_static_meshes(
            static_mesh_objects, static_hierarchy_objects)

    # Note: baked-transforms validation lives in pre_process (user-facing,
    # runs before the pipeline starts) and in plan (BR-side defense-in-depth).
    # Describe deliberately does not validate so round-trip tests can take a
    # build → describe → BR snapshot of an importer-built scene without first
    # baking the importer's Y-up→Z-up viewing rotation into the data.
    use_bezier = options.get('sparsify_bezier', True)

    br_models = []
    # One image cache spans all models so a bpy Image datablock shared
    # across them is serialised into a single BRImage.
    image_cache = {}
    if armatures:
        for armature in armatures:
            logger.info("  Processing armature '%s'", armature.name)
            br_model = _describe_one_model(armature, use_bezier, logger, image_cache)
            br_models.append(br_model)
    else:
        br_models.append(
            _describe_static_model(
                static_mesh_objects, logger, image_cache,
                hierarchy_objects=static_hierarchy_objects,
            )
        )

    # In multi-armature scenes actions attach only when bound to an armature
    # (assigned / NLA / matching OBJECT slot / name prefix) — surface any
    # pose action nobody claimed so a dropped animation is loud, not silent.
    if len(armatures) > 1:
        try:
            from .helpers.animations_decode import _is_pose_action
        except (ImportError, SystemError):
            from exporter.phases.describe.helpers.animations_decode import _is_pose_action
        claimed = {a.name for m in br_models for a in m.actions}
        orphans = [a.name for a in bpy.data.actions
                   if _is_pose_action(a) and a.name not in claimed]
        if orphans:
            logger.warning(
                "  %d pose action(s) are not bound to any armature and will "
                "not be exported: %s. Assign the action (or an NLA strip / "
                "OBJECT action slot named after the armature) to include it.",
                len(orphans), ", ".join(sorted(orphans)))

    br_lights = describe_lights(context, logger=logger)
    br_cameras = describe_cameras(context, logger=logger)
    br_fogs = _describe_fogs(context, logger=logger)

    br_scene = BRScene(models=br_models, lights=br_lights, cameras=br_cameras,
                       fogs=br_fogs)

    shiny_params = extract_shiny_params(armatures, logger) if armatures else None

    # Build action_name → DAT animation index from the first model's
    # action ordering (compose ultimately keys DAT animation slots off
    # this same list).
    action_name_to_index = {}
    if br_models and br_models[0].actions:
        for idx, br_action in enumerate(br_models[0].actions):
            action_name_to_index[br_action.name] = idx

    pkx_header = (
        extract_pkx_header(armatures, action_name_to_index, logger)
        if armatures else None
    )

    logger.info("=== Export Phase 1 complete: %d model(s), %d light(s), %d camera(s), shiny=%s, pkx=%s ===",
                len(br_scene.models), len(br_scene.lights), len(br_scene.cameras),
                shiny_params is not None, pkx_header is not None)
    return br_scene, shiny_params, pkx_header


def _collect_static_hierarchy_objects(mesh_objects):
    """Collect MESH/EMPTY nodes needed to preserve explicit mesh parenting.

    With no MESH/EMPTY parent relation the exporter stays in flat mode. When
    such parenting exists, every mesh plus its MESH/EMPTY ancestors becomes a
    JOBJ in the static hierarchy.
    """
    found_parent_link = False
    by_id = {id(obj): obj for obj in mesh_objects}
    for mesh in mesh_objects:
        parent = getattr(mesh, "parent", None)
        while parent is not None and getattr(parent, "type", None) in ("MESH", "EMPTY"):
            found_parent_link = True
            by_id[id(parent)] = parent
            parent = getattr(parent, "parent", None)
    return list(by_id.values()) if found_parent_link else []


def _animation_data_active(anim):
    if anim is None:
        return False
    if getattr(anim, "action", None) is not None:
        return True
    if getattr(anim, "drivers", None):
        return True
    return any(
        getattr(track, "strips", None)
        for track in (getattr(anim, "nla_tracks", None) or ())
    )


def _validate_armatureless_static_meshes(mesh_objects, hierarchy_objects=None):
    """Reject states that cannot be represented by a static JOBJ hierarchy."""
    animated = []
    material_animated = []
    armature_modified = []
    shape_keyed = []

    hierarchy_objects = list(hierarchy_objects or [])
    objects_to_check = {}
    for obj in list(mesh_objects) + hierarchy_objects:
        objects_to_check[id(obj)] = obj

    for obj in objects_to_check.values():
        if _animation_data_active(getattr(obj, 'animation_data', None)):
            animated.append(obj.name)

    for obj in mesh_objects:
        data = getattr(obj, 'data', None)
        shape_keys = getattr(data, 'shape_keys', None) if data is not None else None
        key_blocks = getattr(shape_keys, 'key_blocks', None) if shape_keys is not None else None
        if key_blocks is not None and len(key_blocks) > 1:
            shape_keyed.append(obj.name)

        for material in (
                (getattr(data, 'materials', None) or ())
                if data is not None else ()):
            if material is None:
                continue
            node_tree = getattr(material, 'node_tree', None)
            if (_animation_data_active(getattr(material, 'animation_data', None))
                    or _animation_data_active(
                        getattr(node_tree, 'animation_data', None)
                        if node_tree is not None else None)):
                material_animated.append(getattr(material, 'name', obj.name))

        for modifier in getattr(obj, 'modifiers', ()) or ():
            if getattr(modifier, 'type', None) == 'ARMATURE':
                armature_modified.append(obj.name)
                break

    if animated:
        raise ValueError(
            "Armatureless DAT export is static-only. Object animation or "
            "drivers found on: " + ", ".join(sorted(set(animated)))
        )
    if material_animated:
        raise ValueError(
            "Armatureless DAT export is static-only. Material animation or "
            "drivers found on: " + ", ".join(sorted(set(material_animated)))
        )
    if shape_keyed:
        raise ValueError(
            "Armatureless DAT export cannot preserve shape keys yet. Meshes: "
            + ", ".join(sorted(set(shape_keyed)))
        )
    if armature_modified:
        raise ValueError(
            "Armatureless DAT export cannot preserve Armature modifiers. "
            "Apply/remove the modifier or export with its armature. Meshes: "
            + ", ".join(sorted(set(armature_modified)))
        )


def _describe_static_model(mesh_objects, logger, image_cache=None,
                           hierarchy_objects=None):
    """Describe a no-armature Blender scene as a rigid HSD model."""
    model_name = mesh_objects[0].name if len(mesh_objects) == 1 else "StaticModel"
    hierarchy_objects = list(hierarchy_objects or [])

    if hierarchy_objects:
        br_armature, owner_names = make_static_hierarchy_armature(
            hierarchy_objects, model_name + "_HSDHierarchy")
        fallback_root = br_armature.bones[0].name
        bone_names = {bone.name for bone in br_armature.bones}
    else:
        br_armature = make_static_root_armature(model_name + "_HSDRoot")
        owner_names = {}
        fallback_root = "Root"
        bone_names = {"Root"}

    br_meshes, _instances, br_materials, _blender_materials = (
        describe_static_meshes(
            mesh_objects,
            root_bone_name=fallback_root,
            mesh_owner_names=owner_names,
            bone_names=bone_names,
            logger=logger,
            image_cache=image_cache,
        )
    )
    if not br_meshes:
        raise ValueError(
            "Armatureless scene contains no mesh geometry with faces to export."
        )
    return BRModel(
        name=model_name,
        armature=br_armature,
        meshes=br_meshes,
        materials=br_materials,
    )


def _describe_fogs(context, logger=StubLogger()):
    """Recover scene fog from the world's native Mist settings.

    Fog exists iff the scene has a world with ``mist_settings.use_mist``
    enabled (how build signals fog presence — and how an arbitrary user
    scene opts into exporting fog). Returns [] otherwise.
    """
    world = context.scene.world
    if not world or not world.mist_settings.use_mist:
        return []
    mist = world.mist_settings
    c = world.color
    fog = BRFog(
        color=(c[0], c[1], c[2]),
        mist_start=mist.start,
        mist_depth=mist.depth,
        falloff=mist.falloff,
        intensity=mist.intensity,
    )
    logger.info("  Recovered fog from world mist (start=%.3f depth=%.3f)",
                mist.start, mist.depth)
    return [fog]


def _describe_one_model(armature, use_bezier, logger, image_cache=None):
    """Pull one armature's full BR description out of Blender.

    Computes IR bones + merged IR meshes inline because the bpy-side
    animation unbaker and constraint walker read them while a live
    Blender context is still available. These IR copies are private to
    describe — they are not stashed on the BRModel. The plan phase
    re-derives them from BR (via the same pure ``plan_armature`` /
    ``plan_meshes`` / ``merge_meshes`` helpers) so that BR → IR is a
    self-contained transform that works on any BRScene, not only one
    produced by this describe phase.
    """
    source_game = armature.get("dat_game_origin")
    source_build = armature.get("dat_plugin_build")
    logger.info(
        "  Source metadata: game=%s imported_by=%s alias_slots=%s unique_actions=%s",
        source_game or "<none>",
        source_build or "<none>",
        armature.get("dat_hsd_animation_slot_count", "<none>"),
        armature.get("dat_hsd_animation_unique_count", "<none>"),
    )

    br_armature = describe_armature(armature, logger=logger)
    ir_bones = plan_armature(br_armature, logger=logger)

    br_meshes, _br_instances, br_materials, blender_materials = describe_meshes(
        armature, br_armature, logger=logger, image_cache=image_cache,
    )
    ir_meshes = plan_meshes(br_meshes, br_materials, ir_bones, logger=logger)
    ir_meshes, blender_materials_merged = merge_meshes(
        ir_meshes, parallel=blender_materials, logger=logger,
    )

    referenced_actions = collect_pkx_referenced_actions(armature)
    br_actions = describe_actions(
        armature, br_armature, ir_bones, logger=logger,
        use_bezier=use_bezier,
        referenced_actions=referenced_actions,
        ir_meshes=ir_meshes, blender_materials=blender_materials_merged,
    )

    br_constraints = describe_constraints(armature, ir_bones, logger=logger)

    # Diagnostic dump expects IR-shaped animation sets (it walks
    # `anim_set.tracks` and `track.bone_index`). BRAction carries
    # BRBoneTracks with the same field names, so they pass straight in.
    maybe_dump_diagnostic(armature, ir_bones, br_actions, logger)

    animation_slot_map = []
    raw_slot_map = armature.get("dat_hsd_animation_slot_map")
    if isinstance(raw_slot_map, str) and raw_slot_map:
        try:
            parsed = json.loads(raw_slot_map)
            if (isinstance(parsed, list)
                    and all(isinstance(i, int) for i in parsed)
                    and all(0 <= i < len(br_actions) for i in parsed)):
                animation_slot_map = parsed
        except (ValueError, TypeError):
            logger.warning("  Invalid dat_hsd_animation_slot_map metadata; aliases will not be restored")

    if source_game == "CHIBI_ROBO":
        expected_slots = armature.get("dat_hsd_animation_slot_count")
        if expected_slots and not animation_slot_map:
            logger.warning(
                "  Chibi source reports %s original animation slots but no valid "
                "slot map survived; export would duplicate unique actions",
                expected_slots)
        elif animation_slot_map:
            logger.info(
                "  Restoring Chibi animation aliases: %d slot(s) from %d unique Action(s)",
                len(animation_slot_map), len(br_actions))

    return BRModel(
        name=armature.name,
        armature=br_armature,
        meshes=br_meshes,
        materials=br_materials,
        actions=br_actions,
        animation_slot_map=animation_slot_map,
        constraints=br_constraints,
    )
