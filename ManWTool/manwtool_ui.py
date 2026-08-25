import bpy

from bpy.types import Panel

from .manwtool_collections import get_collection_target_label
from .manwtool_core import (
    active_obj_status,
    build_rename_name,
    collect_export_validation,
    count_multi_user_meshes,
    current_version_str,
    get_addon_prefs,
    get_current_export_dir,
    get_logo_icon_value,
    is_license_active,
)
from .manwtool_export import format_export_settings_lines, get_addon_preferences, get_preset_pref_fields
from .manwtool_i18n import tr, yes_no
from .manwtool_operators import get_collection_requirements_status, get_export_requirements_status, get_import_requirements_status


def big_button(layout):
    row = layout.row()
    row.scale_y = 1.35
    return row


def draw_update_box_if_needed(layout):
    prefs = get_addon_prefs()
    if not prefs:
        return

    if not (prefs.update_available or prefs.last_update_error or prefs.restart_required):
        return

    box = layout.box()
    box.label(text=tr("ui.update_section"), icon="FILE_REFRESH")

    if prefs.last_update_error:
        err = box.box()
        err.alert = True
        err.label(text=prefs.last_update_error, icon="ERROR")

    if prefs.update_available:
        box.label(text=tr("ui.new_version", latest=prefs.latest_version, current=current_version_str()), icon="INFO")
        row = box.row(align=True)
        row.scale_y = 1.2
        row.enabled = getattr(prefs, "allow_in_app_update_install", False)
        row.operator("manwtool.install_update", text=tr("ui.update"), icon="IMPORT")
        action_row = box.row(align=True)
        action_row.scale_y = 1.1
        action_row.operator("manwtool.check_updates", text=tr("ui.review"), icon="VIEWZOOM")
        if prefs.latest_release_url:
            action_row.operator("manwtool.open_release_page", text=tr("ui.release"), icon="URL")
        if not getattr(prefs, "allow_in_app_update_install", False):
            hint = box.box()
            hint.enabled = False
            hint.label(text=tr("ui.update_disabled_hint"))
    else:
        box.operator("manwtool.check_updates", text=tr("ui.check_updates"), icon="VIEWZOOM")

    if prefs.restart_required:
        warn = box.box()
        warn.alert = True
        warn.label(text=tr("ui.update_installed_restart"), icon="ERROR")
        warn.operator("manwtool.clear_restart_flag", text=tr("prefs.hide_notice"), icon="CHECKMARK")


def draw_header(panel, context, show_status=True):
    layout = panel.layout
    row = layout.row(align=True)
    icon_value = get_logo_icon_value()
    title = f"ManWTool  v{current_version_str()}"

    if icon_value:
        row.label(text=title, icon_value=icon_value)
    else:
        row.label(text=title, icon="TOOL_SETTINGS")

    prefs = get_addon_prefs()
    if prefs and prefs.update_available:
        row.alert = True
        row.label(text=tr("ui.title_update", version=prefs.latest_version), icon="FILE_REFRESH")

    if not show_status:
        return

    status, level, icon = active_obj_status(context)
    row2 = layout.row()
    if level in {"ERROR", "WARNING"}:
        row2.alert = True
    row2.label(text=status, icon=icon)


def draw_path_picker(layout, title: str, button_text: str, current_value: str, operator_id: str, icon="FILE_FOLDER"):
    box = layout.box()
    box.label(text=title, icon=icon)
    big_button(box).operator(operator_id, text=button_text, icon=icon)

    shown_value = bpy.path.abspath(current_value) if current_value else tr("ui.path.none")
    info = box.box()
    info.enabled = False
    info.label(text=shown_value)
    return box


def draw_status_lines(layout, lines):
    info = layout.box()
    info.enabled = False
    for line in lines:
        info.label(text=line)


