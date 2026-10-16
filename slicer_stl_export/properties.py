import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty


class SlicerExportSettings(bpy.types.PropertyGroup):
    scale: FloatProperty(
        name="Scale",
        description="Multiplier for the exported coordinates. Slicers read STL units as millimeters",
        default=1.0,
        min=1e-6,
        soft_min=0.001,
        soft_max=1000.0,
        step=10,
        precision=3,
    )
    apply_modifiers: BoolProperty(
        name="Apply Modifiers",
        description=(
            "Export the geometry as shown in the viewport, with modifiers and instances applied. "
            "When off, the base geometry is exported and only collection instances are kept"
        ),
        default=True,
    )
    new_project: BoolProperty(
        name="Export in New Project",
        description="Open the export in a new slicer project instead of adding it to the open one",
        default=False,
    )


def register():
    bpy.utils.register_class(SlicerExportSettings)
    bpy.types.Scene.slicer_stl_export = PointerProperty(type=SlicerExportSettings)


def unregister():
    del bpy.types.Scene.slicer_stl_export
    bpy.utils.unregister_class(SlicerExportSettings)
