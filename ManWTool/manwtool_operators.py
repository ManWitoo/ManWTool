import os
import tempfile

import bpy

from bpy.props import BoolProperty, StringProperty
from bpy.types import Menu, Operator
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .manwtool_collections import auto_organize_objects, ensure_collection_structure, move_objects_to_target_collection
from .manwtool_core import (
    POST_INSTALL,
    TRANSFORM_WARNING_STATE,
    ensure_license_active,
    get_inverted_normals_mesh_objects,
    get_negative_scale_mesh_objects,
    run_apply_selected_transforms,
    apply_transformations_to_objects,
    apply_material_pack_to_imported_objects,
    call_in_preferences_context,
    clear_license_cache,
    clean_export_name,
    collect_export_validation,
    collection_has_child,
    current_version_str,
    download_file,
    build_rename_name,
    export_mesh_object_to_fbx,
    get_empty_objects_from_selection,
    get_addon_prefs,
    get_current_export_dir,
    get_mesh_objects_from_selection,
    get_machine_fingerprint,
    get_visible_empty_objects,
    get_visible_mesh_objects,
    load_cached_license_into_prefs,
    log_exception,
    reload_addon_timer,
    prepare_imported_objects,
    start_update_check,
    validate_license_key_format,
    validate_license_with_server,
    validate_release_zip,
    write_export_validation_report,
)
from .manwtool_export import get_export_settings_for_props, reset_export_preset_to_defaults
from .manwtool_i18n import tr


def get_import_requirements_status(props):
    fbx_path = bpy.path.abspath((props.import_fbx_path or "").strip()) if props.import_fbx_path else ""
    materials_dir = bpy.path.abspath((props.import_materials_dir or "").strip()) if props.import_materials_dir else ""
    return {
        "fbx_path": fbx_path,
        "materials_dir": materials_dir,
        "fbx_ok": bool(fbx_path and os.path.isfile(fbx_path)),
        "materials_ok": bool(materials_dir and os.path.isdir(materials_dir)),
    }


def get_export_requirements_status(context, props):
    current_dir = get_current_export_dir(props)
    active = context.active_object
    selected_meshes = get_mesh_objects_from_selection(context)
    export_settings = get_export_settings_for_props(props)
    return {
        "current_dir": current_dir,
        "has_export_dir": bool(current_dir),
        "active_mesh_ok": bool(active and active.type == "MESH"),
        "selected_meshes": selected_meshes,
        "selected_count": len(selected_meshes),
        "export_settings": export_settings,
    }


def get_collection_requirements_status(context, props):
    selected_meshes = get_mesh_objects_from_selection(context)
    return {
        "selected_meshes": selected_meshes,
        "selected_count": len(selected_meshes),
        "target": props.collection_target,
        "root_name": (props.root_name or "").strip() or "Asset",
    }


def run_export_validation_and_report(context, objects, base_dir, report_fn, export_summary=None, write_report=True):
    validation = collect_export_validation(context, objects)
    summary = validation["summary"]
    report_path = ""
    if write_report:
        report_path = write_export_validation_report(base_dir, validation, export_summary=export_summary)

    if summary["warning_count"] > 0:
        report_fn(
            {"WARNING"},
            tr(
                "report.validator.warn",
                warnings=summary["warning_count"],
                transforms=summary["transform_issues"],
                duplicates=summary["duplicate_issues"],
                collections=summary["collection_issues"],
            ),
        )
    else:
        report_fn({"INFO"}, tr("report.validator.ok"))

    if report_path:
        report_fn({"INFO"}, tr("report.report_generated", path=report_path))
    return validation, report_path


class MANWTOOL_OT_check_updates(Operator):
    bl_idname = "manwtool.check_updates"
    bl_label = "Check updates"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        start_update_check(force=True)
        self.report({"INFO"}, tr("report.checking_updates"))
        return {"FINISHED"}