def draw_rename_fields(layout, props):
    layout.prop(props, "rename_affix_mode", text=tr("ui.naming.affix_mode"))
    mode = (props.rename_affix_mode or "PREFIX").upper()
    if mode in {"PREFIX", "BOTH"}:
        layout.prop(props, "rename_prefix", text=tr("ui.naming.prefix"))
    if mode in {"SUFFIX", "BOTH"}:
        layout.prop(props, "rename_suffix", text=tr("ui.naming.suffix"))
    layout.prop(props, "rename_base", text=tr("ui.naming.name"))


def draw_export_preset_editor(layout, props):
    prefs = get_addon_preferences()
    preset = props.export_preset
    layout.prop(props, "export_preset", text=tr("ui.export.preset"))

    if not prefs:
        warn = layout.box()
        warn.alert = True
        warn.label(text=tr("ui.error.prefs_unavailable"), icon="ERROR")
        return

    fields = get_preset_pref_fields(preset)
    col = layout.column(align=True)
    col.prop(prefs, fields["axis_forward"])
    col.prop(prefs, fields["axis_up"])
    col.prop(prefs, fields["apply_unit_scale"])
    col.prop(prefs, fields["use_mesh_modifiers"])

    actions = layout.row(align=True)
    actions.operator("manwtool.save_export_presets", text=tr("ui.preset.save"), icon="FILE_TICK")
    actions.operator("manwtool.reset_export_preset", text=tr("ui.preset.reset"), icon="LOOP_BACK")


def draw_license_required_notice(layout):
    box = layout.box()
    box.alert = True
    box.label(text=tr("ui.license.required_title"), icon="LOCKED")
    box.label(text=tr("ui.license.required_line1"))
    box.label(text=tr("ui.license.required_line2"))


def draw_section_tabs(layout, props):
    split = layout.split(factor=0.16, align=True)
    nav = split.column(align=True)
    nav.scale_y = 1.3
    nav.prop_enum(props, "ui_section", "SUMMARY", text="", icon="HOME")
    locked_nav = nav.column(align=True)
    locked_nav.enabled = is_license_active()
    locked_nav.prop_enum(props, "ui_section", "FOLDERS", text="", icon="FILE_FOLDER")
    locked_nav.prop_enum(props, "ui_section", "RENAME", text="", icon="FILE_TEXT")
    locked_nav.prop_enum(props, "ui_section", "TRANSFORM", text="", icon="OBJECT_ORIGIN")
    locked_nav.prop_enum(props, "ui_section", "EXPORT", text="", icon="EXPORT")
    locked_nav.prop_enum(props, "ui_section", "IMPORT", text="", icon="IMPORT")
    return split.column(align=True)


def draw_summary_metrics(layout, context, props):
    selected_objects = list(context.selected_objects)
    selected_meshes = [obj for obj in selected_objects if obj.type == "MESH"]
    selected_empties = [obj for obj in selected_objects if obj.type == "EMPTY"]
    active = context.active_object
    export_dir = get_current_export_dir(props) or "-"

    box = layout.box()
    box.label(text=tr("ui.summary.asset"), icon="INFO")

    col = box.column(align=True)
    col.enabled = False
    active_name = active.name if active else tr("ui.path.none")
    export_path = bpy.path.abspath(export_dir) if export_dir != "-" else tr("ui.path.none")
    col.label(text=tr("ui.summary.active", name=active_name))
    col.label(text=tr("ui.summary.selected_meshes", count=len(selected_meshes)))
    col.label(text=tr("ui.summary.selected_empties", count=len(selected_empties)))
    col.label(text=tr("ui.summary.shared_data", count=count_multi_user_meshes(selected_meshes)))
    col.label(text=tr("ui.summary.export_dir", path=export_path))


