from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences, PropertyGroup

from .manwtool_collections import COLLECTION_TARGET_ITEMS, get_collection_target_items
from .manwtool_core import DEFAULT_REPO_NAME, DEFAULT_REPO_OWNER, current_version_str
from .manwtool_export import AXIS_ITEMS, EXPORT_PRESET_ITEMS, get_export_preset_items
from .manwtool_i18n import LANGUAGE_ITEMS, tr
from .manwtool_sync import on_sync_data_names_updated


def get_ui_section_items(_self=None, _context=None):
    return [
        ("SUMMARY", tr("ui.section.summary"), ""),
        ("FOLDERS", tr("ui.section.folders"), ""),
        ("RENAME", tr("ui.section.rename"), ""),
        ("TRANSFORM", tr("ui.section.transform"), ""),
        ("EXPORT", tr("ui.section.export"), ""),
        ("IMPORT", tr("ui.section.import"), ""),
    ]


def get_rename_affix_mode_items(_self=None, _context=None):
    return [
        ("PREFIX", tr("ui.naming.mode.prefix"), ""),
        ("SUFFIX", tr("ui.naming.mode.suffix"), ""),
        ("BOTH", tr("ui.naming.mode.both"), ""),
    ]


UI_SECTION_ITEMS = [
    ("SUMMARY", "Summary", ""),
    ("FOLDERS", "Collections", ""),
    ("RENAME", "Rename", ""),
    ("TRANSFORM", "Transform", ""),
    ("EXPORT", "Export", ""),
    ("IMPORT", "Import", ""),
]


RENAME_AFFIX_MODE_ITEMS = [
    ("PREFIX", "Prefix", ""),
    ("SUFFIX", "Suffix", ""),
    ("BOTH", "Both", ""),
]


SYNC_SCOPE_ITEMS = [
    ("SELECTED", "Selected", ""),
    ("SCENE", "Scene", ""),
    ("FILE", "File", ""),
]


