import os
import re
import struct

import numpy as np

HEADER = b"Binary STL exported from Blender by Slicer STL Export".ljust(80, b" ")
RECORD = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])

_CHUNK = 1 << 20
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_MAX_NAME = 120


def safe_name(name):
    cleaned = _INVALID.sub("_", name).strip().rstrip(". ")[:_MAX_NAME].rstrip(". ")
    if not cleaned:
        return "object"
    if cleaned.split(".")[0].upper() in _RESERVED:
        return "_" + cleaned
    return cleaned


def unique_names(names):
    used = set()
    result = []
    for name in names:
        base = safe_name(name)
        candidate = base
        index = 2
        while candidate.lower() in used:
            candidate = f"{base} ({index})"
            index += 1
        used.add(candidate.lower())
        result.append(candidate)
    return result


def write_owners(directory, owners, geometries, scale):
    os.makedirs(directory, exist_ok=True)
    paths = []
    for owner, name in zip(owners, unique_names(owner.name for owner in owners)):
        path = os.path.join(directory, name + ".stl")
        parts = ((geometries[key], matrix) for key, matrix in owner.parts)
        if write(path, parts, scale):
            paths.append(path)
    return paths


def write(path, parts, scale):
    temporary = path + ".tmp"
    count = 0
    try:
        with open(temporary, "wb") as stream:
            stream.write(HEADER)
            stream.write(struct.pack("<I", 0))
            for (vertices, triangles), matrix in parts:
                count += _write_part(stream, vertices, triangles, matrix, scale)
            stream.seek(len(HEADER))
            stream.write(struct.pack("<I", count))
        if count:
            os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return count


def _write_part(stream, vertices, triangles, matrix, scale):
    world = (vertices @ matrix[:3, :3].T + matrix[:3, 3]) * scale
    if np.linalg.det(matrix[:3, :3]) < 0.0:
        triangles = triangles[:, ::-1]
    for start in range(0, len(triangles), _CHUNK):
        corners = world[triangles[start:start + _CHUNK]]
        records = np.zeros(len(corners), dtype=RECORD)
        records["normal"] = _normals(corners)
        records["vertices"] = corners
        stream.write(records.tobytes())
    return len(triangles)


def _normals(corners):
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    return np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0.0)
