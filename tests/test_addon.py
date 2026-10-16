import importlib
import os
import shutil
import struct
import sys
import tempfile
import unittest

import addon_utils
import bpy
import numpy as np

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
MODULE = "slicer_stl_export"
FAKE_EXECUTABLE = os.path.join(tempfile.gettempdir(), "slicer.exe")

for path in (ROOT, TESTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from support import unescape_arguments


def read_stl(path):
    record = sys.modules[MODULE + ".stl"].RECORD
    with open(path, "rb") as stream:
        header = stream.read(80)
        count = struct.unpack("<I", stream.read(4))[0]
        records = np.frombuffer(stream.read(), dtype=record)
    assert len(records) == count, (len(records), count)
    return header, records


def add_cube(name, location=(0.0, 0.0, 0.0), size=2.0):
    bpy.ops.mesh.primitive_cube_add(size=size, location=location)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def select_only(*objects):
    bpy.context.view_layer.update()
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj in objects)
    if objects:
        bpy.context.view_layer.objects.active = objects[0]


def add_scatter_modifier(obj):
    tree = bpy.data.node_groups.new("Scatter", "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    group_input = tree.nodes.new("NodeGroupInput")
    group_output = tree.nodes.new("NodeGroupOutput")
    points = tree.nodes.new("GeometryNodeMeshToPoints")
    cube = tree.nodes.new("GeometryNodeMeshCube")
    instances = tree.nodes.new("GeometryNodeInstanceOnPoints")
    join = tree.nodes.new("GeometryNodeJoinGeometry")
    tree.links.new(group_input.outputs[0], points.inputs["Mesh"])
    tree.links.new(points.outputs["Points"], instances.inputs["Points"])
    tree.links.new(cube.outputs["Mesh"], instances.inputs["Instance"])
    tree.links.new(instances.outputs["Instances"], join.inputs[0])
    tree.links.new(group_input.outputs[0], join.inputs[0])
    tree.links.new(join.outputs[0], group_output.inputs[0])
    obj.modifiers.new("Scatter", "NODES").node_group = tree


class AddonTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        addon_utils.enable(MODULE, default_set=True)
        assert hasattr(bpy.types.Scene, "slicer_stl_export"), "add-on failed to register"
        cls.slicers = sys.modules[MODULE + ".slicers"]
        cls.output = tempfile.mkdtemp(prefix="slicer_stl_test_")
        cls.preferences = bpy.context.preferences.addons[MODULE].preferences
        cls.calls = []
        cls.found_executable = FAKE_EXECUTABLE
        cls.original_locate = cls.slicers.locate
        cls.original_deliver = cls.slicers.deliver

        def fake_locate(slicer, custom_path=""):
            return cls.found_executable

        def fake_deliver(slicer, executable, files, new_project):
            cls.calls.append((slicer, executable, list(files), new_project))
            return cls.slicers.Delivery.SENT

        cls.slicers.locate = fake_locate
        cls.slicers.deliver = fake_deliver

    @classmethod
    def tearDownClass(cls):
        cls.slicers.locate = cls.original_locate
        cls.slicers.deliver = cls.original_deliver
        addon_utils.disable(MODULE)
        shutil.rmtree(cls.output, ignore_errors=True)

    def setUp(self):
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for collection in list(bpy.data.collections):
            bpy.data.collections.remove(collection)
        for tree in list(bpy.data.node_groups):
            bpy.data.node_groups.remove(tree)
        settings = bpy.context.scene.slicer_stl_export
        settings.scale = 1.0
        settings.apply_modifiers = True
        settings.new_project = False
        self.preferences.slicer = "BAMBU_STUDIO"
        self.preferences.export_directory = self.output
        self.calls.clear()
        type(self).found_executable = FAKE_EXECUTABLE
        shutil.rmtree(self.output, ignore_errors=True)

    def export(self, mode="SELECTED"):
        return bpy.ops.slicer.export_stl(mode=mode)

    def exported(self):
        self.assertEqual(len(self.calls), 1)
        return {os.path.basename(path): read_stl(path)[1] for path in self.calls[0][2]}


class ExportTests(AddonTestCase):
    def test_selected_objects_become_separate_files(self):
        alpha = add_cube("Alpha")
        beta = add_cube("Beta", location=(5.0, 0.0, 0.0))
        add_cube("Gamma", location=(10.0, 0.0, 0.0))
        select_only(alpha, beta)
        self.assertEqual(self.export(), {"FINISHED"})
        files = self.exported()
        self.assertEqual(set(files), {"Alpha.stl", "Beta.stl"})
        self.assertTrue(all(len(records) == 12 for records in files.values()))
        slicer, executable, paths, new_project = self.calls[0]
        self.assertIs(slicer, self.slicers.BAMBU_STUDIO)
        self.assertEqual(executable, FAKE_EXECUTABLE)
        self.assertFalse(new_project)
        self.assertTrue(all(os.path.dirname(path) == os.path.join(self.output, "untitled") for path in paths))
        self.assertTrue(all(os.path.isabs(path) for path in paths))

    def test_selected_slicer_receives_the_files(self):
        cube = add_cube("Orca")
        select_only(cube)
        self.preferences.slicer = "ORCA_SLICER"
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertIs(self.calls[0][0], self.slicers.ORCA_SLICER)

    def test_export_all_skips_hidden_and_non_geometry(self):
        add_cube("Visible")
        add_cube("Hidden", location=(4.0, 0.0, 0.0)).hide_set(True)
        bpy.ops.object.camera_add(location=(0.0, -5.0, 0.0))
        bpy.ops.object.light_add(type="POINT", location=(0.0, 0.0, 5.0))
        select_only()
        self.assertEqual(self.export("ALL"), {"FINISHED"})
        self.assertEqual(set(self.exported()), {"Visible.stl"})

    def test_export_all_skips_boolean_helpers(self):
        add_cube("Body")
        add_cube("Cutter", location=(0.5, 0.0, 0.0), size=1.0).display_type = "WIRE"
        add_cube("Bounds", location=(3.0, 0.0, 0.0)).display_type = "BOUNDS"
        add_cube("NoRender", location=(6.0, 0.0, 0.0)).hide_render = True
        select_only()
        self.assertEqual(self.export("ALL"), {"FINISHED"})
        self.assertEqual(set(self.exported()), {"Body.stl"})

    def test_export_selected_keeps_explicit_helpers(self):
        cutter = add_cube("Cutter")
        cutter.display_type = "WIRE"
        select_only(cutter)
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(set(self.exported()), {"Cutter.stl"})

    def test_scale_and_world_transform(self):
        cube = add_cube("Box", location=(3.0, 0.0, 0.0))
        cube.scale = (1.0, 2.0, 1.0)
        select_only(cube)
        bpy.context.scene.slicer_stl_export.scale = 10.0
        self.assertEqual(self.export(), {"FINISHED"})
        corners = self.exported()["Box.stl"]["vertices"].reshape(-1, 3)
        np.testing.assert_allclose(corners.min(axis=0), (20.0, -20.0, -10.0), atol=1e-4)
        np.testing.assert_allclose(corners.max(axis=0), (40.0, 20.0, 10.0), atol=1e-4)

    def test_apply_modifiers_toggle(self):
        cube = add_cube("Smooth")
        cube.modifiers.new("Subdivision", "SUBSURF").levels = 1
        select_only(cube)
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(len(self.exported()["Smooth.stl"]), 48)
        self.calls.clear()
        bpy.context.scene.slicer_stl_export.apply_modifiers = False
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(len(self.exported()["Smooth.stl"]), 12)

    def test_mirrored_object_keeps_outward_normals(self):
        cube = add_cube("Mirrored", location=(0.0, 0.0, 0.0))
        cube.scale = (-1.0, 1.0, 1.0)
        select_only(cube)
        self.assertEqual(self.export(), {"FINISHED"})
        records = self.exported()["Mirrored.stl"]
        corners = records["vertices"].astype(np.float64)
        winding = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
        centroids = corners.mean(axis=1)
        self.assertTrue(np.all(np.einsum("ij,ij->i", winding, centroids) > 0.0))
        self.assertTrue(np.all(np.einsum("ij,ij->i", records["normal"], centroids) > 0.0))

    def test_curve_geometry_is_written_once(self):
        bpy.ops.curve.primitive_bezier_circle_add(radius=1.0)
        curve = bpy.context.active_object
        curve.name = "Ring"
        curve.data.bevel_depth = 0.1
        select_only(curve)
        evaluated = curve.evaluated_get(bpy.context.evaluated_depsgraph_get())
        expected = len(evaluated.to_mesh().loop_triangles)
        evaluated.to_mesh_clear()
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(len(self.exported()["Ring.stl"]), expected)

    def test_text_geometry_is_written_once(self):
        bpy.ops.object.text_add()
        text = bpy.context.active_object
        text.name = "Label"
        text.data.extrude = 0.1
        select_only(text)
        evaluated = text.evaluated_get(bpy.context.evaluated_depsgraph_get())
        expected = len(evaluated.to_mesh().loop_triangles)
        evaluated.to_mesh_clear()
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(len(self.exported()["Label.stl"]), expected)

    def test_collection_instance_is_grouped_under_instancer(self):
        parts = bpy.data.collections.new("Parts")
        part = add_cube("Part", size=1.0)
        for collection in list(part.users_collection):
            collection.objects.unlink(part)
        parts.objects.link(part)
        rack = bpy.data.objects.new("Rack", None)
        rack.instance_type = "COLLECTION"
        rack.instance_collection = parts
        rack.location = (10.0, 0.0, 0.0)
        bpy.context.scene.collection.objects.link(rack)
        select_only(rack)
        for apply_modifiers in (True, False):
            with self.subTest(apply_modifiers=apply_modifiers):
                self.calls.clear()
                bpy.context.scene.slicer_stl_export.apply_modifiers = apply_modifiers
                self.assertEqual(self.export(), {"FINISHED"})
                corners = self.exported()["Rack.stl"]["vertices"].reshape(-1, 3)
                self.assertEqual(len(corners), 36)
                np.testing.assert_allclose(corners.min(axis=0), (9.5, -0.5, -0.5), atol=1e-5)

    def test_geometry_nodes_instances_follow_modifier_toggle(self):
        bpy.ops.mesh.primitive_plane_add(size=2.0)
        host = bpy.context.active_object
        host.name = "Field"
        add_scatter_modifier(host)
        select_only(host)
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(len(self.exported()["Field.stl"]), 2 + 4 * 12)
        self.calls.clear()
        bpy.context.scene.slicer_stl_export.apply_modifiers = False
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(len(self.exported()["Field.stl"]), 2)

    def test_edit_mode_changes_are_exported(self):
        import bmesh

        cube = add_cube("Edited")
        select_only(cube)
        bpy.ops.object.mode_set(mode="EDIT")
        mesh = bmesh.from_edit_mesh(cube.data)
        mesh.verts.ensure_lookup_table()
        mesh.verts[0].co.x += 4.0
        expected = max(vertex.co.x for vertex in mesh.verts)
        bmesh.update_edit_mesh(cube.data)
        for apply_modifiers in (True, False):
            with self.subTest(apply_modifiers=apply_modifiers):
                self.calls.clear()
                bpy.context.scene.slicer_stl_export.apply_modifiers = apply_modifiers
                self.assertEqual(self.export(), {"FINISHED"})
                corners = self.exported()["Edited.stl"]["vertices"].reshape(-1, 3)
                self.assertGreater(expected, 1.5)
                self.assertAlmostEqual(float(corners[:, 0].max()), expected, places=4)
        self.assertEqual(cube.mode, "EDIT")

    def test_binary_layout(self):
        cube = add_cube("Layout")
        select_only(cube)
        self.assertEqual(self.export(), {"FINISHED"})
        path = self.calls[0][2][0]
        header, records = read_stl(path)
        self.assertFalse(header.lower().startswith(b"solid"))
        self.assertEqual(os.path.getsize(path), 84 + 50 * len(records))
        self.assertFalse(any(name.endswith(".tmp") for name in os.listdir(os.path.dirname(path))))

    def test_new_project_flag_is_forwarded(self):
        cube = add_cube("Flag")
        select_only(cube)
        bpy.context.scene.slicer_stl_export.new_project = True
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertTrue(self.calls[0][3])

    def test_relative_export_folder_needs_saved_file(self):
        cube = add_cube("Relative")
        select_only(cube)
        self.preferences.export_directory = "//stl"
        with self.assertRaisesRegex(RuntimeError, "save the file first"):
            self.export()
        self.assertEqual(self.calls, [])

    def test_nothing_selected_cancels(self):
        add_cube("Lonely")
        select_only()
        self.assertEqual(self.export(), {"CANCELLED"})
        self.assertEqual(self.calls, [])

    def test_missing_slicer_cancels(self):
        cube = add_cube("Orphan")
        select_only(cube)
        type(self).found_executable = None
        with self.assertRaisesRegex(RuntimeError, "Bambu Studio was not found"):
            self.export()
        self.assertEqual(self.calls, [])

    def test_objects_without_faces_cancel(self):
        bpy.ops.curve.primitive_bezier_curve_add()
        curve = bpy.context.active_object
        select_only(curve)
        self.assertEqual(self.export(), {"CANCELLED"})
        self.assertEqual(self.calls, [])


class NamingTests(AddonTestCase):
    def test_unique_and_safe_names(self):
        stl = sys.modules[MODULE + ".stl"]
        names = stl.unique_names(["a/b", "A_B", "CON", "com1.part", "  ", "ok.", "Куб"])
        self.assertEqual(names, ["a_b", "A_B (2)", "_CON", "_com1.part", "object", "ok", "Куб"])

    def test_unicode_object_name_is_exported(self):
        cube = add_cube("Деталь №1")
        select_only(cube)
        self.assertEqual(self.export(), {"FINISHED"})
        self.assertEqual(set(self.exported()), {"Деталь №1.stl"})


class PanelTests(AddonTestCase):
    def test_panel_lives_in_sidebar_and_follows_preferences(self):
        panel = getattr(bpy.types, "SLICER_PT_export")
        self.assertEqual((panel.bl_region_type, panel.bl_category, panel.bl_label), ("UI", "Slicer", "Bambu Studio"))
        self.preferences.slicer = "ORCA_SLICER"
        self.preferences.sidebar_category = "Print"
        panel = getattr(bpy.types, "SLICER_PT_export")
        self.assertEqual((panel.bl_region_type, panel.bl_category, panel.bl_label), ("UI", "Print", "OrcaSlicer"))
        self.assertTrue(panel.is_registered)
        self.preferences.sidebar_category = "Slicer"
        self.preferences.slicer = "BAMBU_STUDIO"
        self.assertEqual(getattr(bpy.types, "SLICER_PT_export").bl_label, "Bambu Studio")


class SlicerTests(unittest.TestCase):
    def test_catalog(self):
        catalog = importlib.import_module(MODULE + ".slicers.catalog")
        self.assertEqual([slicer.name for slicer in catalog.SLICERS], ["Bambu Studio", "OrcaSlicer"])
        self.assertEqual(catalog.get("ORCA_SLICER").windows_executable, "orca-slicer.exe")
        self.assertEqual(catalog.get("ORCA_SLICER").config_file, "OrcaSlicer.conf")
        self.assertIs(catalog.get("UNKNOWN"), catalog.BAMBU_STUDIO)

    def test_single_instance_config(self):
        common = importlib.import_module(MODULE + ".slicers.common")
        folder = tempfile.mkdtemp(prefix="slicer_conf_")
        try:
            path = os.path.join(folder, "BambuStudio.conf")
            cases = (('{"app": {"single_instance": true}}', True), ('{"app": {"single_instance": "false"}}', False))
            for body, expected in cases:
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(body + "\n# MD5 checksum 0123456789ABCDEF\n")
                self.assertIs(common.single_instance_enabled(path), expected)
            self.assertFalse(common.single_instance_enabled(os.path.join(folder, "missing.conf")))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_escape_arguments_round_trip(self):
        windows = importlib.import_module(MODULE + ".slicers.windows")
        values = [
            r"C:\Program Files\Bambu Studio\bambu-studio.exe",
            r"C:\Users\Тест\AppData\Local\Temp\Blender Slicer\Part;1.stl",
            'quote"d',
            "plain",
        ]
        text = windows.escape_arguments(values)
        self.assertEqual(unescape_arguments(text), values)
        self.assertTrue(text.endswith(";plain"))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
