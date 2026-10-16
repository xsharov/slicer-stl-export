import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
FAKE_SLICER = os.path.join(TESTS, "fake_slicer.py")
PACKAGE = "slicer_stl_export.slicers"

for path in (ROOT, TESTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from support import unescape_arguments


def wait_for(condition, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return False


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class WindowsDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.windows = importlib.import_module(PACKAGE + ".windows")
        cls.win32 = importlib.import_module(PACKAGE + ".win32")
        cls.common = importlib.import_module(PACKAGE + ".common")
        cls.slicer = importlib.import_module(PACKAGE + ".catalog").BAMBU_STUDIO
        cls.python = sys.executable

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="slicer_ipc_")
        self.output = os.path.join(self.folder, "received.json")
        self.files = [os.path.join(self.folder, name) for name in ("Деталь 1.stl", "part;2.stl")]
        for path in self.files:
            open(path, "wb").close()
        self.fake = None
        self.patched = []

    def tearDown(self):
        for name, value in reversed(self.patched):
            setattr(self.windows, name, value)
        if self.fake is not None and self.fake.poll() is None:
            self.fake.kill()
            self.fake.wait()
        self.windows.shutdown()
        shutil.rmtree(self.folder, ignore_errors=True)

    def patch(self, name, value):
        self.patched.append((name, getattr(self.windows, name)))
        setattr(self.windows, name, value)

    def start_fake(self, delay, hang=0.0):
        self.fake = subprocess.Popen([self.python, "-I", FAKE_SLICER, self.output, str(delay), str(hang)])

    def wait_for_window(self):
        self.assertTrue(wait_for(lambda: self.windows._main_window(self.python, self.fake.pid) is not None))

    def received_arguments(self):
        self.assertEqual(self.fake.wait(timeout=20), 0)
        with open(self.output, encoding="utf-8") as stream:
            data = json.load(stream)
        self.assertEqual(data["id"], 1)
        self.assertTrue(data["text"].endswith("\0"))
        return unescape_arguments(data["text"][:-1])

    def test_files_are_sent_to_running_instance(self):
        self.start_fake(0.0)
        self.wait_for_window()
        self.assertIs(self.windows.deliver(self.slicer, self.python, self.files, False), self.common.Delivery.SENT)
        self.assertEqual(self.received_arguments(), [self.python, *self.files])

    def test_files_wait_for_starting_instance(self):
        self.start_fake(2.0)
        self.assertTrue(wait_for(lambda: self.fake.pid in self.win32.process_ids(os.path.basename(self.python))))
        self.assertIs(self.windows.deliver(self.slicer, self.python, self.files, False), self.common.Delivery.QUEUED)
        self.assertTrue(wait_for(lambda: self.windows._poll() is None))
        self.assertEqual(self.received_arguments(), [self.python, *self.files])

    def test_unresponsive_window_reports_error_instead_of_relaunching(self):
        launched = []
        self.patch("_SEND_TIMEOUT_MS", 300)
        self.patch("_spawn", lambda slicer, command: launched.append(command))
        self.start_fake(0.0, hang=2.0)
        self.wait_for_window()
        with self.assertRaisesRegex(self.common.SlicerError, "did not accept the files"):
            self.windows.deliver(self.slicer, self.python, self.files, False)
        self.assertEqual(launched, [])

    def test_old_process_without_window_is_not_waited_for(self):
        launched = []
        self.patch("_STARTUP_TIMEOUT", 0.0)
        self.patch("_spawn", lambda slicer, command: launched.append(command))
        self.start_fake(5.0)
        self.assertTrue(wait_for(lambda: self.fake.pid in self.win32.process_ids(os.path.basename(self.python))))
        self.assertIs(self.windows.deliver(self.slicer, self.python, self.files, False), self.common.Delivery.LAUNCHED)
        self.assertEqual(launched, [[self.python, *self.files]])

    def test_process_ids_stay_in_current_session(self):
        current = self.win32.current_session()
        sessions = {pid: session for pid, session, name in self.win32.processes() if name.lower() == "csrss.exe"}
        pids = self.win32.process_ids("csrss.exe")
        self.assertTrue(pids)
        self.assertTrue(all(sessions[pid] == current for pid in pids))
        self.assertLess(len(pids), len(sessions))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