def draw_summary_validator(layout, context):
    selected_meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
    box = layout.box()
    box.label(text=tr("ui.validator"), icon="CHECKMARK")

    if not selected_meshes:
        info = box.column(align=True)
        info.enabled = False
        info.label(text=tr("ui.validator.select_mesh"))
        return

    validation = collect_export_validation(context, selected_meshes)
    summary = validation["summary"]
    level = "OK"
    icon = "CHECKMARK"
    if summary["warning_count"] > 0:
        level = "WARN"
        icon = "ERROR"
        box.alert = True

    header = box.row(align=True)
    header.label(text=tr("ui.validator.state", level=level), icon=icon)
    header.label(text=tr("ui.validator.reviewed", count=summary["objects_checked"]))

    col = box.column(align=True)
    col.enabled = False
    col.label(text=tr("ui.validator.transforms", count=summary["transform_issues"]))
    col.label(text=tr("ui.validator.duplicates", count=summary["duplicate_issues"]))
    col.label(text=tr("ui.validator.collections", count=summary["collection_issues"]))


def draw_summary_actions(layout, context, props):
    selected_meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
    selected_empties = [obj for obj in context.selected_objects if obj.type == "EMPTY"]
    active = context.active_object
    export_status = get_export_requirements_status(context, props)
    collection_status = get_collection_requirements_status(context, props)

    box = layout.box()
    box.label(text=tr("ui.quick_actions"), icon="TOOL_SETTINGS")
    if not is_license_active():
        box.enabled = False

    rename = box.box()
    rename.label(text=tr("ui.naming"), icon="FILE_TEXT")
    draw_rename_fields(rename, props)
    btn = big_button(rename)
    btn.enabled = bool(active and active.type == "MESH")
    btn.operator("manwtool.rename_geo_data_material", text=tr("ui.apply_name"), icon="FILE_TICK")

    collections = box.box()
    collections.label(text=tr("ui.collections"), icon="OUTLINER_COLLECTION")
    collections.prop(props, "root_name", text=tr("ui.root"))
    collections.prop(props, "collection_target", text=tr("ui.target"))
    collections.prop(props, "collection_auto_detect", text=tr("ui.auto_detect_name"))
    row = collections.row(align=True)
    row.scale_y = 1.15
    row.operator("manwtool.create_folders", text=tr("ui.create_structure"), icon="PLUS")
    move_row = collections.row(align=True)
    move_row.scale_y = 1.15
    move_row.enabled = collection_status["selected_count"] > 0
    move_row.operator("manwtool.move_selected_to_collection", text=tr("ui.move"), icon="TRIA_RIGHT")
    move_row.operator("manwtool.auto_organize_collections", text=tr("ui.auto_organize"), icon="FILE_REFRESH")

    transforms = box.box()
    transforms.label(text=tr("ui.transform"), icon="OBJECT_ORIGIN")
    find = transforms.row(align=True)
    find.prop(props, "mesh_name_filter", text="", icon="VIEWZOOM")
    find.operator("manwtool.select_meshes_by_name", text="", icon="RESTRICT_SELECT_OFF")
    row = transforms.row(align=True)
    row.scale_y = 1.1
    row.operator("manwtool.select_all_meshes", text=tr("ui.select_mesh"), icon="MESH_CUBE")
    row.operator("manwtool.select_all_empties", text=tr("ui.select_empty"), icon="EMPTY_AXIS")
    btn = big_button(transforms)
    btn.enabled = len(selected_meshes) > 0 or len(selected_empties) > 0
    btn.operator("manwtool.apply_selected_transforms", text=tr("ui.apply_transforms"), icon="CHECKMARK")

    export_box = box.box()
    export_box.label(text=tr("ui.export_box"), icon="EXPORT")
    draw_export_preset_editor(export_box, props)
    export_box.operator("manwtool.pick_export_dir", text=tr("ui.select_folder"), icon="FILE_FOLDER")
    row = export_box.row(align=True)
    row.scale_y = 1.2
    row.enabled = export_status["active_mesh_ok"]
    row.operator("manwtool.export_fbx", text=tr("ui.export_active"), icon="EXPORT")
    row2 = export_box.row(align=True)
    row2.scale_y = 1.2
    row2.enabled = export_status["active_mesh_ok"] and export_status["has_export_dir"]
    row2.operator("manwtool.reexport_fbx", text=tr("ui.reexport"), icon="FILE_REFRESH")
    row3 = export_box.row(align=True)
    row3.scale_y = 1.2
    row3.enabled = export_status["has_export_dir"] and export_status["selected_count"] > 0
    row3.operator("manwtool.export_multiple_fbx", text=tr("ui.export_multiple"), icon="COPYDOWN")


