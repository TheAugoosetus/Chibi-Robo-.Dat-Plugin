bl_info = {
    "name": "Chibi-Robo DAT Model",
    "author": "Made, StarsMmd, MikeyX",
    "version": (3, 1, 6),
    "blender": (4, 5, 0),
    "location": "File > Import-Export",
    "description": "Import-export Chibi-Robo GameCube .dat models",
    "warning": "",
    "category": "Import-Export",
}

from .BlenderPlugin import register, unregister
