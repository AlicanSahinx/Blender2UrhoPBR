import bpy
from bpy.props import StringProperty, IntProperty


class UrhoExportPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    output_path: StringProperty(
        name="Output Path",
        description="Default output path for Urho3D resources",
        default="",
        subtype='DIR_PATH',
    )

    max_messages: IntProperty(
        name="Max Log Messages",
        description="Maximum number of log messages to display",
        default=500,
        min=100,
        max=5000,
    )

    viewer_path: StringProperty(
        name="SceneViewer Path",
        description="Path to SceneViewer binary (auto-detected if empty)",
        default="",
        subtype='FILE_PATH',
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "output_path")
        layout.prop(self, "max_messages")
        layout.prop(self, "viewer_path")
