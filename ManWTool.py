bl_info = {
    "name": "ManWTool",
    "author": "Jairo (ManW)",
    "version": (0, 0, 7),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > ManWTool",
    "description": "Colecciones, renombrado y export FBX con ReExport.",
    "category": "3D View",
}

import os
import bpy
import bpy.utils.previews
import threading
import urllib.request
import json
import zipfile
import tempfile
import shutil

from bpy.types import Panel, Operator, PropertyGroup, AddonPreferences
from bpy.props import PointerProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper
from bpy.app.handlers import persistent


ADDON_ID = __name__
_preview_col = None  # logo

# ⚠️ SOLO CAMBIA ESTO: tu usuario y nombre del repositorio de GitHub
GITHUB_USER = "Man"      # 👈 Cambia esto
GITHUB_REPO = "ManWTool"        # 👈 Cambia esto

# Variable global para almacenar info de actualización
_update_info = {
    "checking": False,
    "available": False,
    "version": None,
    "download_url": None,
    "notes": "",
    "error": None,
}


# -------------------------------------------------
# Preferencias (logo + auto-update)
# -------------------------------------------------
class MANWTOOL_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    logo_path: StringProperty(
        name="Logo (PNG)",
        description="Selecciona un PNG para mostrarlo como logo en la cabecera del addon",
        subtype="FILE_PATH",
        default="",
    )
    
    auto_check_updates: BoolProperty(
        name="Verificar actualizaciones al iniciar",
        description="Comprobar automáticamente si hay nuevas versiones al abrir Blender",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Preferencias de ManWTool")
        
        box = layout.box()
        box.label(text="Apariencia:", icon="IMAGE_DATA")
        box.prop(self, "logo_path")
        box.label(text="Sugerencia: PNG cuadrado (128x128 o 256x256).")
        
        box = layout.box()
        box.label(text="Actualizaciones:", icon="URL")
        box.prop(self, "auto_check_updates")
        box.label(text=f"Repo: {GITHUB_USER}/{GITHUB_REPO}", icon="GITHUB")
        
        row = box.row()
        row.operator("manwtool.check_updates", icon="FILE_REFRESH")


def _reload_logo():
    global _preview_col
    if _preview_col is None:
        return

    prefs = bpy.context.preferences.addons[ADDON_ID].preferences
    path = bpy.path.abspath(prefs.logo_path) if prefs.logo_path else ""
    key = "manwtool_logo"

    if key in _preview_col:
        try:
            _preview_col.remove(_preview_col[key])
        except Exception:
            pass

    if not path or not os.path.isfile(path):
        return

    try:
        _preview_col.load(key, path, "IMAGE")
    except Exception:
        pass


def _get_logo_icon_value():
    global _preview_col
    if _preview_col is None:
        return None
    key = "manwtool_logo"
    if key in _preview_col:
        return _preview_col[key].icon_id
    return None


# -------------------------------------------------
# Sistema de actualización simplificado
# -------------------------------------------------
def _compare_versions(current, remote):
    """Compara dos tuplas de versión. Retorna True si remote > current"""
    return remote > current


def _check_for_updates_thread():
    """Verifica actualizaciones consultando GitHub Releases API"""
    global _update_info
    
    _update_info["checking"] = True
    _update_info["error"] = None
    
    try:
        # Consultar la última release de GitHub
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
        
        req = urllib.request.Request(api_url)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        # Extraer versión del tag (ej: "v0.0.8" o "0.0.8")
        tag_name = data.get("tag_name", "").replace("v", "").replace("V", "")
        version_parts = tag_name.split(".")
        
        if len(version_parts) >= 3:
            remote_version = tuple(int(x) for x in version_parts[:3])
            current_version = bl_info["version"]
            
            if _compare_versions(current_version, remote_version):
                # Buscar el asset .zip en la release
                download_url = None
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".zip"):
                        download_url = asset["browser_download_url"]
                        break
                
                if download_url:
                    _update_info["available"] = True
                    _update_info["version"] = remote_version
                    _update_info["download_url"] = download_url
                    _update_info["notes"] = data.get("body", "")[:200]  # Primeras 200 chars
                else:
                    _update_info["error"] = "No se encontró archivo .zip en la release"
            else:
                _update_info["available"] = False
        else:
            _update_info["error"] = "Formato de versión no válido en GitHub"
            
    except Exception as e:
        _update_info["error"] = f"Error al conectar: {str(e)[:50]}"
        _update_info["available"] = False
    
    finally:
        _update_info["checking"] = False