class MANWTOOL_OT_open_release_page(Operator):
    bl_idname = "manwtool.open_release_page"
    bl_label = "Open release"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs and prefs.latest_release_url:
            bpy.ops.wm.url_open(url=prefs.latest_release_url)
            return {"FINISHED"}
        self.report({"ERROR"}, tr("report.no_release_url"))
        return {"CANCELLED"}


class MANWTOOL_OT_install_update(Operator):
    bl_idname = "manwtool.install_update"
    bl_label = "Update ManWTool"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if not prefs:
            self.report({"ERROR"}, tr("report.prefs_unavailable"))
            return {"CANCELLED"}

        if not getattr(prefs, "allow_in_app_update_install", False):
            self.report({"ERROR"}, tr("report.direct_install_disabled"))
            return {"CANCELLED"}

        url = (prefs.latest_download_url or "").strip()
        if not url:
            self.report({"ERROR"}, tr("report.run_check_first"))
            return {"CANCELLED"}

        tmp_dir = tempfile.mkdtemp(prefix="manwtool_update_")
        installer_path = os.path.join(tmp_dir, "manwtool_update.zip")

        try:
            download_file(url, installer_path, timeout=60)
            zip_info = validate_release_zip(installer_path, expected_version=prefs.latest_version)
            call_in_preferences_context(bpy.ops.preferences.addon_install, filepath=installer_path, overwrite=True)
            # Recarga en caliente diferida: el reload debe ocurrir FUERA de este
            # operador (cuyo propio modulo se va a reimportar). Si falla, el timer
            # marca restart_required como plan B.
            prefs.restart_required = False
            POST_INSTALL["pending"] = True
            POST_INSTALL["zip_path"] = installer_path
            POST_INSTALL["tmp_dir"] = tmp_dir
            POST_INSTALL["version"] = zip_info["version"]
            bpy.app.timers.register(reload_addon_timer, first_interval=0.3)
            self.report({"INFO"}, tr("report.update_reloaded", version=zip_info["version"]))
            return {"FINISHED"}
        except Exception as exc:
            prefs.last_update_error = str(exc)
            log_exception("Fallo la actualizacion del addon", exc)
            self.report({"ERROR"}, tr("report.update_failed", error=exc))
            return {"CANCELLED"}


class MANWTOOL_OT_update_popup(Operator):
    bl_idname = "manwtool.update_popup"
    bl_label = "Update available"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        prefs = get_addon_prefs()
        layout = self.layout
        layout.label(text=tr("report.update_popup.title"), icon="INFO")
        if prefs:
            layout.label(text=tr("report.update_popup.versions", current=current_version_str(), latest=prefs.latest_version))
        row = layout.row(align=True)
        row.operator("manwtool.install_update", text=tr("report.update_now"), icon="IMPORT")
        if prefs and prefs.latest_release_url:
            row.operator("manwtool.open_release_page", text=tr("ui.release"), icon="URL")

    def execute(self, context):
        return {"FINISHED"}


class MANWTOOL_OT_restart_required_popup(Operator):
    bl_idname = "manwtool.restart_required_popup"
    bl_label = "Restart required"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.label(text=tr("report.restart_ok"), icon="CHECKMARK")
        layout.label(text=tr("report.restart_needed"), icon="INFO")

    def execute(self, context):
        return {"FINISHED"}


class MANWTOOL_OT_clear_restart_flag(Operator):
    bl_idname = "manwtool.clear_restart_flag"
    bl_label = "Hide notice"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs:
            prefs.restart_required = False
        return {"FINISHED"}


