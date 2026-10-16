import sys
import time

from .catalog import BAMBU_STUDIO, ORCA_SLICER, SLICERS, Slicer, get
from .common import Delivery, SlicerError

if sys.platform == "win32":
    from . import windows as _backend
elif sys.platform == "darwin":
    from . import macos as _backend
else:
    from . import linux as _backend

__all__ = (
    "BAMBU_STUDIO",
    "ORCA_SLICER",
    "SLICERS",
    "Delivery",
    "Slicer",
    "SlicerError",
    "deliver",
    "get",
    "locate",
    "shutdown",
)

_CACHE_SECONDS = 5.0
_located = {}


def locate(slicer, custom_path=""):
    key = (slicer.key, custom_path)
    now = time.monotonic()
    cached = _located.get(key)
    if cached is not None and now - cached[0] < _CACHE_SECONDS:
        return cached[1]
    found = _backend.locate(slicer, custom_path)
    _located[key] = (now, found)
    return found


def deliver(slicer, executable, files, new_project):
    return _backend.deliver(slicer, executable, files, new_project)


def shutdown():
    _located.clear()
    stop = getattr(_backend, "shutdown", None)
    if stop is not None:
        stop()