class MANWTOOL_Preferences(AddonPreferences):
    bl_idname = "ManWTool"

    ui_language: EnumProperty(name="Language", items=LANGUAGE_ITEMS, default="AUTO")
    logo_path: StringProperty(name="Logo (PNG)", subtype="FILE_PATH", default="")
    repo_owner: StringProperty(name="GitHub Owner", default=DEFAULT_REPO_OWNER)
    repo_name: StringProperty(name="GitHub Repo", default=DEFAULT_REPO_NAME)
    asset_name_contains: StringProperty(name="Filtro ZIP", default="ManWTool")
    auto_check_updates: BoolProperty(name="Comprobar al iniciar", default=True)
    allow_in_app_update_install: BoolProperty(name="Permitir instalacion directa", default=False)
    check_interval_days: IntProperty(name="Intervalo (dias)", default=1, min=1, max=30)
    debug_logging: BoolProperty(name="Debug logging", default=False)
    sync_data_names: BoolProperty(
        name="Sync Mesh Names on Rename",
        description=(
            "When renaming an object, also rename its data-block. "
            "Does not affect data-blocks shared by multiple objects, nor linked data."
        ),
        default=False,
        update=on_sync_data_names_updated,
    )
    last_check_time: FloatProperty(default=0.0)
    update_available: BoolProperty(default=False)
    latest_version: StringProperty(default="")
    latest_download_url: StringProperty(default="")
    latest_download_kind: StringProperty(default="ZIP")
    latest_release_url: StringProperty(default="")
    last_update_error: StringProperty(default="")
    last_notified_version: StringProperty(default="")
    restart_required: BoolProperty(default=False)
    license_server_url: StringProperty(name="License Server", default="")
    license_email: StringProperty(name="Email licencia", default="")
    license_key: StringProperty(name="Clave licencia", default="")
    license_active: BoolProperty(default=False)
    license_status: StringProperty(default=tr("state.license.inactive"))
    license_valid_until: StringProperty(default="")
    license_last_check: StringProperty(default="")
    license_hardware_id: StringProperty(default="")
    unreal_axis_forward: EnumProperty(name="Axis Forward", items=AXIS_ITEMS, default="-Z")
    unreal_axis_up: EnumProperty(name="Axis Up", items=AXIS_ITEMS, default="Y")
    unreal_apply_unit_scale: BoolProperty(name="Apply Unit Scale", default=True)
    unreal_use_mesh_modifiers: BoolProperty(name="Usar modificadores", default=False)
    unity_axis_forward: EnumProperty(name="Axis Forward", items=AXIS_ITEMS, default="-Z")
    unity_axis_up: EnumProperty(name="Axis Up", items=AXIS_ITEMS, default="Y")
    unity_apply_unit_scale: BoolProperty(name="Apply Unit Scale", default=True)
    unity_use_mesh_modifiers: BoolProperty(name="Usar modificadores", default=False)
    highpoly_axis_forward: EnumProperty(name="Axis Forward", items=AXIS_ITEMS, default="-Z")
    highpoly_axis_up: EnumProperty(name="Axis Up", items=AXIS_ITEMS, default="Y")
    highpoly_apply_unit_scale: BoolProperty(name="Apply Unit Scale", default=True)
    highpoly_use_mesh_modifiers: BoolProperty(name="Usar modificadores", default=True)
    lowpoly_axis_forward: EnumProperty(name="Axis Forward", items=AXIS_ITEMS, default="-Z")
    lowpoly_axis_up: EnumProperty(name="Axis Up", items=AXIS_ITEMS, default="Y")
    lowpoly_apply_unit_scale: BoolProperty(name="Apply Unit Scale", default=True)
    lowpoly_use_mesh_modifiers: BoolProperty(name="Usar modificadores", default=False)
    custom_axis_forward: EnumProperty(name="Axis Forward", items=AXIS_ITEMS, default="-Z")
    custom_axis_up: EnumProperty(name="Axis Up", items=AXIS_ITEMS, default="Y")
    custom_apply_unit_scale: BoolProperty(name="Apply Unit Scale", default=True)
    custom_use_mesh_modifiers: BoolProperty(name="Usar modificadores", default=False)

    def draw(self, context):
        layout = self.layout

        logo = layout.box()
        logo.label(text=tr("prefs.appearance"), icon="IMAGE_DATA")
        logo.prop(self, "ui_language", text=tr("addon.language"))
        logo.prop(self, "logo_path", text=tr("prefs.label.logo_path"))

        box = layout.box()
        box.label(text=tr("prefs.auto_update"), icon="FILE_REFRESH")
        col = box.column(align=True)
        col.prop(self, "repo_owner", text=tr("prefs.label.repo_owner"))
        col.prop(self, "repo_name", text=tr("prefs.label.repo_name"))
        col.prop(self, "asset_name_contains", text=tr("prefs.label.asset_name_contains"))

        row = box.row(align=True)
        row.prop(self, "auto_check_updates", text=tr("prefs.label.auto_check_updates"))
        row.prop(self, "check_interval_days", text=tr("prefs.label.check_interval_days"))
        box.prop(self, "allow_in_app_update_install", text=tr("prefs.label.allow_in_app_update_install"))
        warn = box.box()
        warn.enabled = False
        warn.label(text=tr("prefs.update_sales_hint"))
        box.operator("manwtool.check_updates", text=tr("prefs.check_now"), icon="VIEWZOOM")

        if self.update_available:
            update_box = box.box()
            update_box.alert = True
            update_box.label(
                text=tr("prefs.update_available", latest=self.latest_version, current=current_version_str()),
                icon="INFO",
            )
            row = update_box.row(align=True)
            row.enabled = self.allow_in_app_update_install
            row.operator("manwtool.install_update", text=tr("ui.update"), icon="IMPORT")
            if self.latest_release_url:
                release_row = update_box.row(align=True)
                release_row.operator("manwtool.open_release_page", text=tr("ui.release"), icon="URL")

        if self.restart_required:
            restart_box = box.box()
            restart_box.alert = True
            restart_box.label(text=tr("prefs.update_installed_restart"), icon="ERROR")
            restart_box.operator("manwtool.clear_restart_flag", text=tr("prefs.hide_notice"), icon="CHECKMARK")

        if self.last_update_error:
            err = box.box()
            err.alert = True
            err.label(text=f"Error: {self.last_update_error}", icon="ERROR")

        renaming = layout.box()
        renaming.label(text=tr("prefs.renaming"), icon="FILE_TEXT")
        renaming.prop(self, "sync_data_names", text=tr("ui.sync.toggle"))
        sync_hint = renaming.box()
        sync_hint.enabled = False
        sync_hint.label(text=tr("ui.sync.toggle_hint"))

        debug = layout.box()
        debug.label(text=tr("prefs.debug"), icon="CONSOLE")
        debug.prop(self, "debug_logging", text=tr("prefs.label.debug_logging"))

        license_box = layout.box()
        license_box.label(text=tr("prefs.license"), icon="KEYINGSET")
        license_box.prop(self, "license_server_url", text=tr("prefs.label.license_server_url"))
        license_box.prop(self, "license_email", text=tr("prefs.label.license_email"))
        license_box.prop(self, "license_key", text=tr("prefs.label.license_key"))
        row = license_box.row(align=True)
        row.operator("manwtool.activate_license", text=tr("prefs.activate_license"), icon="CHECKMARK")
        row.operator("manwtool.clear_license_cache", text=tr("prefs.clear_license"), icon="TRASH")

        status = license_box.box()
        status.enabled = False
        status.label(text=tr("prefs.status", status=self.license_status))
        if self.license_valid_until:
            status.label(text=tr("prefs.valid_until", value=self.license_valid_until))
        if self.license_last_check:
            status.label(text=tr("prefs.last_check", value=self.license_last_check))
        if self.license_hardware_id:
            status.label(text=tr("prefs.hardware_id", value=self.license_hardware_id))


