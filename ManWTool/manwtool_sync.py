"""Sincronizacion automatica de nombres Object -> Data.

En Blender el objeto y su datablock (mesh, curve, camera, light...) son IDs
independientes con nombres independientes: renombrar el objeto en el Outliner,
con F2 o en el panel N no toca el nombre de la mesh. Esto rompe la trazabilidad
en el export FBX y en cualquier pipeline que resuelva por nombre de datablock.

Este modulo anade dos cosas:
  - Un handler en depsgraph_update_post que, con el toggle activo, copia
    obj.name a obj.data.name venga el renombrado de donde venga.
  - Un operador batch (manwtool.sync_all_data_names) que corrige de una pasada
    todos los desajustes existentes.

Con el toggle apagado el handler NO esta registrado: el coste es exactamente cero.
"""

import bpy

from bpy.app.handlers import persistent

from .manwtool_core import get_addon_prefs, log_debug, log_exception


# Tipos de datablock que no admiten renombrado o para los que no tiene sentido.
SYNC_STATUS_SYNCED = "SYNCED"
SYNC_STATUS_NO_DATA = "NO_DATA"
SYNC_STATUS_LINKED = "LINKED"
SYNC_STATUS_SHARED = "SHARED"
SYNC_STATUS_ALREADY = "ALREADY"


# Guarda de re-entrancia a nivel de modulo. Asignar data.name marca el ID como
# actualizado y vuelve a disparar depsgraph_update_post; sin este flag hay recursion.
_syncing = False


def is_syncing():
    return _syncing


def get_sync_enabled():
    prefs = get_addon_prefs()
    return bool(getattr(prefs, "sync_data_names", False)) if prefs else False


def get_real_users(data):
    """Usuarios reales del datablock, descontando el fake user.

    data.use_fake_user suma 1 a data.users, asi que un datablock con fake user y
    un solo objeto real reporta users == 2. Sin este descuento lo trataríamos
    como compartido y no se sincronizaria nunca.
    """
    users = getattr(data, "users", 1)
    if getattr(data, "use_fake_user", False):
        users -= 1
    return users


def get_sync_status(obj):
    """Clasifica que haria la sincronizacion sobre este objeto, sin aplicarla."""
    data = getattr(obj, "data", None)
    if data is None:
        # Empties y similares no tienen datablock.
        return SYNC_STATUS_NO_DATA
    if getattr(data, "library", None) is not None:
        # Datos linkeados desde una libreria externa: read-only.
        return SYNC_STATUS_LINKED
    if getattr(data, "override_library", None) is not None:
        # Library override: renombrar rompe el vinculo con el original.
        return SYNC_STATUS_LINKED
    if get_real_users(data) > 1:
        # Compartido por varios objetos: que nombre gana es ambiguo, no tocamos.
        return SYNC_STATUS_SHARED
    if data.name == obj.name:
        return SYNC_STATUS_ALREADY
    return SYNC_STATUS_SYNCED


def sync_one(obj):
    """Sincroniza el datablock de un objeto. Devuelve True si lo renombro."""
    if get_sync_status(obj) != SYNC_STATUS_SYNCED:
        return False
    obj.data.name = obj.name
    return True


def sync_objects(objects):
    """Sincroniza una coleccion de objetos y devuelve el conteo por resultado.

    Activa la guarda _syncing durante toda la pasada para que el handler, si esta
    registrado, no reprocese en cascada los mismos objetos.
    """
    global _syncing

    counters = {
        SYNC_STATUS_SYNCED: 0,
        SYNC_STATUS_NO_DATA: 0,
        SYNC_STATUS_LINKED: 0,
        SYNC_STATUS_SHARED: 0,
        SYNC_STATUS_ALREADY: 0,
    }

    previous = _syncing
    _syncing = True
    try:
        for obj in objects:
            if obj is None:
                continue
            status = get_sync_status(obj)
            if status == SYNC_STATUS_SYNCED:
                obj.data.name = obj.name
            counters[status] += 1
    finally:
        _syncing = previous

    return counters


@persistent
def sync_object_data_names(scene, depsgraph):
    """Handler de depsgraph_update_post. @persistent es obligatorio: sin el,
    Blender lo descarta al cargar un .blend y el toggle quedaria mintiendo."""
    global _syncing

    if _syncing:
        return
    if not get_sync_enabled():
        return

    _syncing = True
    try:
        for update in depsgraph.updates:
            source = update.id
            if not isinstance(source, bpy.types.Object):
                continue
            # El depsgraph puede entregar copias evaluadas; escribir sobre ellas
            # no persiste en el .blend. .original devuelve el ID real.
            obj = getattr(source, "original", None) or source
            try:
                sync_one(obj)
            except Exception as exc:
                # Un objeto problematico no debe tumbar el resto de la pasada,
                # pero el error se registra: nunca se silencia del todo.
                log_exception(f"No se pudo sincronizar el datablock de {source!r}", exc)
    finally:
        # try/finally obligatorio: una excepcion que dejase _syncing en True
        # mataria la feature en silencio durante el resto de la sesion.
        _syncing = False


def is_handler_registered():
    return sync_object_data_names in bpy.app.handlers.depsgraph_update_post


def set_handler_enabled(enabled):
    """Registra o retira el handler. Idempotente: comprobar pertenencia antes de
    append() evita duplicados al recargar el addon, y antes de remove() evita
    el ValueError."""
    handlers = bpy.app.handlers.depsgraph_update_post
    if enabled:
        if sync_object_data_names not in handlers:
            handlers.append(sync_object_data_names)
            log_debug("Handler de sincronizacion de nombres registrado")
    else:
        while sync_object_data_names in handlers:
            handlers.remove(sync_object_data_names)
            log_debug("Handler de sincronizacion de nombres retirado")


def on_sync_data_names_updated(self, context):
    """Callback update= del BoolProperty de preferencias."""
    try:
        set_handler_enabled(bool(self.sync_data_names))
    except Exception as exc:
        log_exception("No se pudo cambiar el estado del handler de sincronizacion", exc)


def refresh_handler_from_prefs():
    """Realinea el handler con el valor guardado de la preferencia.

    Se llama desde register(): las preferencias persisten entre sesiones, pero los
    handlers no, asi que si el toggle quedo activo hay que volver a registrarlo.
    """
    try:
        set_handler_enabled(get_sync_enabled())
    except Exception as exc:
        log_exception("No se pudo restaurar el handler de sincronizacion", exc)


def remove_handler():
    """Retira el handler incondicionalmente. Se llama desde unregister()."""
    try:
        set_handler_enabled(False)
    except Exception as exc:
        log_exception("No se pudo retirar el handler de sincronizacion", exc)
