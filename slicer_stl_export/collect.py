import numpy as np

_CONVERTIBLE_TYPES = {"MESH", "CURVE", "SURFACE", "FONT"}
_MAX_INSTANCE_DEPTH = 32


class Owner:
    __slots__ = ("name", "parts")

    def __init__(self, name):
        self.name = name
        self.parts = []


def gather(depsgraph, objects, apply_modifiers):
    owners = {obj.as_pointer(): Owner(obj.name) for obj in objects}
    geometries = {}
    if apply_modifiers:
        _gather_evaluated(depsgraph, owners, geometries)
    else:
        for obj in objects:
            owner = owners[obj.as_pointer()]
            _gather_original(depsgraph, obj, np.array(obj.matrix_world), owner, geometries, 0)
    return geometries, [owner for owner in owners.values() if owner.parts]


def _gather_evaluated(depsgraph, owners, geometries):
    for instance in depsgraph.object_instances:
        source = instance.object
        if source.type != "MESH":
            continue
        holder = instance.parent if instance.is_instance else source
        owner = owners.get(holder.original.as_pointer())
        if owner is None:
            continue
        key = source.data.as_pointer()
        if key not in geometries:
            geometries[key] = _mesh_arrays(source)
        if geometries[key] is not None:
            owner.parts.append((key, np.array(instance.matrix_world)))


def _gather_original(depsgraph, obj, matrix, owner, geometries, depth):
    if obj.type in _CONVERTIBLE_TYPES or obj.type == "META":
        key = obj.as_pointer()
        if key not in geometries:
            source = obj.evaluated_get(depsgraph) if obj.type == "META" else obj
            geometries[key] = _mesh_arrays(source)
        if geometries[key] is not None:
            owner.parts.append((key, matrix))

    collection = obj.instance_collection if obj.instance_type == "COLLECTION" else None
    if collection is None or depth >= _MAX_INSTANCE_DEPTH:
        return
    offset = np.identity(4)
    offset[:3, 3] = np.negative(collection.instance_offset)
    base = matrix @ offset
    for child in _collection_objects(collection, set()):
        _gather_original(depsgraph, child, base @ np.array(child.matrix_world), owner, geometries, depth + 1)


def _collection_objects(collection, seen):
    if collection.hide_viewport:
        return
    for obj in collection.objects:
        pointer = obj.as_pointer()
        if not obj.hide_viewport and pointer not in seen:
            seen.add(pointer)
            yield obj
    for child in collection.children:
        yield from _collection_objects(child, seen)


def _mesh_arrays(obj):
    try:
        mesh = obj.to_mesh()
    except RuntimeError:
        return None
    try:
        if mesh is None:
            return None
        triangle_count = len(mesh.loop_triangles)
        if triangle_count == 0:
            return None
        vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", vertices)
        triangles = np.empty(triangle_count * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("vertices", triangles)
        return vertices.reshape(-1, 3).astype(np.float64), triangles.reshape(-1, 3)
    finally:
        obj.to_mesh_clear()
