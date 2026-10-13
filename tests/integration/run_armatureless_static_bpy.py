#!/usr/bin/env python3
"""Headless bpy integration test for static armatureless DAT export."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bpy

from exporter.exporter import Exporter
from importer.phases.parse.parse import parse_sections
from importer.phases.route.route import route_sections
from shared.helpers.logger import StubLogger


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)


def build_scene():
    root = bpy.data.objects.new("Stand", None)
    bpy.context.scene.collection.objects.link(root)

    mesh_data = bpy.data.meshes.new("SignMesh")
    mesh_data.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)],
        [],
        [(0, 1, 2)],
    )
    mesh_data.update()

    sign = bpy.data.objects.new("Sign", mesh_data)
    bpy.context.scene.collection.objects.link(sign)
    sign.parent = root
    sign.location = (2.0, 0.5, 1.0)

    material = bpy.data.materials.new("SignMaterial")
    material.use_nodes = True
    mesh_data.materials.append(material)

    return root, sign


def main():
    clear_scene()
    build_scene()

    assert not any(obj.type == 'ARMATURE' for obj in bpy.context.scene.objects)

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "armatureless_static.dat")
        result = Exporter.run(
            bpy.context,
            out,
            options={"strip_names": False, "sparsify_bezier": True},
            logger=StubLogger(),
        )
        assert result == {'FINISHED'}

        raw = Path(out).read_bytes()
        assert len(raw) >= 0x20
        assert int.from_bytes(raw[0:4], "big") == len(raw)

        section_map = route_sections(raw, game="CHIBI_ROBO")
        sections = parse_sections(
            raw,
            section_map,
            {"game": "CHIBI_ROBO", "filepath": out},
            logger=StubLogger(),
        )
        scene_section = next(
            section for section in sections
            if getattr(section, "name", None) == "scene_data"
        )
        scene = scene_section.root_node
        assert len(scene.models) == 1

        model = scene.models[0]
        assert model.root_joint.name == "Stand"
        assert model.root_joint.child is not None
        assert model.root_joint.child.name == "Sign"
        assert model.root_joint.child.property is not None

    print("armatureless static bpy integration: PASS")


if __name__ == "__main__":
    main()