def _download_and_install_update(download_url):
    """Descarga e instala la actualización"""
    try:
        # Crear carpeta temporal
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, "update.zip")
        
        # Descargar el archivo
        urllib.request.urlretrieve(download_url, zip_path)
        
        # Extraer
        extract_dir = os.path.join(temp_dir, "extracted")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Encontrar el archivo .py principal
        addon_file = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if "bl_info" in content:
                                addon_file = file_path
                                break
                    except:
                        continue
            if addon_file:
                break
        
        if not addon_file:
            return False, "No se encontró el archivo del addon en la descarga"
        
        # Obtener la ruta del addon actual
        current_file = os.path.realpath(__file__)
        
        # Copiar el nuevo archivo sobre el actual
        shutil.copy2(addon_file, current_file)
        
        # Limpiar archivos temporales
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return True, "�?Actualización instalada. Reinicia Blender para aplicar cambios."
        
    except Exception as e:
        return False, f"Error: {str(e)}"


# -------------------------------------------------
# Operadores de actualización
# -------------------------------------------------
class MANWTOOL_OT_check_updates(Operator):
    bl_idname = "manwtool.check_updates"
    bl_label = "Verificar Actualizaciones"
    bl_description = "Comprobar si hay una nueva versión disponible en GitHub"
    
    def execute(self, context):
        if not GITHUB_USER or GITHUB_USER == "TU_USUARIO":
            self.report({"ERROR"}, "Configura GITHUB_USER y GITHUB_REPO en el código")
            return {"CANCELLED"}
        
        # Ejecutar en hilo separado para no bloquear la UI
        thread = threading.Thread(target=_check_for_updates_thread)
        thread.daemon = True
        thread.start()
        
        self.report({"INFO"}, "Verificando actualizaciones...")
        return {"FINISHED"}


class MANWTOOL_OT_install_update(Operator):
    bl_idname = "manwtool.install_update"
    bl_label = "Instalar Actualización"
    bl_description = "Descargar e instalar la nueva versión"
    
    def execute(self, context):
        global _update_info
        
        if not _update_info["available"] or not _update_info["download_url"]:
            self.report({"ERROR"}, "No hay actualización disponible")
            return {"CANCELLED"}
        
        self.report({"INFO"}, "Descargando actualización...")
        
        success, message = _download_and_install_update(_update_info["download_url"])
        
        if success:
            self.report({"INFO"}, message)
            _update_info["available"] = False
        else:
            self.report({"ERROR"}, message)
        
        return {"FINISHED"}


class MANWTOOL_OT_dismiss_update(Operator):
    bl_idname = "manwtool.dismiss_update"
    bl_label = "Más Tarde"
    bl_description = "Ocultar la notificación de actualización por ahora"
    
    def execute(self, context):
        global _update_info
        _update_info["available"] = False
        return {"FINISHED"}


# -------------------------------------------------
# Auto-check al iniciar Blender
# -------------------------------------------------
@persistent
def _auto_check_updates(dummy):
    """Se ejecuta al cargar un archivo .blend"""
    try:
        prefs = bpy.context.preferences.addons[ADDON_ID].preferences
        if prefs.auto_check_updates and GITHUB_USER != "TU_USUARIO":
            thread = threading.Thread(target=_check_for_updates_thread)
            thread.daemon = True
            thread.start()
    except Exception:
        pass


# -------------------------------------------------
# Propiedades
# -------------------------------------------------
class MANWTOOL_Properties(PropertyGroup):
    root_name: StringProperty(
        name="Raíz",
        description="Nombre de la colección raíz (p.ej. 'Robot01')",
        default="Asset",
    )

    rename_prefix: StringProperty(
        name="Prefijo",
        description="Prefijo a añadir (p.ej. 'SM_', 'GEO_', etc.)",
        default="SM_",
    )
    rename_base: StringProperty(
        name="Nombre",
        description="Nombre base del objeto (sin prefijo).",
        default="Object",
    )

    last_export_dir: StringProperty(
        name="Última carpeta",
        description="Carpeta usada en el último export. Se usa para ReExport.",
        subtype="DIR_PATH",
        default="",
    )


# -------------------------------------------------
# UI helpers
# -------------------------------------------------
def _active_obj_status(context):
    obj = context.active_object
    if obj is None:
        return ("Sin objeto activo", "ERROR", "ERROR")
    if obj.type != "MESH":
        return (f"Activo: {obj.name} ({obj.type})", "WARNING", "ERROR")
    return (f"Activo: {obj.name} (MESH)", "INFO", "MESH_CUBE")


