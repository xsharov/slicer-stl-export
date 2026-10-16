import bpy

from .operators import SLICER_OT_export_stl
from .preferences import DEFAULT_CATEGORY, current_slicer, get_preferences


class SLICER_PT_export(bpy.types.Panel):
    bl_label = "Slicer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = DEFAULT_CATEGORY

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, "slicer_stl_export", None) is not None

    def draw_header(self, context):
        self.layout.label(icon="EXPORT")

    def draw(self, context):
        layout = self.layout
        settings = context.scene.slicer_stl_export

        column = layout.column()
        column.prop(settings, "scale")
        column.prop(settings, "apply_modifiers")
        column.prop(settings, "new_project")

        buttons = layout.column(align=True)
        buttons.scale_y = 1.4
        row = buttons.row(align=True)
        row.enabled = bool(context.selected_objects)
        row.operator(SLICER_OT_export_stl.bl_idname, text="Export Selected", icon="RESTRICT_SELECT_OFF").mode = "SELECTED"
        buttons.operator(SLICER_OT_export_stl.bl_idname, text="Export All", icon="SCENE_DATA").mode = "ALL"


def _apply_preferences():
    preferences = get_preferences()
    category = preferences.sidebar_category.strip() if preferences else ""
    SLICER_PT_export.bl_label = current_slicer(preferences).name
    SLICER_PT_export.bl_category = category or DEFAULT_CATEGORY


def refresh_panel():
    if SLICER_PT_export.is_registered:
        bpy.utils.unregister_class(SLICER_PT_export)
    _apply_preferences()
    bpy.utils.register_class(SLICER_PT_export)


def register():
    _apply_preferences()
    bpy.utils.register_class(SLICER_PT_export)


def unregister():
    if SLICER_PT_export.is_registered:
        bpy.utils.unregister_class(SLICER_PT_export)