class MANWTOOL_Properties(PropertyGroup):
    ui_section: EnumProperty(
        name="Seccion",
        items=UI_SECTION_ITEMS,
        default="SUMMARY",
    )

    root_name: StringProperty(name="Raiz", default="Asset")
    collection_target: EnumProperty(name="Destino", items=COLLECTION_TARGET_ITEMS, default="HIGH")
    collection_auto_detect: BoolProperty(name="Auto detectar por nombre", default=True)
    rename_affix_mode: EnumProperty(name="Modo", items=RENAME_AFFIX_MODE_ITEMS, default="PREFIX")
    rename_prefix: StringProperty(name="Prefijo", default="SM_")
    rename_base: StringProperty(name="Nombre", default="Object")
    rename_suffix: StringProperty(name="Sufijo", default="")
    mesh_name_filter: StringProperty(name="Buscar geometria", default="")
    sync_scope: EnumProperty(name="Ambito", items=SYNC_SCOPE_ITEMS, default="SELECTED")
    export_dir: StringProperty(name="Carpeta exportacion", subtype="DIR_PATH", default="")
    last_export_dir: StringProperty(name="Ultima carpeta", subtype="DIR_PATH", default="")
    export_preset: EnumProperty(name="Preset", items=EXPORT_PRESET_ITEMS, default="UNREAL")
    import_fbx_path: StringProperty(name="FBX", subtype="FILE_PATH", default="")
    import_materials_dir: StringProperty(name="Carpeta materiales", subtype="DIR_PATH", default="")
    reset_import_rotation: BoolProperty(name="Rotacion a 0", default=True)
    send_import_to_origin: BoolProperty(name="Posicion a 0,0,0", default=True)
    apply_import_scale: BoolProperty(name="Aplicar escala", default=True)


CLASSES = (
    MANWTOOL_Preferences,
    MANWTOOL_Properties,
)
