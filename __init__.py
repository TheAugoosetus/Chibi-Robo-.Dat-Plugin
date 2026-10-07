bl_info = {
    "name": "Chibi-Robo DAT Model",
    "author": "Made, StarsMmd, MikeyX",
    "version": (3, 1, 7),
    "blender": (4, 5, 0),
    "location": "File > Import-Export",
    "description": "Import-export Chibi-Robo GameCube .dat models",
    "warning": "",
    "category": "Import-Export",
}

# Blender loads this directory as an add-on package, so __package__ is set
# and the relative import below is the normal runtime path. Pytest may import
# this file directly while discovering tests from a checkout whose directory
# name is not a valid Python package name (for example this repository's
# "Chibi-Robo-.Dat-Plugin"). In that collection-only case, do not import the
# Blender entrypoint; tests import the pipeline modules they exercise directly.
if __package__:
    from .BlenderPlugin import register, unregister
else:
    def register():
        pass

    def unregister():
        pass