class MANWTOOL_OT_activate_license(Operator):
    bl_idname = "manwtool.activate_license"
    bl_label = "Activate license"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if not prefs:
            self.report({"ERROR"}, tr("report.prefs_unavailable"))
            return {"CANCELLED"}

        prefs.license_hardware_id = get_machine_fingerprint()

        if not (prefs.license_server_url or "").strip():
            try:
                validate_license_key_format(prefs.license_key)
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
            prefs.license_active = False
            prefs.license_status = tr("report.license_format_ok_server_missing")
            self.report({"WARNING"}, tr("report.license_valid_but_needs_server"))
            return {"CANCELLED"}

        try:
            result = validate_license_with_server(prefs.license_email, prefs.license_key, prefs.license_server_url)
        except Exception as exc:
            log_exception("No se pudo validar la licencia", exc)
            prefs.license_active = False
            prefs.license_status = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        if result["valid"]:
            self.report({"INFO"}, tr("report.license_activated"))
            return {"FINISHED"}

        self.report({"ERROR"}, result["status"])
        return {"CANCELLED"}


class MANWTOOL_OT_clear_license_cache(Operator):
    bl_idname = "manwtool.clear_license_cache"
    bl_label = "Clear license"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        try:
            clear_license_cache()
            load_cached_license_into_prefs()
        except Exception as exc:
            log_exception("No se pudo limpiar la cache de licencia", exc)
            self.report({"ERROR"}, tr("report.clear_license_failed", error=exc))
            return {"CANCELLED"}

        if prefs:
            prefs.license_email = ""
            prefs.license_key = ""
        self.report({"INFO"}, tr("report.license_cleared"))
        return {"FINISHED"}


class MANWTOOL_OT_pick_export_dir(Operator):
    bl_idname = "manwtool.pick_export_dir"
    bl_label = "Choose folder"
    bl_options = {"REGISTER"}

    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        props = context.scene.manwtool_props
        self.directory = bpy.path.abspath(get_current_export_dir(props) or "//")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        chosen_dir = bpy.path.abspath((self.directory or "").strip())
        if not chosen_dir:
            self.report({"ERROR"}, tr("report.no_folder_selected"))
            return {"CANCELLED"}
        try:
            os.makedirs(chosen_dir, exist_ok=True)
        except Exception:
            self.report({"ERROR"}, tr("report.cannot_use_folder"))
            return {"CANCELLED"}
        props.export_dir = chosen_dir
        self.report({"INFO"}, tr("report.folder_selected", path=chosen_dir))
        return {"FINISHED"}


class MANWTOOL_OT_pick_import_fbx(Operator, ImportHelper):
    bl_idname = "manwtool.pick_import_fbx"
    bl_label = "Select FBX"
    bl_options = {"REGISTER"}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        context.scene.manwtool_props.import_fbx_path = self.filepath
        self.report({"INFO"}, tr("report.fbx_selected", name=os.path.basename(self.filepath)))
        return {"FINISHED"}


class MANWTOOL_OT_pick_materials_dir(Operator):
    bl_idname = "manwtool.pick_materials_dir"
    bl_label = "Select materials"
    bl_options = {"REGISTER"}

    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        props = context.scene.manwtool_props
        self.directory = bpy.path.abspath(props.import_materials_dir or "//")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        chosen_dir = bpy.path.abspath((self.directory or "").strip())
        context.scene.manwtool_props.import_materials_dir = chosen_dir
        self.report({"INFO"}, tr("report.materials_folder", path=chosen_dir))
        return {"FINISHED"}


class MANWTOOL_OT_save_export_presets(Operator):
    bl_idname = "manwtool.save_export_presets"
    bl_label = "Save export presets"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        try:
            bpy.ops.wm.save_userpref()
        except Exception as exc:
            self.report({"ERROR"}, tr("report.userprefs_save_failed", error=exc))
            return {"CANCELLED"}

        self.report({"INFO"}, tr("report.presets_saved"))
        return {"FINISHED"}


class MANWTOOL_OT_reset_export_preset(Operator):
    bl_idname = "manwtool.reset_export_preset"
    bl_label = "Reset export preset"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        preset = context.scene.manwtool_props.export_preset
        if not reset_export_preset_to_defaults(preset):
            self.report({"ERROR"}, tr("report.preset_reset_failed"))
            return {"CANCELLED"}

        self.report({"INFO"}, tr("report.preset_reset", preset=preset))
        return {"FINISHED"}


