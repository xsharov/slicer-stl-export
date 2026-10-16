import os

import bpy
from bpy.props import EnumProperty, StringProperty

from . import slicers

DEFAULT_CATEGORY = "Slicer"

_PATH_PROPERTIES = {
    slicers.BAMBU_STUDIO.key: "bambu_studio_path",
    slicers.ORCA_SLICER.key: "orca_slicer_path",
}


def get_preferences(context=None):
    addon = (context or bpy.context).preferences.addons.get(__package__)
    return addon.preferences if addon else None


def current_slicer(preferences):
    return slicers.get(preferences.slicer if preferences else "")


def slicer_path(preferences, slicer):
    raw = getattr(preferences, _PATH_PROPERTIES[slicer.key]).strip() if preferences else ""
    return absolute_path(raw)


def export_folder(preferences):
    return preferences.export_directory.strip() if preferences else ""


def absolute_path(raw):
    return os.path.abspath(bpy.path.abspath(raw)) if raw else ""


def _refresh_panel(self, context):
    from . import ui

    ui.refresh_panel()


class SlicerExportPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    slicer: EnumProperty(
        name="Slicer",
        description="Application that receives the exported STL files",
        items=[(slicer.key, slicer.name, f"Open the exported files in {slicer.name}") for slicer in slicers.SLICERS],
        default=slicers.BAMBU_STUDIO.key,
        update=_refresh_panel,
    )
    bambu_studio_path: StringProperty(
        name="Bambu Studio",
        description="Bambu Studio executable. Leave empty to detect it automatically",
        subtype="FILE_PATH",
    )
    orca_slicer_path: StringProperty(
        name="OrcaSlicer",
        description="OrcaSlicer executable. Leave empty to detect it automatically",
        subtype="FILE_PATH",
    )
    export_directory: StringProperty(
        name="Export Folder",
        description="Folder for the exported STL files. Leave empty to use the system temporary folder",
        subtype="DIR_PATH",
    )
    sidebar_category: StringProperty(
        name="Sidebar Tab",
        description="Sidebar tab that holds the panel",
        default=DEFAULT_CATEGORY,
        update=_refresh_panel,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        column = layout.column()
        column.row().prop(self, "slicer", expand=True)
        slicer = current_slicer(self)
        column.prop(self, _PATH_PROPERTIES[slicer.key])
        found = slicers.locate(slicer, slicer_path(self, slicer))
        if found:
            column.label(text=f"Using {found}", icon="CHECKMARK")
        else:
            column.label(text=f"{slicer.name} was not found", icon="ERROR")

        column.separator()
        column.prop(self, "export_directory")
        column.prop(self, "sidebar_category")


def register():
    bpy.utils.register_class(SlicerExportPreferences)


def unregister():
    bpy.utils.unregister_class(SlicerExportPreferences)
