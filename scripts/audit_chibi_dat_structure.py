#!/usr/bin/env python3
"""Audit Chibi-Robo HAL DAT JOBJ/PObject structure from a qp.bin extraction ZIP.

This intentionally parses only the small structural subset needed to classify
rigid/static model topology. It does not decode geometry or materials.
"""
import argparse
import collections
import struct
import zipfile

HEADER = 0x20
POBJ_TYPE_MASK = 3 << 12
POBJ_SKIN = 0 << 12
POBJ_SHAPEANIM = 1 << 12
POBJ_ENVELOPE = 2 << 12
JOBJ_PTCL = 1 << 5
JOBJ_INSTANCE = 1 << 12
JOBJ_SPLINE = 1 << 14


def u32(data, offset):
    return struct.unpack_from(">I", data, offset)[0]


def u16(data, offset):
    return struct.unpack_from(">H", data, offset)[0]


def pointer_array(data, pointer, data_size):
    if not pointer:
        return []
    out = []
    cursor = HEADER + pointer
    limit = HEADER + data_size
    while cursor + 4 <= limit:
        value = u32(data, cursor)
        cursor += 4
        if value == 0:
            break
        if value >= data_size:
            break
        out.append(value)
    return out


def scan_dat(data):
    if len(data) < HEADER:
        raise ValueError("DAT shorter than 0x20-byte header")
    _file_size, data_size, reloc_count, root_count, ref_count = struct.unpack_from(
        ">5I", data, 0
    )
    root_table = HEADER + data_size + reloc_count * 4
    string_table = root_table + root_count * 8 + ref_count * 8

    roots = []
    for i in range(root_count):
        node_offset, string_offset = struct.unpack_from(
            ">2I", data, root_table + i * 8
        )
        start = string_table + string_offset
        end = data.find(b"\0", start)
        name = data[start:end].decode("ascii", "replace") if end >= 0 else "?"
        roots.append((node_offset, name))

    result = {
        "roots": [name for _, name in roots],
        "model_sets": 0,
        "joint_count": 0,
        "pobj_count": 0,
        "rigid": 0,
        "single_bone": 0,
        "envelope": 0,
        "shape": 0,
        "animated_modelsets": 0,
    }

    for scene_offset, root_name in roots:
        if root_name != "scene_data":
            continue
        scene_abs = HEADER + scene_offset
        models_ptr = u32(data, scene_abs)
        for model_offset in pointer_array(data, models_ptr, data_size):
            result["model_sets"] += 1
            model_abs = HEADER + model_offset
            root_joint, anim_joints, anim_materials, anim_shapes = struct.unpack_from(
                ">4I", data, model_abs
            )
            if anim_joints or anim_materials or anim_shapes:
                result["animated_modelsets"] += 1

            seen_joints = set()
            stack = [root_joint] if root_joint else []
            while stack:
                joint = stack.pop()
                if not joint or joint in seen_joints or joint >= data_size:
                    continue
                seen_joints.add(joint)
                joint_abs = HEADER + joint
                _name, flags, child, next_joint, prop = struct.unpack_from(
                    ">5I", data, joint_abs
                )
                result["joint_count"] += 1
                if child:
                    stack.append(child)
                if next_joint:
                    stack.append(next_joint)

                # Particle/spline/instance properties are not DObject chains.
                if not prop or flags & (JOBJ_PTCL | JOBJ_SPLINE | JOBJ_INSTANCE):
                    continue

                seen_meshes = set()
                mesh = prop
                while mesh and mesh not in seen_meshes and mesh < data_size:
                    seen_meshes.add(mesh)
                    mesh_abs = HEADER + mesh
                    _mesh_name, next_mesh, _mobj, pobj = struct.unpack_from(
                        ">4I", data, mesh_abs
                    )

                    seen_pobjs = set()
                    while pobj and pobj not in seen_pobjs and pobj < data_size:
                        seen_pobjs.add(pobj)
                        pobj_abs = HEADER + pobj
                        _pobj_name, next_pobj, _vtx_list = struct.unpack_from(
                            ">3I", data, pobj_abs
                        )
                        flags16 = u16(data, pobj_abs + 12)
                        prop2 = u32(data, pobj_abs + 20)
                        result["pobj_count"] += 1
                        pobj_type = flags16 & POBJ_TYPE_MASK

                        if prop2 == 0:
                            result["rigid"] += 1
                        elif pobj_type == POBJ_ENVELOPE:
                            result["envelope"] += 1
                        elif pobj_type == POBJ_SKIN:
                            result["single_bone"] += 1
                        elif pobj_type == POBJ_SHAPEANIM:
                            result["shape"] += 1

                        pobj = next_pobj
                    mesh = next_mesh

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip_path", help="ZIP containing extracted qp.bin files")
    args = ap.parse_args()

    rows = []
    with zipfile.ZipFile(args.zip_path) as archive:
        for info in archive.infolist():
            if not info.filename.lower().endswith(".dat"):
                continue
            result = scan_dat(archive.read(info.filename))
            result["path"] = info.filename
            rows.append(result)

    static_rigid = [
        r for r in rows
        if r["pobj_count"] > 0
        and r["rigid"] == r["pobj_count"]
        and r["animated_modelsets"] == 0
    ]
    single_joint_static = [r for r in static_rigid if r["joint_count"] == 1]

    print("DAT files:", len(rows))
    print("scene_data-only roots:",
          sum(r["roots"] == ["scene_data"] for r in rows))
    print("PObjects:", sum(r["pobj_count"] for r in rows))
    print("  rigid:", sum(r["rigid"] for r in rows))
    print("  single-bone:", sum(r["single_bone"] for r in rows))
    print("  envelope:", sum(r["envelope"] for r in rows))
    print("  shape:", sum(r["shape"] for r in rows))
    print("static all-rigid DATs:", len(static_rigid))
    print("  one JOBJ:", len(single_joint_static))
    print("  multiple JOBJs:", len(static_rigid) - len(single_joint_static))
    print("animated all-rigid DATs:", sum(
        r["pobj_count"] > 0
        and r["rigid"] == r["pobj_count"]
        and r["animated_modelsets"] > 0
        for r in rows
    ))
    print("DATs with no traversed PObjects:",
          sum(r["pobj_count"] == 0 for r in rows))


if __name__ == "__main__":
    main()