class MANWTOOL_OT_create_folders(Operator):
    bl_idname = "manwtool.create_folders"
    bl_label = "Create structure"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        base = (props.root_name or "").strip()
        if not base:
            self.report({"ERROR"}, tr("report.write_root_name"))
            return {"CANCELLED"}
        ensure_collection_structure(context.scene, base)
        self.report(
            {"INFO"},
            tr(
                "report.structure_created",
                root=base,
                high=f"{base}_High",
                low=f"{base}_Low",
                reference=f"{base}_Reference",
            ),
        )
        return {"FINISHED"}


class MANWTOOL_OT_move_selected_to_collection(Operator):
    bl_idname = "manwtool.move_selected_to_collection"
    bl_label = "Move selection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        selected_meshes = get_mesh_objects_from_selection(context)
        if not selected_meshes:
            self.report({"ERROR"}, tr("report.no_mesh_selected"))
            return {"CANCELLED"}

        moved = move_objects_to_target_collection(context.scene, selected_meshes, props.root_name, props.collection_target)
        self.report({"INFO"}, tr("report.objects_moved", count=moved, target=props.collection_target))
        return {"FINISHED"}


class MANWTOOL_OT_auto_organize_collections(Operator):
    bl_idname = "manwtool.auto_organize_collections"
    bl_label = "Auto organizar"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        selected_meshes = get_mesh_objects_from_selection(context)
        if not selected_meshes:
            self.report({"ERROR"}, tr("report.no_mesh_selected"))
            return {"CANCELLED"}

        if props.collection_auto_detect:
            summary = auto_organize_objects(
                context.scene,
                selected_meshes,
                props.root_name,
                default_target=props.collection_target,
            )
        else:
            moved = move_objects_to_target_collection(
                context.scene,
                selected_meshes,
                props.root_name,
                props.collection_target,
            )
            summary = {"HIGH": 0, "LOW": 0, "REFERENCE": 0, "TOTAL": moved}
            summary[props.collection_target] = moved
        self.report(
            {"INFO"},
            tr(
                "report.collections_organized",
                high=summary["HIGH"],
                low=summary["LOW"],
                reference=summary["REFERENCE"],
            ),
        )
        return {"FINISHED"}


class MANWTOOL_OT_rename_geo_data_material(Operator):
    bl_idname = "manwtool.rename_geo_data_material"
    bl_label = "Apply name"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, tr("report.need_active_mesh"))
            return {"CANCELLED"}

        props = context.scene.manwtool_props
        final_name = build_rename_name(props)
        if not final_name.strip():
            self.report({"ERROR"}, tr("report.write_name"))
            return {"CANCELLED"}

        obj.name = final_name
        if obj.data:
            obj.data.name = final_name

        material = bpy.data.materials.get(final_name)
        if material is None:
            material = bpy.data.materials.new(name=final_name)
            material.use_nodes = True

        if len(obj.data.materials) == 0:
            obj.data.materials.append(material)
        else:
            obj.data.materials[0] = material

        self.report({"INFO"}, tr("report.name_applied", name=final_name))
        return {"FINISHED"}


class MANWTOOL_OT_export_fbx(Operator, ExportHelper):
    bl_idname = "manwtool.export_fbx"
    bl_label = "Export FBX"
    bl_options = {"REGISTER"}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def invoke(self, context, event):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        obj = context.active_object
        default_name = f"{clean_export_name(obj.name)}.fbx" if obj else "Export.fbx"
        base_dir = get_current_export_dir(props)
        self.filepath = os.path.join(bpy.path.abspath(base_dir), default_name) if base_dir else default_name
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        chosen_dir = os.path.dirname(self.filepath) if self.filepath else ""
        if not chosen_dir:
            self.report({"ERROR"}, tr("report.invalid_export_path"))
            return {"CANCELLED"}

        props = context.scene.manwtool_props
        props.export_dir = chosen_dir
        props.last_export_dir = chosen_dir
        export_settings = get_export_settings_for_props(props)
        run_export_validation_and_report(context, [context.active_object], chosen_dir, self.report)
        ok = export_mesh_object_to_fbx(context, context.active_object, chosen_dir, self.report, export_settings=export_settings)
        return {"FINISHED"} if ok else {"CANCELLED"}


