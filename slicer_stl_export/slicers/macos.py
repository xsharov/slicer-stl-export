import os
import plistlib
import subprocess

from .common import Delivery, SlicerError, single_instance_enabled


def locate(slicer, custom_path):
    if custom_path:
        bundle = _bundle_of(custom_path)
        if bundle:
            return bundle
        return custom_path if os.path.isfile(custom_path) else None
    for root in ("/Applications", os.path.expanduser("~/Applications")):
        for name in slicer.mac_bundles:
            candidate = os.path.join(root, name)
            if os.path.isdir(candidate):
                return candidate
    return None


def deliver(slicer, executable, files, new_project):
    if not executable.endswith(".app"):
        _spawn(slicer, [executable, *files])
        return Delivery.LAUNCHED
    running = _is_running(executable)
    reused = new_project and running and single_instance_enabled(_config_path(slicer))
    if new_project and not reused:
        _open(slicer, ["open", "-n", "-a", executable, "--args", *files])
        return Delivery.LAUNCHED
    _open(slicer, ["open", "-a", executable, *files])
    if reused:
        return Delivery.REUSED
    return Delivery.SENT if running else Delivery.LAUNCHED


def _config_path(slicer):
    folder = os.path.expanduser(os.path.join("~/Library/Application Support", slicer.config_folder))
    return os.path.join(folder, slicer.config_file)


def _bundle_of(path):
    path = os.path.normpath(path)
    while path and path != os.path.dirname(path):
        if path.endswith(".app") and os.path.isdir(path):
            return path
        path = os.path.dirname(path)
    return None


def _bundle_executable(bundle):
    fallback = os.path.splitext(os.path.basename(bundle))[0]
    try:
        with open(os.path.join(bundle, "Contents", "Info.plist"), "rb") as stream:
            return plistlib.load(stream).get("CFBundleExecutable") or fallback
    except (OSError, plistlib.InvalidFileException):
        return fallback


def _is_running(bundle):
    try:
        result = subprocess.run(["pgrep", "-x", _bundle_executable(bundle)], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _open(slicer, command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        raise SlicerError(f"Could not open {slicer.name}: {error}") from error
    if result.returncode != 0:
        raise SlicerError(result.stderr.strip() or f"Could not open {slicer.name}")


def _spawn(slicer, command):
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as error:
        raise SlicerError(f"Could not start {slicer.name}: {error}") from error