def _draw_header(panel, context, show_status=True):
    layout = panel.layout

    icon_value = _get_logo_icon_value()
    row = layout.row(align=True)

    title = "ManWTool"
    ver = ".".join(map(str, bl_info["version"]))

    if icon_value:
        row.label(text=f"{title}  v{ver}", icon_value=icon_value)
    else:
        row.label(text=f"{title}  v{ver}", icon="TOOL_SETTINGS")

    if not show_status:
        return

    status, level, icon = _active_obj_status(context)
    row2 = layout.row()
    if level in {"ERROR", "WARNING"}:
        row2.alert = True
    row2.label(text=status, icon=icon if icon else "INFO")


def _draw_update_notification(layout):
    """Dibuja la notificación de actualización si está disponible"""
    global _update_info
    
    if _update_info["checking"]:
        box = layout.box()
        row = box.row()
        row.label(text="🔄 Verificando actualizaciones...", icon="SORTTIME")
        return
    
    if _update_info["error"]:
        # No mostrar errores de forma intrusiva
        return
    
    if _update_info["available"]:
        box = layout.box()
        box.alert = True
        
        # Título
        row = box.row()
        ver_str = ".".join(map(str, _update_info["version"]))
        row.label(text=f"🎉 Nueva versión: v{ver_str}", icon="INFO")
        
        # Notas (máximo 2 líneas)
        if _update_info["notes"]:
            col = box.column(align=True)
            col.scale_y = 0.8
            lines = _update_info["notes"].split("\n")[:2]
            for line in lines:
                if line.strip():
                    col.label(text=line[:50])
        
        # Botones
        row = box.row(align=True)
        row.scale_y = 1.2
        row.operator("manwtool.install_update", text="Actualizar", icon="IMPORT")
        row.operator("manwtool.dismiss_update", text="Más Tarde", icon="X")


def _big_button(row_or_layout):
    r = row_or_layout.row()
    r.scale_y = 1.35
    return r


# -------------------------------------------------
# Export core
# -------------------------------------------------
def _export_active_mesh_to_fbx(context, base_dir, report_fn):
    src = context.active_object
    if src is None:
        report_fn({"ERROR"}, "No hay objeto activo.")
        return False
    if src.type != "MESH":
        report_fn({"ERROR"}, "El objeto activo no es un MESH.")
        return False

    export_name = src.name

    if not base_dir:
        report_fn({"ERROR"}, "Carpeta de exportación no válida.")
        return False

    base_dir = bpy.path.abspath(base_dir)
    if not os.path.isdir(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            report_fn({"ERROR"}, "No se pudo crear/usar la carpeta de exportación.")
            return False

    export_dir = os.path.join(base_dir, export_name)
    os.makedirs(export_dir, exist_ok=True)
    final_fbx_path = os.path.join(export_dir, f"{export_name}.fbx")

    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = src.evaluated_get(depsgraph)

    try:
        baked_mesh = bpy.data.meshes.new_from_object(
            eval_obj,
            preserve_all_data_layers=True,
            depsgraph=depsgraph
        )
    except TypeError:
        baked_mesh = bpy.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True)

    tmp_obj = bpy.data.objects.new(f"{export_name}_EXPORT_TMP", baked_mesh)

    if src.data and src.data.materials:
        baked_mesh.materials.clear()
        for m in src.data.materials:
            baked_mesh.materials.append(m)

    tmp_col = bpy.data.collections.get("_ManWTool_EXPORT_TMP")
    if tmp_col is None:
        tmp_col = bpy.data.collections.new("_ManWTool_EXPORT_TMP")
        context.scene.collection.children.link(tmp_col)
    tmp_col.objects.link(tmp_obj)

    tmp_obj.matrix_world = src.matrix_world.copy()

    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_sel = [o for o in context.selected_objects]

    for o in prev_sel:
        o.select_set(False)
    tmp_obj.select_set(True)
    view_layer.objects.active = tmp_obj

    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    tmp_obj.location = (0.0, 0.0, 0.0)

    bpy.ops.export_scene.fbx(
        filepath=final_fbx_path,
        use_selection=True,
        object_types={'MESH'},
        apply_unit_scale=True,
        axis_forward='-Z',
        axis_up='Y',
        add_leaf_bones=False,
        use_mesh_modifiers=False,
    )

    tmp_obj.select_set(False)
    for o in prev_sel:
        if o and o.name in bpy.data.objects:
            o.select_set(True)
    if prev_active and prev_active.name in bpy.data.objects:
        view_layer.objects.active = prev_active

    try:
        tmp_col.objects.unlink(tmp_obj)
    except Exception:
        pass
    bpy.data.objects.remove(tmp_obj, do_unlink=True)
    bpy.data.meshes.remove(baked_mesh, do_unlink=True)

    if tmp_col and len(tmp_col.objects) == 0:
        try:
            context.scene.collection.children.unlink(tmp_col)
        except Exception:
            pass
        bpy.data.collections.remove(tmp_col)

    report_fn({"INFO"}, f"Exportado: {final_fbx_path}")
    return True