class MANWTOOL_OT_reexport_fbx(Operator):
    bl_idname = "manwtool.reexport_fbx"
    bl_label = "Re-export"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        base_dir = get_current_export_dir(props)
        if not base_dir:
            self.report({"ERROR"}, tr("report.select_export_folder_first"))
            return {"CANCELLED"}
        props.last_export_dir = base_dir
        export_settings = get_export_settings_for_props(props)
        run_export_validation_and_report(context, [context.active_object], base_dir, self.report)
        ok = export_mesh_object_to_fbx(context, context.active_object, base_dir, self.report, export_settings=export_settings)
        return {"FINISHED"} if ok else {"CANCELLED"}


class MANWTOOL_OT_select_all_meshes(Operator):
    bl_idname = "manwtool.select_all_meshes"
    bl_label = "Select all geometry"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        bpy.ops.object.select_all(action="DESELECT")
        meshes = get_visible_mesh_objects(context)
        for obj in meshes:
            obj.select_set(True)
        if meshes:
            context.view_layer.objects.active = meshes[0]
        self.report({"INFO"}, tr("report.geometry_selected", count=len(meshes)))
        return {"FINISHED"}


class MANWTOOL_OT_select_meshes_by_name(Operator):
    bl_idname = "manwtool.select_meshes_by_name"
    bl_label = "Select geometry by name"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        search = (props.mesh_name_filter or "").strip().lower()
        if not search:
            self.report({"ERROR"}, tr("report.write_search_text"))
            return {"CANCELLED"}

        bpy.ops.object.select_all(action="DESELECT")
        meshes = [obj for obj in get_visible_mesh_objects(context) if search in obj.name.lower()]
        for obj in meshes:
            obj.select_set(True)
        if meshes:
            context.view_layer.objects.active = meshes[0]
            self.report({"INFO"}, tr("report.geometry_selected_with", count=len(meshes), text=props.mesh_name_filter))
            return {"FINISHED"}

        self.report({"WARNING"}, tr("report.geometry_not_found_with", text=props.mesh_name_filter))
        return {"CANCELLED"}


class MANWTOOL_OT_select_all_empties(Operator):
    bl_idname = "manwtool.select_all_empties"
    bl_label = "Select all empties"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        bpy.ops.object.select_all(action="DESELECT")
        empties = get_visible_empty_objects(context)
        for obj in empties:
            obj.select_set(True)
        if empties:
            context.view_layer.objects.active = empties[0]
        self.report({"INFO"}, tr("report.empty_selected", count=len(empties)))
        return {"FINISHED"}


class MANWTOOL_MT_transform_warning_menu(Menu):
    bl_idname = "MANWTOOL_MT_transform_warning_menu"
    bl_label = "Normales sospechosas detectadas"

    def draw(self, context):
        layout = self.layout
        negative_scale_count = int(TRANSFORM_WARNING_STATE.get("negative_scale_count", 0))
        inverted_normals_count = int(TRANSFORM_WARNING_STATE.get("inverted_normals_count", 0))
        affected_count = int(TRANSFORM_WARNING_STATE.get("affected_count", 0))
        affected_names = TRANSFORM_WARNING_STATE.get("affected_names", [])

        if negative_scale_count:
            layout.label(text=tr("ui.warning.negative_scale"), icon="ERROR")
        if inverted_normals_count:
            layout.label(text=tr("ui.warning.inverted_normals"), icon="ERROR")
        layout.label(text=tr("ui.warning.recalc_hint"), icon="INFO")
        layout.label(text=tr("ui.warning.detected_objects", count=affected_count))
        if affected_names:
            names_box = layout.box()
            names_box.enabled = False
            for name in affected_names:
                if name:
                    names_box.label(text=name)

        layout.separator()

        first = layout.operator(
            "manwtool.apply_selected_transforms_confirm",
            text=tr("ui.warning.apply_and_recalc"),
            icon="CHECKMARK",
        )
        first.recalc_suspect_normals = True

        second = layout.operator(
            "manwtool.apply_selected_transforms_confirm",
            text=tr("ui.warning.continue_without"),
            icon="TRIA_RIGHT",
        )
        second.recalc_suspect_normals = False


