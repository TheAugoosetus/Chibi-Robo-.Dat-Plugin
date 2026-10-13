"""Keep every public plugin-version declaration synchronized."""

import ast
import re
from pathlib import Path

from shared.version import PLUGIN_VERSION, PLUGIN_VERSION_TUPLE


ROOT = Path(__file__).resolve().parents[1]


def _bl_info_version():
    tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "bl_info" for t in node.targets):
                return tuple(ast.literal_eval(node.value)["version"])
    raise AssertionError("bl_info assignment not found")


def _manifest_version():
    text = (ROOT / "blender_manifest.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_plugin_version_declarations_match():
    assert PLUGIN_VERSION == "3.1.8"
    assert PLUGIN_VERSION_TUPLE == (3, 1, 8)
    assert _bl_info_version() == PLUGIN_VERSION_TUPLE
    assert _manifest_version() == PLUGIN_VERSION
