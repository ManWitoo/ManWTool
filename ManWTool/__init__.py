bl_info = {
    "name": "ManWTool",
    "author": "Jairo (ManW)",
    "version": (1, 1, 2),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > ManWTool",
    "description": "Colecciones, renombrado, export FBX, import FBX automatico y updater por GitHub.",
    "category": "3D View",
}

import bpy

from bpy.props import PointerProperty

from .manwtool_core import (
    clear_preview_collection,
    init_preview_collection,
    load_cached_license_into_prefs,
    log_debug,
    log_exception,
    reload_logo,
    startup_update_check_timer,
)
from .manwtool_operators import CLASSES as OPERATOR_CLASSES
from .manwtool_properties import CLASSES as PROPERTY_CLASSES, MANWTOOL_Properties
from .manwtool_ui import CLASSES as UI_CLASSES


classes = PROPERTY_CLASSES + OPERATOR_CLASSES + UI_CLASSES


def register():
    init_preview_collection()

    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except Exception as exc:
            log_debug(f"No fue necesario desregistrar {cls.__name__}: {exc}")

    for cls in classes:
        bpy.utils.register_class(cls)

    if hasattr(bpy.types.Scene, "manwtool_props"):
        del bpy.types.Scene.manwtool_props
    bpy.types.Scene.manwtool_props = PointerProperty(type=MANWTOOL_Properties)

    try:
        load_cached_license_into_prefs()
    except Exception as exc:
        log_exception("No se pudo cargar la cache de licencia", exc)

    try:
        reload_logo()
    except Exception as exc:
        log_exception("No se pudo recargar el logo", exc)

    try:
        if not bpy.app.timers.is_registered(startup_update_check_timer):
            bpy.app.timers.register(startup_update_check_timer, first_interval=2.0)
    except Exception as exc:
        log_exception("No se pudo registrar el timer de update", exc)


def unregister():
    if hasattr(bpy.types.Scene, "manwtool_props"):
        del bpy.types.Scene.manwtool_props

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as exc:
            log_debug(f"No se pudo desregistrar {cls.__name__}: {exc}")

    clear_preview_collection()


if __name__ == "__main__":
    register()
