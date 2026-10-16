from . import operators, preferences, properties, slicers, ui


def register():
    properties.register()
    preferences.register()
    operators.register()
    ui.register()


def unregister():
    slicers.shutdown()
    ui.unregister()
    operators.unregister()
    preferences.unregister()
    properties.unregister()
