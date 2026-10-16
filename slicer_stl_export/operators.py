import os
import tempfile

import bpy
from bpy.props import EnumProperty

from . import collect, slicers, stl
from .preferences import absolute_path, current_slicer, export_folder, get_preferences, slicer_path

_FOLDER_NAME = "BlenderSlicerExport"
_HELPER_DISPLAY_TYPES = {"WIRE", "BOUNDS"}

_MODES = (
    ("SELECTED", "Selected", "Export the selected objects"),
    ("ALL", "All", "Export all visible objects except helpers such as boolean cutters"),
)


class SLICER_OT_export_stl(bpy.types.Operator):
    bl_idname = "slicer.export_stl"
    bl_label = "Export to Slicer"
    bl_description = "Export objects as STL and open them in the slicer"
    bl_options = {"REGISTER"}

    mode: EnumProperty(name="Objects", items=_MODES, default="SELECTED", options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, "slicer_stl_export", None) is not None

    @classmethod
    def description(cls, context, properties):
        name = current_slicer(get_preferences(context)).name
        if properties.mode == "ALL":
            return (
                f"Export all visible objects as STL and open them in {name}. "
                "Objects displayed as wire or bounds or disabled in renders, such as boolean cutters, are skipped"
            )
        return f"Export the selected objects as STL and open them in {name}"

    def execute(self, context):
        settings = context.scene.slicer_stl_export
        preferences = get_preferences(context)
        slicer = current_slicer(preferences)

        custom_path = slicer_path(preferences, slicer)
        executable = slicers.locate(slicer, custom_path)
        if executable is None:
            if custom_path:
                self.report({"ERROR"}, f"{slicer.name} was not found at {custom_path}")
            else:
                self.report({"ERROR"}, f"{slicer.name} was not found, set its path in the add-on preferences")
            return {"CANCELLED"}

        folder = export_folder(preferences)
        if folder.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, "The export folder is relative to the .blend file, save the file first")
            return {"CANCELLED"}

        _flush_edit_mode(context)
        depsgraph = context.evaluated_depsgraph_get()
        objects = self._objects(context)
        if not objects:
            if self.mode == "ALL":
                self.report({"WARNING"}, "There are no visible objects to export")
            else:
                self.report({"WARNING"}, "Select the objects to export")
            return {"CANCELLED"}

        geometries, owners = collect.gather(depsgraph, objects, settings.apply_modifiers)
        if not owners:
            self.report({"WARNING"}, "The objects have no faces to export")
            return {"CANCELLED"}

        try:
            paths = stl.write_owners(_export_directory(folder), owners, geometries, settings.scale)
        except OSError as error:
            self.report({"ERROR"}, f"Could not write the STL files: {error}")
            return {"CANCELLED"}

        try:
            delivery = slicers.deliver(slicer, executable, paths, settings.new_project)
        except slicers.SlicerError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        self.report({"INFO"}, _summary(slicer, delivery, len(paths)))
        return {"FINISHED"}

    def _objects(self, context):
        if self.mode == "ALL":
            return [obj for obj in context.visible_objects if _printable(obj)]
        return [obj for obj in context.selected_objects if obj.visible_get()]


def _printable(obj):
    return not obj.hide_render and obj.display_type not in _HELPER_DISPLAY_TYPES


def _flush_edit_mode(context):
    for obj in getattr(context, "objects_in_mode", ()):
        if obj.mode == "EDIT":
            obj.update_from_editmode()


def _export_directory(folder):
    root = absolute_path(folder) or os.path.join(tempfile.gettempdir(), _FOLDER_NAME)
    stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0] or "untitled"
    return os.path.join(root, stl.safe_name(stem))


def _summary(slicer, delivery, count):
    objects = "1 object" if count == 1 else f"{count} objects"
    if delivery is slicers.Delivery.SENT:
        return f"Added {objects} to the open {slicer.name} project"
    if delivery is slicers.Delivery.REUSED:
        return f"{slicer.name} keeps a single instance, added {objects} to the open project"
    if delivery is slicers.Delivery.QUEUED:
        return f"{slicer.name} is starting, {objects} will be added when it is ready"
    return f"Opened {objects} in a new {slicer.name} project"


def register():
    bpy.utils.register_class(SLICER_OT_export_stl)


def unregister():
    bpy.utils.unregister_class(SLICER_OT_export_stl)