# -------------------------------------------------
# Operadores
# -------------------------------------------------
class MANWTOOL_OT_create_folders(Operator):
    bl_idname = "manwtool.create_folders"
    bl_label = "Crear estructura"
    bl_description = "Crea una colección raíz y tres sub-colecciones: _High, _Low, _Reference"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.manwtool_props
        base = (props.root_name or "").strip()
        if not base:
            self.report({"ERROR"}, "Escribe un nombre para la raíz.")
            return {"CANCELLED"}

        name_root = base
        name_high = f"{base}_High"
        name_low = f"{base}_Low"
        name_ref = f"{base}_Reference"

        root_col = bpy.data.collections.get(name_root)
        if root_col is None:
            root_col = bpy.data.collections.new(name_root)
            context.scene.collection.children.link(root_col)
        else:
            if root_col.name not in context.scene.collection.children:
                context.scene.collection.children.link(root_col)

        def ensure_child(parent, child_name):
            col = bpy.data.collections.get(child_name)
            if col is None:
                col = bpy.data.collections.new(child_name)
            if col.name not in parent.children:
                parent.children.link(col)
            return col

        col_high = ensure_child(root_col, name_high)
        col_low = ensure_child(root_col, name_low)
        col_ref = ensure_child(root_col, name_ref)

        col_high.color_tag = "COLOR_01"
        col_low.color_tag = "COLOR_03"
        col_ref.color_tag = "COLOR_05"

        self.report({"INFO"}, "Estructura creada.")
        return {"FINISHED"}


class MANWTOOL_OT_rename_geo_data_material(Operator):
    bl_idname = "manwtool.rename_geo_data_material"
    bl_label = "Aplicar nombre"
    bl_description = "Renombra el objeto activo, su data y asigna/crea un material con el mismo nombre"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({"ERROR"}, "No hay objeto activo.")
            return {"CANCELLED"}
        if obj.type != "MESH":
            self.report({"ERROR"}, "El objeto activo no es un MESH.")
            return {"CANCELLED"}

        props = context.scene.manwtool_props
        prefix = (props.rename_prefix or "").strip()
        base = (props.rename_base or "").strip()
        if not base:
            self.report({"ERROR"}, "Escribe un nombre.")
            return {"CANCELLED"}

        final_name = f"{prefix}{base}"

        obj.name = final_name
        if obj.data:
            obj.data.name = final_name

        mat = bpy.data.materials.get(final_name)
        if mat is None:
            mat = bpy.data.materials.new(name=final_name)
            mat.use_nodes = True

        mats = obj.data.materials
        if len(mats) == 0:
            mats.append(mat)
        else:
            mats[0] = mat

        self.report({"INFO"}, f"OK: {final_name}")
        return {"FINISHED"}


class MANWTOOL_OT_export_fbx(Operator, ExportHelper):
    bl_idname = "manwtool.export_fbx"
    bl_label = "Exportar FBX"
    bl_description = "Exporta el objeto activo a FBX (crea carpeta automática por objeto)"
    bl_options = {"REGISTER"}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def invoke(self, context, event):
        obj = context.active_object
        if obj:
            self.filepath = f"{obj.name}.fbx"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        chosen_dir = os.path.dirname(self.filepath) if self.filepath else ""
        if not chosen_dir:
            self.report({"ERROR"}, "Ruta de exportación no válida.")
            return {"CANCELLED"}

        props = context.scene.manwtool_props
        props.last_export_dir = chosen_dir

        ok = _export_active_mesh_to_fbx(context, chosen_dir, self.report)
        return {"FINISHED"} if ok else {"CANCELLED"}


class MANWTOOL_OT_reexport_fbx(Operator):
    bl_idname = "manwtool.reexport_fbx"
    bl_label = "ReExport"
    bl_description = "Reexporta usando la última carpeta guardada"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.manwtool_props
        base_dir = (props.last_export_dir or "").strip()
        if not base_dir:
            self.report({"ERROR"}, "No hay carpeta guardada. Haz un Export primero.")
            return {"CANCELLED"}

        ok = _export_active_mesh_to_fbx(context, base_dir, self.report)
        return {"FINISHED"} if ok else {"CANCELLED"}


