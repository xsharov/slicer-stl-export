import os
import shutil
import subprocess

from .common import Delivery, SlicerError, single_instance_enabled

FLATPAK_PREFIX = "flatpak:"

_COMM_LENGTH = 15
_FLATPAK_ROOTS = ("/var/lib/flatpak/app", "~/.local/share/flatpak/app")


def locate(slicer, custom_path):
    if custom_path:
        return custom_path if os.path.isfile(custom_path) and os.access(custom_path, os.X_OK) else None
    for name in slicer.linux_binaries:
        found = shutil.which(name)
        if found:
            return found
    for root in _FLATPAK_ROOTS:
        if os.path.isdir(os.path.join(os.path.expanduser(root), slicer.flatpak_id)):
            return FLATPAK_PREFIX + slicer.flatpak_id
    return None


def deliver(slicer, executable, files, new_project):
    forwarded = _is_running(slicer) and any(single_instance_enabled(path) for path in _config_paths(slicer))
    if forwarded and not slicer.linux_forwarding:
        raise SlicerError(
            f"{slicer.name} on Linux cannot take files from another program while its "
            f"'Keep only one {slicer.name} instance' option is on. Turn it off or close {slicer.name}"
        )
    if executable.startswith(FLATPAK_PREFIX):
        command = ["flatpak", "run", "--file-forwarding", executable[len(FLATPAK_PREFIX):], "@@", *files, "@@"]
    else:
        command = [executable, *files]
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
    return Delivery.REUSED if forwarded else Delivery.LAUNCHED


def _config_paths(slicer):
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    yield os.path.join(config_home, slicer.config_folder, slicer.config_file)
    flatpak_config = os.path.expanduser(os.path.join("~/.var/app", slicer.flatpak_id, "config"))
    yield os.path.join(flatpak_config, slicer.config_folder, slicer.config_file)


def _is_running(slicer):
    names = {name[:_COMM_LENGTH] for name in slicer.linux_binaries}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return False
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(os.path.join("/proc", entry, "comm"), encoding="utf-8") as stream:
                if stream.read().strip() in names:
                    return True
        except OSError:
            continue
    return False
