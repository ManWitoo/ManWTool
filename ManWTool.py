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

from bpy.types import Panel, Operator, PropertyGroup, AddonPreferences
from bpy.props import PointerProperty, StringProperty
from bpy_extras.io_utils import ExportHelper


ADDON_ID = __name__
_preview_col = None  # logo


# -------------------------------------------------
# Preferencias (logo)
# -------------------------------------------------
class MANWTOOL_Preferences(AddonPreferences):
    bl_idname = ADDON_ID

    logo_path: StringProperty(
        name="Logo (PNG)",
        description="Selecciona un PNG para mostrarlo como logo en la cabecera del addon",
        subtype="FILE_PATH",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Preferencias de ManWTool")
        layout.prop(self, "logo_path")
        layout.label(text="Sugerencia: PNG cuadrado (128x128 o 256x256).")


def _reload_logo():
    global _preview_col
    if _preview_col is None:
        return

    prefs = bpy.context.preferences.addons[ADDON_ID].preferences
    path = bpy.path.abspath(prefs.logo_path) if prefs.logo_path else ""
    key = "manwtool_logo"

    # limpiar si ya existía
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
# Propiedades
# -------------------------------------------------
class MANWTOOL_Properties(PropertyGroup):
    # Colecciones
    root_name: StringProperty(
        name="Raíz",
        description="Nombre de la colección raíz (p.ej. 'Robot01')",
        default="Asset",
    )

    # Renombrado
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

    # Export
    last_export_dir: StringProperty(
        name="Última carpeta",
        description="Carpeta usada en el último export. Se usa para ReExport.",
        subtype="DIR_PATH",
        default="",
    )


# -------------------------------------------------
# UI helpers (más elegante)
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

    # Cabecera con logo + nombre + versión
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


def _big_button(row_or_layout):
    r = row_or_layout.row()
    r.scale_y = 1.35
    return r


# -------------------------------------------------
# Export core (compartido por Export / ReExport)
# -------------------------------------------------
def _export_active_mesh_to_fbx(context, base_dir, report_fn):
    """
    Exporta el objeto activo (MESH) a:
    base_dir/<NombreObjeto>/<NombreObjeto>.fbx
    Aplicando: modificadores bakeados (copia), rot/scale, origin al centro, location (0,0,0).
    """
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
        # si es una ruta nueva, intentamos crearla
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            report_fn({"ERROR"}, "No se pudo crear/usar la carpeta de exportación.")
            return False

    export_dir = os.path.join(base_dir, export_name)
    os.makedirs(export_dir, exist_ok=True)
    final_fbx_path = os.path.join(export_dir, f"{export_name}.fbx")

    # Bake modificadores (copia no destructiva)
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

    # Materiales (por seguridad)
    if src.data and src.data.materials:
        baked_mesh.materials.clear()
        for m in src.data.materials:
            baked_mesh.materials.append(m)

    # Colección temporal
    tmp_col = bpy.data.collections.get("_ManWTool_EXPORT_TMP")
    if tmp_col is None:
        tmp_col = bpy.data.collections.new("_ManWTool_EXPORT_TMP")
        context.scene.collection.children.link(tmp_col)
    tmp_col.objects.link(tmp_obj)

    # Copiar transform inicial
    tmp_obj.matrix_world = src.matrix_world.copy()

    # Guardar selección previa
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_sel = [o for o in context.selected_objects]

    # Seleccionar solo temporal
    for o in prev_sel:
        o.select_set(False)
    tmp_obj.select_set(True)
    view_layer.objects.active = tmp_obj

    # Orden pedido
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    tmp_obj.location = (0.0, 0.0, 0.0)

    # Export FBX solo selección
    bpy.ops.export_scene.fbx(
        filepath=final_fbx_path,
        use_selection=True,
        object_types={'MESH'},
        apply_unit_scale=True,
        axis_forward='-Z',
        axis_up='Y',
        add_leaf_bones=False,
        use_mesh_modifiers=False,  # ya bakeado
    )

    # Restaurar selección
    tmp_obj.select_set(False)
    for o in prev_sel:
        if o and o.name in bpy.data.objects:
            o.select_set(True)
    if prev_active and prev_active.name in bpy.data.objects:
        view_layer.objects.active = prev_active

    # Limpiar temporal
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
# Operador 1: colecciones
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


# -------------------------------------------------
# Operador 2: renombrar + data + material
# -------------------------------------------------
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


# -------------------------------------------------
# Operador 3: Export FBX (selector + guarda última carpeta)
# -------------------------------------------------
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
        # El file browser devuelve una ruta de archivo; nosotros usamos su carpeta
        chosen_dir = os.path.dirname(self.filepath) if self.filepath else ""
        if not chosen_dir:
            self.report({"ERROR"}, "Ruta de exportación no válida.")
            return {"CANCELLED"}

        # Guardar última carpeta para ReExport
        props = context.scene.manwtool_props
        props.last_export_dir = chosen_dir

        ok = _export_active_mesh_to_fbx(context, chosen_dir, self.report)
        return {"FINISHED"} if ok else {"CANCELLED"}


# -------------------------------------------------
# Operador 4: ReExport (sin selector)
# -------------------------------------------------
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
# Base panel
# -------------------------------------------------
class MANWTOOL_PT_base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ManWTool"


# -------------------------------------------------
# Panel 1: Carpetas / Colecciones (SIN estado)
# -------------------------------------------------
class MANWTOOL_PT_folders(MANWTOOL_PT_base):
    bl_label = "Carpetas / Colecciones"
    bl_idname = "MANWTOOL_PT_folders"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        _draw_header(self, context, show_status=False)  # SOLO aquí sin estado
        layout = self.layout
        props = context.scene.manwtool_props

        box = layout.box()
        box.label(text="Estructura de colecciones", icon="OUTLINER_COLLECTION")

        row = box.row(align=True)
        row.prop(props, "root_name", text="Raíz")

        box.separator()
        btn = _big_button(box)
        btn.operator("manwtool.create_folders", icon="PLUS")


# -------------------------------------------------
# Panel 2: Renombrar (CON estado)
# -------------------------------------------------
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


# -------------------------------------------------
# Panel 3: Export (CON estado + ReExport)
# -------------------------------------------------
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

        # Info pequeña, elegante
        info = box.column(align=True)
        info.enabled = False
        info.label(text="• Modificadores bakeados (copia temporal)")
        info.label(text="• Rot/Scale aplicados + Origin al centro")
        info.label(text="• Posición a (0,0,0) + carpeta por objeto")

        # Última carpeta
        last = bpy.path.abspath(props.last_export_dir) if props.last_export_dir else ""
        row = box.row()
        row.label(text="Última carpeta:", icon="FILE_FOLDER")
        row2 = box.row()
        row2.enabled = False
        row2.label(text=last if last else "—")

        box.separator()

        obj = context.active_object
        can_run = (obj is not None and obj.type == "MESH")

        # Botones en fila (Export / ReExport)
        row = box.row(align=True)
        row.scale_y = 1.35

        b1 = row.operator("manwtool.export_fbx", text="Export", icon="EXPORT")
        # b1 es solo estético; enable va sobre la fila/botón
        row.enabled = can_run

        # Para que ReExport dependa también de tener carpeta guardada:
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


def unregister():
    global _preview_col

    del bpy.types.Scene.manwtool_props

    for c in reversed(classes):
        bpy.utils.unregister_class(c)

    if _preview_col is not None:
        bpy.utils.previews.remove(_preview_col)
        _preview_col = None


if __name__ == "__main__":
    register()