def draw_section_summary(layout, context, props):
    draw_summary_metrics(layout, context, props)
    draw_summary_validator(layout, context)

    active = context.active_object
    if active and active.type in {"MESH", "EMPTY"} and len(context.selected_objects) == 1:
        draw_single_object_transform(layout, active)

    draw_summary_actions(layout, context, props)


def draw_single_object_transform(layout, obj):
    box = layout.box()
    box.label(text=tr("ui.transform"), icon="ORIENTATION_GLOBAL")

    col = box.column(align=True)
    col.use_property_split = False
    col.use_property_decorate = False

    col.prop(obj, "location", text=tr("ui.location"))

    if obj.rotation_mode == "QUATERNION":
        col.prop(obj, "rotation_quaternion", text=tr("ui.rotation"))
    elif obj.rotation_mode == "AXIS_ANGLE":
        col.prop(obj, "rotation_axis_angle", text=tr("ui.rotation"))
    else:
        col.prop(obj, "rotation_euler", text=tr("ui.rotation"))

    col.prop(obj, "scale", text=tr("ui.scale"))


def draw_section_folders(layout, context, props):
    if not is_license_active():
        draw_license_required_notice(layout)
        return
    status = get_collection_requirements_status(context, props)
    box = layout.box()
    box.label(text=tr("ui.collection_structure"), icon="OUTLINER_COLLECTION")
    box.prop(props, "root_name", text=tr("ui.root"))

    preview = box.box()
    preview.enabled = False
    base = (props.root_name or "").strip() or "Asset"
    preview.label(text=tr("ui.collections.preview", root=base, high=f"{base}_High", low=f"{base}_Low", reference=f"{base}_Reference"))

    big_button(box).operator("manwtool.create_folders", text=tr("ui.create_structure"), icon="PLUS")

    manage = layout.box()
    manage.label(text=tr("ui.collections.management"), icon="SORTALPHA")
    manage.prop(props, "collection_target", text=tr("ui.target"))
    manage.prop(props, "collection_auto_detect", text=tr("ui.auto_detect_name"))
    draw_status_lines(
        manage,
        [
            tr("ui.summary.selected_meshes", count=status["selected_count"]),
            tr("ui.collections.current_target", target=get_collection_target_label(status["target"])),
        ],
    )

    row = manage.row(align=True)
    row.scale_y = 1.2
    row.enabled = status["selected_count"] > 0
    row.operator("manwtool.move_selected_to_collection", text=tr("ui.move"), icon="TRIA_RIGHT")
    auto_row = manage.row(align=True)
    auto_row.scale_y = 1.2
    auto_row.enabled = status["selected_count"] > 0
    auto_row.operator("manwtool.auto_organize_collections", text=tr("ui.auto_organize"), icon="FILE_REFRESH")


def draw_section_rename(layout, context, props):
    if not is_license_active():
        draw_license_required_notice(layout)
        return
    box = layout.box()
    box.label(text=tr("ui.naming.consistent"), icon="FILE_TEXT")
    col = box.column(align=True)
    draw_rename_fields(col, props)

    final_name = build_rename_name(props)
    preview = box.box()
    preview.enabled = False
    preview.label(text=tr("ui.naming.result", name=final_name), icon="CHECKMARK")

    obj = context.active_object
    hint = box.box()
    hint.enabled = False
    if obj and obj.type == "MESH":
        hint.label(text=tr("ui.naming.apply_to", name=obj.name))
    else:
        hint.label(text=tr("ui.naming.need_active_mesh"))

    btn = big_button(box)
    btn.enabled = bool(obj and obj.type == "MESH")
    btn.operator("manwtool.rename_geo_data_material", text=tr("ui.apply_name"), icon="FILE_TICK")

    draw_data_name_sync(layout, props)