# -------------------------------------------------
# Panels
# -------------------------------------------------
class MANWTOOL_PT_base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ManWTool"


class MANWTOOL_PT_folders(MANWTOOL_PT_base):
    bl_label = "Carpetas / Colecciones"
    bl_idname = "MANWTOOL_PT_folders"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_header(self, context, show_status=False)
        
        # Mostrar notificación de actualización
        _draw_update_notification(self.layout)
        
        layout = self.layout
        props = context.scene.manwtool_props

        box = layout.box()
        box.label(text="Estructura de colecciones", icon="OUTLINER_COLLECTION")

        row = box.row(align=True)
        row.prop(props, "root_name", text="Raíz")

        box.separator()
        btn = _big_button(box)
        btn.operator("manwtool.create_folders", icon="PLUS")


class MANWTOOL_PT_rename(MANWTOOL_PT_base):
    bl_label = "Geo / Data / Material"
    bl_idname = "manwtool_pt_rename"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_header(self, context, show_status=True)
        layout = self.layout
        props = context.scene.manwtool_props

        box = layout.box()
        box.label(text="Naming consistente", icon="FILE_TEXT")

        col = box.column(align=True)
        col.prop(props, "rename_prefix")
        col.prop(props, "rename_base")

        final_name = f"{(props.rename_prefix or '').strip()}{(props.rename_base or '').strip()}"
        sub = box.box()
        sub.enabled = False
        sub.label(text=f"Resultado: {final_name}", icon="CHECKMARK")

        box.separator()

        obj = context.active_object
        can_run = (obj is not None and obj.type == "MESH")
        btn = _big_button(box)
        btn.enabled = can_run
        btn.operator("manwtool.rename_geo_data_material", icon="FILE_TICK")


class MANWTOOL_PT_export(MANWTOOL_PT_base):
    bl_label = "Exportación"
    bl_idname = "MANWTOOL_PT_export"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_header(self, context, show_status=True)
        layout = self.layout
        props = context.scene.manwtool_props

        box = layout.box()
        box.label(text="FBX (Substance-friendly)", icon="EXPORT")

        info = box.column(align=True)
        info.enabled = False
        info.label(text="�?Modificadores bakeados (copia temporal)")
        info.label(text="�?Rot/Scale aplicados + Origin al centro")
        info.label(text="�?Posición a (0,0,0) + carpeta por objeto")

        last = bpy.path.abspath(props.last_export_dir) if props.last_export_dir else ""
        row = box.row()
        row.label(text="Última carpeta:", icon="FILE_FOLDER")
        row2 = box.row()
        row2.enabled = False
        row2.label(text=last if last else "�?)

        box.separator()

        obj = context.active_object
        can_run = (obj is not None and obj.type == "MESH")

        row = box.row(align=True)
        row.scale_y = 1.35
        b1 = row.operator("manwtool.export_fbx", text="Export", icon="EXPORT")
        row.enabled = can_run

        row2 = box.row(align=True)
        row2.scale_y = 1.35
        row2.enabled = can_run and bool((props.last_export_dir or "").strip())
        row2.operator("manwtool.reexport_fbx", text="ReExport", icon="FILE_REFRESH")


# -------------------------------------------------
# Registro
# -------------------------------------------------
classes = (
    MANWTOOL_Preferences,
    MANWTOOL_Properties,
    MANWTOOL_OT_create_folders,
    MANWTOOL_OT_rename_geo_data_material,
    MANWTOOL_OT_export_fbx,
    MANWTOOL_OT_reexport_fbx,
    MANWTOOL_OT_check_updates,
    MANWTOOL_OT_install_update,
    MANWTOOL_OT_dismiss_update,
    MANWTOOL_PT_folders,
    MANWTOOL_PT_rename,
    MANWTOOL_PT_export,
)


def register():
    global _preview_col
    _preview_col = bpy.utils.previews.new()

    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.manwtool_props = PointerProperty(type=MANWTOOL_Properties)

    _reload_logo()
    
    # Registrar handler para auto-check de actualizaciones
    if _auto_check_updates not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_auto_check_updates)


def unregister():
    global _preview_col

    # Remover handler
    if _auto_check_updates in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_auto_check_updates)

    del bpy.types.Scene.manwtool_props

    for c in reversed(classes):
        bpy.utils.unregister_class(c)

    if _preview_col is not None:
        bpy.utils.previews.remove(_preview_col)
        _preview_col = None


if __name__ == "__main__":
    register()
