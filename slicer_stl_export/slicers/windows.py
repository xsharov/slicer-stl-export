import os
import re
import subprocess
import time
import traceback
import winreg
from dataclasses import dataclass

import bpy

from . import win32
from .catalog import Slicer
from .common import Delivery, SlicerError, single_instance_enabled

_COPY_DATA_ID = 1
_SEND_TIMEOUT_MS = 5000
_STARTUP_TIMEOUT = 180.0
_POLL_INTERVAL = 0.5
_COMMAND_LINE_LIMIT = 30000
_SPAWN_FLAGS = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
_QUOTED_CHARACTERS = frozenset(' \t\\";\r\n')
_QUOTED_COMMAND = re.compile(r'^\s*"([^"]+)"')
_ICON_INDEX = re.compile(r",\s*-?\d+\s*$")
_UNINSTALL = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"


@dataclass
class _Job:
    slicer: Slicer
    executable: str
    files: list
    pid: int | None
    deadline: float


_jobs = []


def locate(slicer, custom_path):
    if custom_path:
        return custom_path if os.path.isfile(custom_path) else None
    for candidate in _candidates(slicer):
        if candidate and os.path.isfile(candidate):
            return os.path.normpath(candidate)
    return None


def deliver(slicer, executable, files, new_project):
    running = bool(_pids(executable, None))
    reused = new_project and running and _keeps_single_instance(slicer)
    if not new_project or reused:
        target = _main_window(executable, None)
        if target is not None:
            if not _send(target, executable, files):
                raise SlicerError(_refused_message(slicer, files))
            return Delivery.REUSED if reused else Delivery.SENT
        if _starting(executable, None):
            _enqueue(slicer, executable, files, None)
            return Delivery.QUEUED
    return _launch(slicer, executable, files)


def shutdown():
    _jobs.clear()
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)


def escape_arguments(values):
    return ";".join(_quote(value) for value in values)


def _quote(value):
    if value and not _QUOTED_CHARACTERS.intersection(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")
    return f'"{escaped}"'


def _candidates(slicer):
    for pid in sorted(win32.process_ids(slicer.windows_executable)):
        yield win32.process_path(pid)
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key, value in slicer.windows_install_keys:
            install = _registry_value(root, key, value)
            yield os.path.join(install, slicer.windows_executable) if install else None
        icon = _registry_value(root, _UNINSTALL + slicer.windows_uninstall_key, "DisplayIcon")
        yield _ICON_INDEX.sub("", icon).strip().strip('"') if icon else None
    command = _registry_value(winreg.HKEY_CLASSES_ROOT, slicer.url_scheme + r"\shell\open\command", "")
    match = _QUOTED_COMMAND.match(command or "")
    yield match.group(1) if match else None
    for variable, folder in (("ProgramW6432", ""), ("ProgramFiles", ""), ("LOCALAPPDATA", "Programs")):
        base = os.environ.get(variable)
        yield os.path.join(base, folder, slicer.windows_folder, slicer.windows_executable) if base else None


def _registry_value(root, path, name):
    try:
        with winreg.OpenKey(root, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return value if isinstance(value, str) and value.strip() else None


def _keeps_single_instance(slicer):
    folder = os.path.join(os.environ.get("APPDATA", ""), slicer.config_folder)
    return single_instance_enabled(os.path.join(folder, slicer.config_file))


def _refused_message(slicer, files):
    return (
        f"{slicer.name} did not accept the files. If it runs as administrator, restart it normally. "
        f"The STL files are in {os.path.dirname(files[0])}"
    )


def _pids(executable, pid):
    pids = win32.process_ids(os.path.basename(executable))
    return pids if pid is None else pids & {pid}


def _starting(executable, pid):
    for candidate in _pids(executable, pid):
        age = win32.process_age(candidate)
        if age is not None and age < _STARTUP_TIMEOUT:
            return True
    return False


def _main_window(executable, pid):
    pids = _pids(executable, pid)
    if not pids:
        return None
    windows = win32.main_windows(pids)
    return windows[0] if windows else None


def _send(target, executable, files):
    hwnd, pid = target
    payload = (escape_arguments([executable, *files]) + "\0").encode("utf-16-le")
    win32.allow_foreground(pid)
    if not win32.send_copy_data(hwnd, _COPY_DATA_ID, payload, _SEND_TIMEOUT_MS):
        return False
    win32.activate(hwnd)
    return True


def _launch(slicer, executable, files):
    command = [executable, *files]
    if len(subprocess.list2cmdline(command)) > _COMMAND_LINE_LIMIT:
        process = _spawn(slicer, [executable])
        _enqueue(slicer, executable, files, process.pid)
        return Delivery.QUEUED
    _spawn(slicer, command)
    return Delivery.LAUNCHED


def _spawn(slicer, command):
    try:
        return subprocess.Popen(
            command,
            cwd=os.path.dirname(command[0]) or None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=_SPAWN_FLAGS,
        )
    except OSError as error:
        raise SlicerError(f"Could not start {slicer.name}: {error}") from error


def _enqueue(slicer, executable, files, pid):
    _jobs.append(_Job(slicer, executable, list(files), pid, time.monotonic() + _STARTUP_TIMEOUT))
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=_POLL_INTERVAL, persistent=True)


def _poll():
    for job in tuple(_jobs):
        try:
            _advance(job)
        except Exception as error:
            traceback.print_exc()
            if job in _jobs:
                _jobs.remove(job)
            _notify(str(error))
    return _POLL_INTERVAL if _jobs else None


def _advance(job):
    target = _main_window(job.executable, job.pid)
    if target is not None:
        _jobs.remove(job)
        if not _send(target, job.executable, job.files):
            _notify(_refused_message(job.slicer, job.files))
        return
    if time.monotonic() < job.deadline and _starting(job.executable, job.pid):
        return
    _jobs.remove(job)
    if job.pid is None:
        _launch(job.slicer, job.executable, job.files)
    else:
        _notify(f"{job.slicer.name} did not finish starting. The STL files are in {os.path.dirname(job.files[0])}")


def _notify(message):
    print(f"Slicer STL Export: {message}")
    window_manager = bpy.context.window_manager
    if window_manager is None or not window_manager.windows:
        return

    def draw(menu, context):
        menu.layout.label(text=message)

    try:
        with bpy.context.temp_override(window=window_manager.windows[0]):
            window_manager.popup_menu(draw, title="Slicer STL Export", icon="ERROR")
    except RuntimeError:
        traceback.print_exc()