def draw_data_name_sync(layout, props):
    prefs = get_addon_preferences()

    box = layout.box()
    box.label(text=tr("ui.sync.title"), icon="OUTLINER_OB_MESH")

    if not prefs:
        warn = box.box()
        warn.alert = True
        warn.label(text=tr("ui.error.prefs_unavailable"), icon="ERROR")
        return

    box.prop(prefs, "sync_data_names", text=tr("ui.sync.toggle"))

    hint = box.box()
    hint.enabled = False
    hint.label(text=tr("ui.sync.toggle_hint"))

    row = box.row(align=True)
    row.prop(props, "sync_scope", text="")
    op = row.operator("manwtool.sync_all_data_names", text=tr("ui.sync.run"), icon="FILE_REFRESH")
    op.scope = props.sync_scope


def draw_section_export(layout, context, props):
    if not is_license_active():
        draw_license_required_notice(layout)
        return
    status = get_export_requirements_status(context, props)
    active_name = context.active_object.name if context.active_object else tr("ui.path.none")

    preset_box = layout.box()
    preset_box.label(text=tr("ui.export.preset"), icon="PRESET")
    draw_export_preset_editor(preset_box, props)
    draw_status_lines(preset_box, format_export_settings_lines(status["export_settings"]))

    draw_path_picker(
        layout,
        title=tr("ui.export.folder_title"),
        button_text=tr("ui.export.folder_button"),
        current_value=status["current_dir"],
        operator_id="manwtool.pick_export_dir",
        icon="FILE_FOLDER",
    )

    draw_status_lines(
        layout,
        [
            tr("ui.summary.active", name=active_name),
            tr("ui.summary.selected_meshes", count=status["selected_count"]),
            tr("ui.export.creates_folder"),
        ],
    )

    box_single = layout.box()
    box_single.label(text=tr("ui.export.single"), icon="EXPORT")
    info = box_single.column(align=True)
    info.enabled = False
    info.label(text=tr("ui.export.copy_hint_1"))
    info.label(text=tr("ui.export.copy_hint_2"))

    row = box_single.row(align=True)
    row.scale_y = 1.35
    row.enabled = status["active_mesh_ok"]
    row.operator("manwtool.export_fbx", text=tr("ui.export.action"), icon="EXPORT")

    row2 = box_single.row(align=True)
    row2.scale_y = 1.35
    row2.enabled = status["active_mesh_ok"] and status["has_export_dir"]
    row2.operator("manwtool.reexport_fbx", text=tr("ui.reexport"), icon="FILE_REFRESH")

    box_multi = layout.box()
    box_multi.label(text=tr("ui.export.batch"), icon="COPYDOWN")
    draw_status_lines(
        box_multi,
        [
            tr("ui.export.batch_hint_1"),
            tr("ui.export.batch_hint_2"),
        ],
    )
    big_button(box_multi).operator("manwtool.select_all_meshes", text=tr("ui.select_mesh"), icon="RESTRICT_SELECT_OFF")
    btn = big_button(box_multi)
    btn.enabled = status["has_export_dir"] and status["selected_count"] > 0
    btn.operator("manwtool.export_multiple_fbx", text=tr("ui.export_multiple"), icon="EXPORT")