class MANWTOOL_OT_apply_selected_transforms_confirm(Operator):
    bl_idname = "manwtool.apply_selected_transforms_confirm"
    bl_label = "Confirmar transformaciones"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    recalc_suspect_normals: BoolProperty(default=False)

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        return run_apply_selected_transforms(
            context,
            self.report,
            recalc_suspect_normals=bool(self.recalc_suspect_normals),
        )


class MANWTOOL_OT_apply_selected_transforms(Operator):
    bl_idname = "manwtool.apply_selected_transforms"
    bl_label = "Apply transforms"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        selected_meshes = get_mesh_objects_from_selection(context)
        selected_empties = get_empty_objects_from_selection(context)
        selected_objects = selected_meshes + selected_empties
        if not selected_objects:
            self.report({"ERROR"}, tr("report.no_mesh_or_empty_selected"))
            return {"CANCELLED"}

        negative_scale_meshes = get_negative_scale_mesh_objects(selected_meshes)
        inverted_normals_meshes = get_inverted_normals_mesh_objects(selected_meshes)
        suspect_meshes = []
        for obj in negative_scale_meshes + inverted_normals_meshes:
            if obj not in suspect_meshes:
                suspect_meshes.append(obj)
        if suspect_meshes:
            TRANSFORM_WARNING_STATE["affected_count"] = len(suspect_meshes)
            TRANSFORM_WARNING_STATE["affected_names"] = [obj.name for obj in suspect_meshes[:8]]
            TRANSFORM_WARNING_STATE["negative_scale_count"] = len(negative_scale_meshes)
            TRANSFORM_WARNING_STATE["inverted_normals_count"] = len(inverted_normals_meshes)
            bpy.ops.wm.call_menu(name="MANWTOOL_MT_transform_warning_menu")
            return {"FINISHED"}

        return self.execute(context)

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        return run_apply_selected_transforms(
            context,
            self.report,
            recalc_suspect_normals=False,
        )


class MANWTOOL_OT_export_multiple_fbx(Operator):
    bl_idname = "manwtool.export_multiple_fbx"
    bl_label = "Batch export"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        base_dir = get_current_export_dir(props)
        if not base_dir:
            self.report({"ERROR"}, tr("report.select_export_folder_first"))
            return {"CANCELLED"}

        selected_meshes = get_mesh_objects_from_selection(context)
        if not selected_meshes:
            self.report({"ERROR"}, tr("report.no_mesh_selected"))
            return {"CANCELLED"}

        props.last_export_dir = base_dir
        export_settings = get_export_settings_for_props(props)
        validation, _ = run_export_validation_and_report(context, selected_meshes, base_dir, self.report, write_report=False)
        exported = 0
        skipped_duplicates = 0
        failed = 0
        processed_names = set()

        for obj in selected_meshes:
            export_name = clean_export_name(obj.name)
            if export_name in processed_names:
                skipped_duplicates += 1
                continue
            processed_names.add(export_name)
            if export_mesh_object_to_fbx(context, obj, base_dir, self.report, export_settings=export_settings):
                exported += 1
            else:
                failed += 1

        self.report(
            {"INFO"},
            tr("report.export_multiple_done", exported=exported, skipped=skipped_duplicates, failed=failed),
        )
        report_path = write_export_validation_report(
            base_dir,
            validation,
            export_summary={
                "exported": exported,
                "failed": failed,
                "skipped_duplicates": skipped_duplicates,
            },
        )
        self.report({"INFO"}, tr("report.report_generated", path=report_path))
        return {"FINISHED"}


