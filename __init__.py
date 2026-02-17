bl_info = {
    "name": "Urho3D Exporter",
    "description": "Export meshes, materials, skeletons, and animations to Urho3D format",
    "author": "acs",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Render > Urho3D Export",
    "category": "Import-Export",
}

import bpy

from .preferences import UrhoExportPreferences
from .ui_panel import UrhoExportSettings, URHO_PT_ExportPanel
from .operators import (
    URHO_OT_Export,
    URHO_OT_ExportAnimations,
    URHO_OT_ExportMaterials,
    URHO_OT_ExportModels,
    URHO_OT_ExportReport,
    URHO_OT_ExportScene,
    URHO_OT_ExportTextures,
)

_classes = (
    UrhoExportPreferences,
    UrhoExportSettings,
    URHO_OT_Export,
    URHO_OT_ExportModels,
    URHO_OT_ExportMaterials,
    URHO_OT_ExportAnimations,
    URHO_OT_ExportTextures,
    URHO_OT_ExportScene,
    URHO_OT_ExportReport,
    URHO_PT_ExportPanel,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.urho_export = bpy.props.PointerProperty(type=UrhoExportSettings)


def unregister():
    del bpy.types.Scene.urho_export
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