def draw_section_transform(layout, context, props):
    if not is_license_active():
        draw_license_required_notice(layout)
        return
    selected_objects = context.selected_objects
    selected_meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
    selected_empties = [obj for obj in context.selected_objects if obj.type == "EMPTY"]
    multi_user_count = count_multi_user_meshes(selected_meshes)

    box = layout.box()
    box.label(text=tr("ui.transform.batch"), icon="OBJECT_ORIGIN")

    draw_status_lines(
        box,
        [
            tr("ui.summary.selected_meshes", count=len(selected_meshes)),
            tr("ui.summary.selected_empties", count=len(selected_empties)),
            tr("ui.transform.shared_data", count=multi_user_count),
        ],
    )

    if len(selected_objects) == 1 and selected_objects[0].type in {"MESH", "EMPTY"}:
        draw_single_object_transform(box, selected_objects[0])

    find = box.row(align=True)
    find.prop(props, "mesh_name_filter", text="", icon="VIEWZOOM")
    find.operator("manwtool.select_meshes_by_name", text="", icon="RESTRICT_SELECT_OFF")

    row = box.row(align=True)
    row.scale_y = 1.2
    row.operator("manwtool.select_all_meshes", text=tr("ui.select_mesh"), icon="MESH_CUBE")
    row.operator("manwtool.select_all_empties", text=tr("ui.select_empty"), icon="EMPTY_AXIS")

    btn = big_button(box)
    btn.enabled = len(selected_meshes) > 0 or len(selected_empties) > 0
    btn.operator("manwtool.apply_selected_transforms", text=tr("ui.apply_transforms"), icon="CHECKMARK")


def draw_section_import(layout, context, props):
    if not is_license_active():
        draw_license_required_notice(layout)
        return
    status = get_import_requirements_status(props)
    box = layout.box()
    box.label(text=tr("ui.import.auto"), icon="IMPORT")

    draw_path_picker(
        box,
        title=tr("ui.import.step1"),
        button_text=tr("ui.import.select_fbx"),
        current_value=props.import_fbx_path,
        operator_id="manwtool.pick_import_fbx",
        icon="FILE",
    )

    draw_path_picker(
        box,
        title=tr("ui.import.step2"),
        button_text=tr("ui.import.select_materials"),
        current_value=props.import_materials_dir,
        operator_id="manwtool.pick_materials_dir",
        icon="FILE_FOLDER",
    )

    opts = box.box()
    opts.label(text=tr("ui.import.step3"), icon="SETTINGS")
    col = opts.column(align=True)
    col.prop(props, "apply_import_scale", text=tr("ui.import.apply_scale"))
    col.prop(props, "reset_import_rotation", text=tr("ui.import.reset_rotation"))
    col.prop(props, "send_import_to_origin", text=tr("ui.import.move_origin"))

    readiness = box.box()
    readiness.alert = not (status["fbx_ok"] and status["materials_ok"])
    readiness.label(text=tr("ui.import.flow"), icon="INFO")
    readiness.label(text=tr("ui.import.fbx_ready", value=yes_no(status["fbx_ok"])))
    readiness.label(text=tr("ui.import.materials_ready", value=yes_no(status["materials_ok"])))

    info = box.box()
    info.enabled = False
    info.label(text=tr("ui.import.info1"))
    info.label(text=tr("ui.import.info2"))

    btn = big_button(box)
    btn.enabled = status["fbx_ok"] and status["materials_ok"]
    btn.operator("manwtool.import_fbx_pack", text=tr("ui.import.run"), icon="IMPORT")


class MANWTOOL_PT_main(Panel):
    bl_label = "ManWTool"
    bl_idname = "MANWTOOL_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ManWTool"

    def draw(self, context):
        layout = self.layout
        props = context.scene.manwtool_props
        if not is_license_active() and props.ui_section != "SUMMARY":
            props.ui_section = "SUMMARY"

        draw_header(self, context, show_status=True)
        draw_update_box_if_needed(layout)
        layout.separator()
        content = draw_section_tabs(layout, props)
        if props.ui_section == "SUMMARY":
            if not is_license_active():
                draw_license_required_notice(content)
            draw_section_summary(content, context, props)
        elif props.ui_section == "FOLDERS":
            draw_section_folders(content, context, props)
        elif props.ui_section == "RENAME":
            draw_section_rename(content, context, props)
        elif props.ui_section == "TRANSFORM":
            draw_section_transform(content, context, props)
        elif props.ui_section == "EXPORT":
            draw_section_export(content, context, props)
        else:
            draw_section_import(content, context, props)


CLASSES = (
    MANWTOOL_PT_main,
)
