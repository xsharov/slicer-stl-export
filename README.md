# Slicer STL Export

A Blender 5.2+ add-on that exports objects as STL and opens them in **Bambu Studio** or **OrcaSlicer**.

## Installation

Download `slicer_stl_export-<version>.zip` from [Releases](https://github.com/xsharov/slicer-stl-export/releases) and drag it into the Blender window.

## Usage

The panel is in the 3D Viewport sidebar (**N**) on the **Slicer** tab.

| Control | Description |
| --- | --- |
| **Scale** | Multiplier for the exported coordinates. Slicers read STL in millimeters, so use `1000` if the model is built in meters. |
| **Apply Modifiers** | On: export what the viewport shows, including modifiers, Geometry Nodes and instances. Off: export the base geometry; only collection instances are kept. |
| **Export in New Project** | Always open the export in a new slicer project, even if the slicer is already open. |
| **Export Selected** | Export the selected visible objects. |
| **Export All** | Export all visible objects except helpers such as boolean cutters (objects displayed as Wire/Bounds or disabled in renders). |

Each object is saved as a separate STL named after the object. If the slicer is open, the models are added to the open instance; otherwise the slicer starts with a new project. If the slicer is not found, the files are only saved to the export folder.

## Preferences

**Edit → Preferences → Add-ons → Slicer STL Export**

- **Slicer** — Bambu Studio or OrcaSlicer.
- **Bambu Studio** / **OrcaSlicer** — path to the executable. Leave empty to detect it automatically.
- **Export Folder** — where the STL files are written. The system temporary folder is used by default.
- **Sidebar Tab** — name of the sidebar tab.

## Limitations

- In Sculpt Mode with Dyntopo, switch to Object Mode before exporting.
- With **Apply Modifiers** off, legacy vertex/face instancing is not expanded.
- Windows is the primary platform. macOS and Linux are untested; on Linux the model always opens in a new slicer window.

## License

[GPL-3.0-or-later](LICENSE)