class MANWTOOL_OT_import_fbx_pack(Operator):
    bl_idname = "manwtool.import_fbx_pack"
    bl_label = "Import FBX + materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if not ensure_license_active(self.report):
            return {"CANCELLED"}
        props = context.scene.manwtool_props
        status = get_import_requirements_status(props)

        if not status["fbx_ok"]:
            self.report({"ERROR"}, tr("report.invalid_fbx"))
            return {"CANCELLED"}
        if not status["materials_ok"]:
            self.report({"ERROR"}, tr("report.invalid_materials_dir"))
            return {"CANCELLED"}

        before_ids = {obj.as_pointer() for obj in bpy.data.objects}
        try:
            bpy.ops.import_scene.fbx(filepath=status["fbx_path"], automatic_bone_orientation=True)
        except Exception as exc:
            log_exception(f"No se pudo importar el FBX {status['fbx_path']}", exc)
            self.report({"ERROR"}, tr("report.fbx_import_failed", error=exc))
            return {"CANCELLED"}

        imported_objects = [obj for obj in bpy.data.objects if obj.as_pointer() not in before_ids]
        if not imported_objects:
            imported_objects = list(context.selected_objects)
        if not imported_objects:
            self.report({"ERROR"}, tr("report.import_no_objects"))
            return {"CANCELLED"}

        prepared = prepare_imported_objects(
            context,
            imported_objects,
            apply_scale=props.apply_import_scale,
            reset_rotation=props.reset_import_rotation,
            move_to_origin=props.send_import_to_origin,
        )
        material_summary = apply_material_pack_to_imported_objects(imported_objects, status["materials_dir"])
        imported_meshes = len([obj for obj in imported_objects if obj.type == "MESH"])
        self.report(
            {"INFO"},
            tr(
                "report.import_done",
                objects=len(imported_objects),
                meshes=imported_meshes,
                prepared=prepared,
                materials=material_summary["materials_updated"],
                textured=material_summary["objects_with_matches"],
            ),
        )
        return {"FINISHED"}


CLASSES = (
    MANWTOOL_OT_check_updates,
    MANWTOOL_OT_open_release_page,
    MANWTOOL_OT_install_update,
    MANWTOOL_OT_update_popup,
    MANWTOOL_OT_restart_required_popup,
    MANWTOOL_OT_clear_restart_flag,
    MANWTOOL_OT_activate_license,
    MANWTOOL_OT_clear_license_cache,
    MANWTOOL_OT_pick_export_dir,
    MANWTOOL_OT_pick_import_fbx,
    MANWTOOL_OT_pick_materials_dir,
    MANWTOOL_OT_save_export_presets,
    MANWTOOL_OT_reset_export_preset,
    MANWTOOL_OT_create_folders,
    MANWTOOL_OT_move_selected_to_collection,
    MANWTOOL_OT_auto_organize_collections,
    MANWTOOL_OT_rename_geo_data_material,
    MANWTOOL_OT_export_fbx,
    MANWTOOL_OT_reexport_fbx,
    MANWTOOL_OT_select_all_meshes,
    MANWTOOL_OT_select_meshes_by_name,
    MANWTOOL_OT_select_all_empties,
    MANWTOOL_MT_transform_warning_menu,
    MANWTOOL_OT_apply_selected_transforms_confirm,
    MANWTOOL_OT_apply_selected_transforms,
    MANWTOOL_OT_export_multiple_fbx,
    MANWTOOL_OT_import_fbx_pack,
)
