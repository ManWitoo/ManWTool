import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request

import bpy
import bpy.utils.previews

from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ExportHelper, ImportHelper

bl_info = {
    "name": "ManWTool",
    "author": "Jairo (ManW)",
    "version": (0, 2, 1),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > ManWTool",
    "description": "Colecciones, renombrado, export FBX, import FBX automatico y updater por GitHub.",
    "category": "3D View",
}


ADDON_ID = "ManWTool"
DEFAULT_REPO_OWNER = "ManWitoo"
DEFAULT_REPO_NAME = "ManWTool"
DEFAULT_ADDON_FILE = "ManWTool.py"

_preview_col = None

UPDATER_STATE = {
    "thread": None,
    "checking": False,
    "done": False,
    "ok": False,
    "latest_version": "",
    "download_url": "",
    "download_kind": "ZIP",
    "release_html_url": "",
    "error": "",
}

POST_INSTALL = {
    "pending": False,
    "zip_path": "",
}

TEXTURE_RULES = {
    "BASE_COLOR": ("basecolor", "base_color", "albedo", "diffuse", "color", "col"),
    "NORMAL": ("normal", "nor", "nrm"),
    "ROUGHNESS": ("roughness", "rough"),
    "METALLIC": ("metallic", "metalness", "metal"),
    "AO": ("ao", "ambientocclusion", "occlusion"),
    "EMISSION": ("emission", "emissive"),
    "OPACITY": ("opacity", "alpha", "transparency"),
}

VALID_COLLECTION_SUFFIXES = ("_High", "_Low", "_Reference")


def current_version_str():
    return ".".join(map(str, bl_info.get("version", (0, 0, 0))))


def version_tuple_from_any(text: str):
    nums = re.findall(r"\d+", text or "")
    values = [int(n) for n in nums[:3]]
    while len(values) < 3:
        values.append(0)
    return tuple(values)


def normalize_name(text: str):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def clean_export_name(name: str):
    return re.sub(r"\.\d{3}$", "", name or "")


def get_addon_prefs():
    try:
        addon = bpy.context.preferences.addons.get(ADDON_ID)
        return addon.preferences if addon else None
    except Exception:
        return None


def github_latest_release_url(owner: str, repo: str):
    return f"https://api.github.com/repos/{owner}/{repo}/releases/latest"


def github_repo_api_url(owner: str, repo: str):
    return f"https://api.github.com/repos/{owner}/{repo}"


def github_raw_file_url(owner: str, repo: str, branch: str, file_path: str):
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"


def github_repo_html_url(owner: str, repo: str):
    return f"https://github.com/{owner}/{repo}"


def http_get_json(url: str, timeout=10):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"{ADDON_ID}/{current_version_str()} (Blender Add-on)",
            "Accept": "application/vnd.github+json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def http_get_text(url: str, timeout=10):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"{ADDON_ID}/{current_version_str()} (Blender Add-on)"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def download_file(url: str, dst_path: str, timeout=30):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"{ADDON_ID}/{current_version_str()}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(dst_path, "wb") as fh:
            shutil.copyfileobj(resp, fh)


def call_in_preferences_context(op_func, **kwargs):
    wm = bpy.context.window_manager
    for win in wm.windows:
        screen = win.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "PREFERENCES":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region:
                with bpy.context.temp_override(window=win, area=area, region=region):
                    return op_func(**kwargs)
            with bpy.context.temp_override(window=win, area=area):
                return op_func(**kwargs)
    return op_func(**kwargs)


def select_best_zip_asset(release_json, asset_name_contains: str):
    asset_filter = (asset_name_contains or "").strip().lower()
    for asset in release_json.get("assets") or []:
        name = (asset.get("name") or "").strip().lower()
        url = (asset.get("browser_download_url") or "").strip()
        if not name.endswith(".zip"):
            continue
        if asset_filter and asset_filter not in name:
            continue
        return url
    return ""


def version_tuple_from_source_text(source_text: str):
    match = re.search(r'"version"\s*:\s*\(([^)]*)\)', source_text or "")
    if not match:
        raise RuntimeError("No se encontro bl_info.version en el addon remoto.")
    return version_tuple_from_any(match.group(1))


def updater_thread_fn(owner: str, repo: str, asset_filter: str):
    release_error = ""
    repo_error = ""
    release_candidate = None
    repo_candidate = None

    try:
        release_data = http_get_json(github_latest_release_url(owner, repo))
        tag = (release_data.get("tag_name") or release_data.get("name") or "").strip()
        if not tag:
            raise RuntimeError("No se encontro una version valida en GitHub.")

        download_url = select_best_zip_asset(release_data, asset_filter)
        if not download_url:
            download_url = (release_data.get("zipball_url") or "").strip()
        if not download_url:
            raise RuntimeError("No se encontro un ZIP descargable en la release.")
        release_candidate = {
            "version_tuple": version_tuple_from_any(tag),
            "version_label": tag,
            "download_url": download_url,
            "download_kind": "ZIP",
            "release_html_url": (release_data.get("html_url") or "").strip(),
        }
    except Exception as exc:
        release_error = str(exc)

    try:
        repo_data = http_get_json(github_repo_api_url(owner, repo))
        default_branch = (repo_data.get("default_branch") or "main").strip() or "main"
        source_text = http_get_text(github_raw_file_url(owner, repo, default_branch, DEFAULT_ADDON_FILE))
        repo_version = version_tuple_from_source_text(source_text)
        repo_candidate = {
            "version_tuple": repo_version,
            "version_label": ".".join(map(str, repo_version)),
            "download_url": (repo_data.get("zipball_url") or "").strip(),
            "download_kind": "ZIP",
            "release_html_url": github_repo_html_url(owner, repo),
        }
    except Exception as exc:
        repo_error = str(exc)

    selected = None
    if release_candidate and repo_candidate:
        selected = repo_candidate if repo_candidate["version_tuple"] > release_candidate["version_tuple"] else release_candidate
    else:
        selected = release_candidate or repo_candidate

    if selected:
        UPDATER_STATE.update(
            {
                "done": True,
                "ok": True,
                "latest_version": selected["version_label"],
                "download_url": selected["download_url"],
                "download_kind": selected["download_kind"],
                "release_html_url": selected["release_html_url"],
                "error": "",
            }
        )
        return

    error_parts = [part for part in (release_error, repo_error) if part]
    UPDATER_STATE.update(
        {
            "done": True,
            "ok": False,
            "latest_version": "",
            "download_url": "",
            "download_kind": "ZIP",
            "release_html_url": "",
            "error": " | ".join(error_parts) if error_parts else "No se pudo comprobar GitHub.",
        }
    )


def start_update_check(force=False):
    prefs = get_addon_prefs()
    if not prefs:
        return

    owner = (prefs.repo_owner or "").strip()
    repo = (prefs.repo_name or "").strip()
    if not owner or not repo:
        prefs.last_update_error = "Configura repo_owner y repo_name en las preferencias del addon."
        return

    now = time.time()
    interval_sec = max(1, int(prefs.check_interval_days)) * 86400
    if not force:
        if not prefs.auto_check_updates:
            return
        if prefs.last_check_time > 0 and (now - prefs.last_check_time) < interval_sec:
            return

    if UPDATER_STATE.get("checking"):
        return

    UPDATER_STATE.update(
        {
            "thread": None,
            "checking": True,
            "done": False,
            "ok": False,
            "latest_version": "",
            "download_url": "",
            "download_kind": "ZIP",
            "release_html_url": "",
            "error": "",
        }
    )

    thread = threading.Thread(
        target=updater_thread_fn,
        args=(owner, repo, prefs.asset_name_contains),
        daemon=True,
    )
    UPDATER_STATE["thread"] = thread
    thread.start()
    bpy.app.timers.register(poll_update_check_timer, first_interval=0.2)


def poll_update_check_timer():
    prefs = get_addon_prefs()
    if not prefs:
        UPDATER_STATE["checking"] = False
        return None

    if not UPDATER_STATE.get("done"):
        return 0.2

    prefs.last_check_time = time.time()
    if UPDATER_STATE.get("ok"):
        latest_tag = UPDATER_STATE.get("latest_version", "")
        prefs.latest_version = latest_tag
        prefs.latest_download_url = UPDATER_STATE.get("download_url", "")
        prefs.latest_download_kind = UPDATER_STATE.get("download_kind", "ZIP")
        prefs.latest_release_url = UPDATER_STATE.get("release_html_url", "")
        prefs.last_update_error = ""
        prefs.update_available = version_tuple_from_any(latest_tag) > tuple(bl_info.get("version", (0, 0, 0)))
        if prefs.update_available and prefs.last_notified_version != prefs.latest_version:
            prefs.last_notified_version = prefs.latest_version
            try:
                bpy.ops.manwtool.update_popup("INVOKE_DEFAULT")
            except Exception:
                pass
    else:
        prefs.last_update_error = UPDATER_STATE.get("error", "Error desconocido.")
        prefs.update_available = False

    UPDATER_STATE["checking"] = False
    return None


def post_install_timer():
    prefs = get_addon_prefs()
    POST_INSTALL["pending"] = False
    if prefs:
        prefs.restart_required = True
        try:
            bpy.ops.manwtool.restart_required_popup("INVOKE_DEFAULT")
        except Exception:
            pass
    return None


def startup_update_check_timer():
    start_update_check(force=False)
    return None


def reload_logo():
    global _preview_col
    if _preview_col is None:
        return
    prefs = get_addon_prefs()
    if prefs is None:
        return

    key = "manwtool_logo"
    if key in _preview_col:
        try:
            del _preview_col[key]
        except Exception:
            pass

    path = bpy.path.abspath(prefs.logo_path) if prefs.logo_path else ""
    if not path or not os.path.isfile(path):
        return

    try:
        _preview_col.load(key, path, "IMAGE")
    except Exception:
        pass


def get_logo_icon_value():
    if _preview_col is None:
        return None
    item = _preview_col.get("manwtool_logo")
    return item.icon_id if item else None


def init_preview_collection():
    global _preview_col
    if _preview_col is None:
        _preview_col = bpy.utils.previews.new()


def clear_preview_collection():
    global _preview_col
    if _preview_col is not None:
        try:
            bpy.utils.previews.remove(_preview_col)
        except Exception:
            pass
        _preview_col = None


def collection_has_child(parent, child_name):
    return parent.children.get(child_name) is not None


def ensure_valid_export_dir(base_dir, report_fn):
    if not base_dir:
        report_fn({"ERROR"}, "Carpeta no valida.")
        return None
    base_dir = bpy.path.abspath(base_dir)
    if not os.path.isdir(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            report_fn({"ERROR"}, "No se pudo crear o usar la carpeta.")
            return None
    return base_dir


def get_mesh_objects_from_selection(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def get_visible_mesh_objects(context):
    return [obj for obj in context.view_layer.objects if obj.visible_get() and obj.type == "MESH"]


def get_current_export_dir(props):
    return (props.export_dir or props.last_export_dir or "").strip()


def get_mesh_export_name_map(objects):
    name_map = {}
    for obj in objects:
        if obj.type != "MESH":
            continue
        export_name = clean_export_name(obj.name)
        name_map.setdefault(export_name, []).append(obj)
    return name_map


def collect_export_validation(context, objects):
    mesh_objects = [obj for obj in objects if obj and obj.name in bpy.data.objects and obj.type == "MESH"]
    scene_meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    scene_name_map = get_mesh_export_name_map(scene_meshes)

    results = []
    summary = {
        "objects_checked": len(mesh_objects),
        "transform_issues": 0,
        "duplicate_issues": 0,
        "collection_issues": 0,
        "warning_count": 0,
    }

    for obj in mesh_objects:
        transform_issues = []
        if any(abs(value) > 0.0001 for value in obj.location):
            transform_issues.append(f"location={tuple(round(v, 4) for v in obj.location)}")
        if any(abs(value) > 0.0001 for value in obj.rotation_euler):
            transform_issues.append(f"rotation={tuple(round(v, 4) for v in obj.rotation_euler)}")
        if any(abs(value - 1.0) > 0.0001 for value in obj.scale):
            transform_issues.append(f"scale={tuple(round(v, 4) for v in obj.scale)}")

        export_name = clean_export_name(obj.name)
        duplicate_names = [other.name for other in scene_name_map.get(export_name, []) if other.name != obj.name]

        collection_names = [col.name for col in obj.users_collection]
        collection_issues = []
        if not collection_names:
            collection_issues.append("sin coleccion asignada")
        else:
            if len(collection_names) > 1:
                collection_issues.append(f"multiples colecciones={', '.join(collection_names)}")
            if not any(name.endswith(VALID_COLLECTION_SUFFIXES) for name in collection_names):
                collection_issues.append(f"fuera de coleccion esperada={', '.join(collection_names)}")

        summary["transform_issues"] += len(transform_issues)
        summary["duplicate_issues"] += len(duplicate_names)
        summary["collection_issues"] += len(collection_issues)
        summary["warning_count"] += int(bool(transform_issues or duplicate_names or collection_issues))

        results.append(
            {
                "object_name": obj.name,
                "export_name": export_name,
                "transform_issues": transform_issues,
                "duplicate_names": duplicate_names,
                "collection_names": collection_names,
                "collection_issues": collection_issues,
            }
        )

    return {
        "summary": summary,
        "results": results,
    }


def write_export_validation_report(base_dir, validation_data, export_summary=None):
    base_dir = bpy.path.abspath(base_dir)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(base_dir, f"manwtool_export_report_{timestamp}.txt")

    lines = [
        "ManWTool Export Validation Report",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    if export_summary:
        lines.extend(
            [
                "Export Summary",
                f"- Exportados: {export_summary.get('exported', 0)}",
                f"- Fallidos: {export_summary.get('failed', 0)}",
                f"- Duplicados omitidos: {export_summary.get('skipped_duplicates', 0)}",
                "",
            ]
        )

    summary = validation_data.get("summary", {})
    lines.extend(
        [
            "Validation Summary",
            f"- Objetos revisados: {summary.get('objects_checked', 0)}",
            f"- Objetos con avisos: {summary.get('warning_count', 0)}",
            f"- Issues de transform: {summary.get('transform_issues', 0)}",
            f"- Issues de duplicados: {summary.get('duplicate_issues', 0)}",
            f"- Issues de colecciones: {summary.get('collection_issues', 0)}",
            "",
            "Per Object",
        ]
    )

    for item in validation_data.get("results", []):
        lines.append(f"* {item['object_name']} -> {item['export_name']}")
        if item["transform_issues"]:
            lines.append(f"  - Transform: {' | '.join(item['transform_issues'])}")
        if item["duplicate_names"]:
            lines.append(f"  - Duplicados: {', '.join(item['duplicate_names'])}")
        if item["collection_names"]:
            lines.append(f"  - Colecciones: {', '.join(item['collection_names'])}")
        else:
            lines.append("  - Colecciones: ninguna")
        if item["collection_issues"]:
            lines.append(f"  - Issues coleccion: {' | '.join(item['collection_issues'])}")
        if not item["transform_issues"] and not item["duplicate_names"] and not item["collection_issues"]:
            lines.append("  - Estado: OK")
        lines.append("")

    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return report_path


def ensure_object_mode():
    obj = bpy.context.active_object
    if obj and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def apply_export_prep_to_object(context, obj):
    ensure_object_mode()
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = list(context.selected_objects)

    try:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
        obj.location = (0.0, 0.0, 0.0)
    finally:
        try:
            obj.select_set(False)
        except Exception:
            pass
        for selected in prev_selected:
            if selected.name in bpy.data.objects:
                selected.select_set(True)
        if prev_active and prev_active.name in bpy.data.objects:
            view_layer.objects.active = prev_active


def export_mesh_object_to_fbx(context, src, base_dir, report_fn):
    if src is None:
        report_fn({"ERROR"}, "No hay objeto para exportar.")
        return False
    if src.type != "MESH":
        report_fn({"ERROR"}, f"{src.name} no es un MESH.")
        return False

    base_dir = ensure_valid_export_dir(base_dir, report_fn)
    if not base_dir:
        return False

    export_name = clean_export_name(src.name)
    export_dir = os.path.join(base_dir, export_name)
    os.makedirs(export_dir, exist_ok=True)
    final_fbx_path = os.path.join(export_dir, f"{export_name}.fbx")

    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = src.evaluated_get(depsgraph)

    try:
        baked_mesh = bpy.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True, depsgraph=depsgraph)
    except TypeError:
        baked_mesh = bpy.data.meshes.new_from_object(eval_obj, preserve_all_data_layers=True)

    tmp_obj = bpy.data.objects.new(f"{export_name}_EXPORT_TMP", baked_mesh)
    if src.data and src.data.materials:
        baked_mesh.materials.clear()
        for mat in src.data.materials:
            baked_mesh.materials.append(mat)

    tmp_col = bpy.data.collections.get("_ManWTool_EXPORT_TMP")
    created_tmp_col = False
    if tmp_col is None:
        tmp_col = bpy.data.collections.new("_ManWTool_EXPORT_TMP")
        context.scene.collection.children.link(tmp_col)
        created_tmp_col = True
    tmp_col.objects.link(tmp_obj)
    tmp_obj.matrix_world = src.matrix_world.copy()

    try:
        apply_export_prep_to_object(context, tmp_obj)
        bpy.ops.object.select_all(action="DESELECT")
        tmp_obj.select_set(True)
        context.view_layer.objects.active = tmp_obj
        bpy.ops.export_scene.fbx(
            filepath=final_fbx_path,
            use_selection=True,
            object_types={"MESH"},
            apply_unit_scale=True,
            axis_forward="-Z",
            axis_up="Y",
            add_leaf_bones=False,
            use_mesh_modifiers=False,
        )
    except Exception as exc:
        report_fn({"ERROR"}, f"Error exportando {src.name}: {exc}")
        return False
    finally:
        try:
            tmp_col.objects.unlink(tmp_obj)
        except Exception:
            pass
        try:
            bpy.data.objects.remove(tmp_obj, do_unlink=True)
        except Exception:
            pass
        try:
            bpy.data.meshes.remove(baked_mesh, do_unlink=True)
        except Exception:
            pass
        if created_tmp_col and tmp_col and len(tmp_col.objects) == 0:
            try:
                context.scene.collection.children.unlink(tmp_col)
            except Exception:
                pass
            try:
                bpy.data.collections.remove(tmp_col)
            except Exception:
                pass

    report_fn({"INFO"}, f"Exportado: {final_fbx_path}")
    return True


def find_matching_textures(material_name: str, obj_name: str, materials_dir: str):
    if not os.path.isdir(materials_dir):
        return {}

    normalized_targets = {normalize_name(material_name), normalize_name(clean_export_name(obj_name))}
    files = [
        os.path.join(materials_dir, name)
        for name in os.listdir(materials_dir)
        if os.path.isfile(os.path.join(materials_dir, name))
    ]

    matched = {}
    for path in files:
        base_name = normalize_name(os.path.splitext(os.path.basename(path))[0])
        if not any(token and token in base_name for token in normalized_targets):
            continue
        for map_type, aliases in TEXTURE_RULES.items():
            if map_type in matched:
                continue
            if any(alias in base_name for alias in aliases):
                matched[map_type] = path
                break
    return matched


def load_image(image_path, colorspace="sRGB"):
    image = bpy.data.images.load(image_path, check_existing=True)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image


def clear_manw_texture_nodes(material):
    if not material or not material.use_nodes or not material.node_tree:
        return
    nodes = material.node_tree.nodes
    removable = [node for node in nodes if (node.label or "").startswith("MANW_")]
    for node in removable:
        try:
            nodes.remove(node)
        except Exception:
            pass


def assign_textures_to_material(material, textures):
    if not textures or material is None:
        return False

    material.use_nodes = True
    clear_manw_texture_nodes(material)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)

    if principled is None:
        principled = nodes.new("ShaderNodeBsdfPrincipled")
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
    if not principled.outputs["BSDF"].is_linked:
        links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    y = 300
    changed = False
    emission_socket = principled.inputs.get("Emission") or principled.inputs.get("Emission Color")

    if "BASE_COLOR" in textures:
        node = nodes.new("ShaderNodeTexImage")
        node.label = "MANW_BASE_COLOR"
        node.location = (-650, y)
        node.image = load_image(textures["BASE_COLOR"], "sRGB")
        links.new(node.outputs["Color"], principled.inputs["Base Color"])
        changed = True

    if "ROUGHNESS" in textures:
        node = nodes.new("ShaderNodeTexImage")
        node.label = "MANW_ROUGHNESS"
        node.location = (-650, y - 260)
        node.image = load_image(textures["ROUGHNESS"], "Non-Color")
        links.new(node.outputs["Color"], principled.inputs["Roughness"])
        changed = True

    if "METALLIC" in textures:
        node = nodes.new("ShaderNodeTexImage")
        node.label = "MANW_METALLIC"
        node.location = (-650, y - 520)
        node.image = load_image(textures["METALLIC"], "Non-Color")
        links.new(node.outputs["Color"], principled.inputs["Metallic"])
        changed = True

    if "NORMAL" in textures:
        tex = nodes.new("ShaderNodeTexImage")
        tex.label = "MANW_NORMAL"
        tex.location = (-950, y - 780)
        tex.image = load_image(textures["NORMAL"], "Non-Color")
        normal = nodes.new("ShaderNodeNormalMap")
        normal.label = "MANW_NORMAL_MAP"
        normal.location = (-650, y - 780)
        links.new(tex.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], principled.inputs["Normal"])
        changed = True

    if "EMISSION" in textures and emission_socket:
        node = nodes.new("ShaderNodeTexImage")
        node.label = "MANW_EMISSION"
        node.location = (-650, y - 1040)
        node.image = load_image(textures["EMISSION"], "sRGB")
        links.new(node.outputs["Color"], emission_socket)
        changed = True

    if "OPACITY" in textures:
        node = nodes.new("ShaderNodeTexImage")
        node.label = "MANW_OPACITY"
        node.location = (-650, y - 1300)
        node.image = load_image(textures["OPACITY"], "Non-Color")
        links.new(node.outputs["Color"], principled.inputs["Alpha"])
        material.blend_method = "BLEND"
        changed = True

    return changed


def apply_material_pack_to_imported_objects(objects, materials_dir):
    summary = {
        "mesh_objects": 0,
        "materials_seen": 0,
        "materials_updated": 0,
        "objects_with_matches": 0,
        "objects_without_matches": 0,
    }

    for obj in objects:
        if obj.type != "MESH" or not obj.data:
            continue
        summary["mesh_objects"] += 1
        object_matched = False
        for material in obj.data.materials:
            if material is None:
                continue
            summary["materials_seen"] += 1
            textures = find_matching_textures(material.name, obj.name, materials_dir)
            if assign_textures_to_material(material, textures):
                summary["materials_updated"] += 1
                object_matched = True
        if object_matched:
            summary["objects_with_matches"] += 1
        else:
            summary["objects_without_matches"] += 1

    return summary


def prepare_imported_objects(context, objects, apply_scale=True, reset_rotation=True, move_to_origin=True):
    if not objects:
        return 0

    ensure_object_mode()
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = list(context.selected_objects)
    processed = 0

    try:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            if obj.name in bpy.data.objects:
                obj.select_set(True)

        for obj in objects:
            if obj.name not in bpy.data.objects or obj.type != "MESH":
                continue
            view_layer.objects.active = obj
            bpy.ops.object.transform_apply(
                location=False,
                rotation=bool(reset_rotation),
                scale=bool(apply_scale),
            )
            bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
            if move_to_origin:
                obj.location = (0.0, 0.0, 0.0)
            if reset_rotation:
                obj.rotation_euler = (0.0, 0.0, 0.0)
            processed += 1
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in prev_selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if prev_active and prev_active.name in bpy.data.objects:
            view_layer.objects.active = prev_active

    return processed


def active_obj_status(context):
    obj = context.active_object
    if obj is None:
        return ("Sin objeto activo", "ERROR", "ERROR")
    if obj.type != "MESH":
        return (f"Activo: {obj.name} ({obj.type})", "WARNING", "ERROR")
    return (f"Activo: {obj.name} (MESH)", "INFO", "MESH_CUBE")

class MANWTOOL_Preferences(AddonPreferences):
    bl_idname = "ManWTool"

    logo_path: StringProperty(name="Logo (PNG)", subtype="FILE_PATH", default="")
    repo_owner: StringProperty(name="GitHub Owner", default=DEFAULT_REPO_OWNER)
    repo_name: StringProperty(name="GitHub Repo", default=DEFAULT_REPO_NAME)
    asset_name_contains: StringProperty(name="Filtro ZIP", default="ManWTool")
    auto_check_updates: BoolProperty(name="Comprobar al iniciar", default=True)
    check_interval_days: IntProperty(name="Intervalo (dias)", default=1, min=1, max=30)
    last_check_time: FloatProperty(default=0.0)
    update_available: BoolProperty(default=False)
    latest_version: StringProperty(default="")
    latest_download_url: StringProperty(default="")
    latest_download_kind: StringProperty(default="ZIP")
    latest_release_url: StringProperty(default="")
    last_update_error: StringProperty(default="")
    last_notified_version: StringProperty(default="")
    restart_required: BoolProperty(default=False)

    def draw(self, context):
        layout = self.layout

        logo = layout.box()
        logo.label(text="Apariencia", icon="IMAGE_DATA")
        logo.prop(self, "logo_path")

        box = layout.box()
        box.label(text="Auto-update (GitHub)", icon="FILE_REFRESH")
        col = box.column(align=True)
        col.prop(self, "repo_owner")
        col.prop(self, "repo_name")
        col.prop(self, "asset_name_contains")

        row = box.row(align=True)
        row.prop(self, "auto_check_updates")
        row.prop(self, "check_interval_days")
        box.operator("manwtool.check_updates", text="Comprobar ahora", icon="VIEWZOOM")

        if self.update_available:
            update_box = box.box()
            update_box.alert = True
            update_box.label(text=f"Update disponible: {self.latest_version} (tu: {current_version_str()})", icon="INFO")
            row = update_box.row(align=True)
            row.operator("manwtool.install_update", text="Actualizar", icon="IMPORT")
            if self.latest_release_url:
                row.operator("manwtool.open_release_page", text="Ver release", icon="URL")

        if self.restart_required:
            restart_box = box.box()
            restart_box.alert = True
            restart_box.label(text="Update instalado. Reinicia Blender.", icon="ERROR")
            restart_box.operator("manwtool.clear_restart_flag", text="Ocultar aviso", icon="CHECKMARK")

        if self.last_update_error:
            err = box.box()
            err.alert = True
            err.label(text=f"Error: {self.last_update_error}", icon="ERROR")


class MANWTOOL_Properties(PropertyGroup):
    ui_section: EnumProperty(
        name="Seccion",
        items=[
            ("FOLDERS", "Colecciones", ""),
            ("RENAME", "Renombrar", ""),
            ("EXPORT", "Exportar", ""),
            ("IMPORT", "Importar", ""),
        ],
        default="EXPORT",
    )

    root_name: StringProperty(name="Raiz", default="Asset")
    rename_prefix: StringProperty(name="Prefijo", default="SM_")
    rename_base: StringProperty(name="Nombre", default="Object")
    export_dir: StringProperty(name="Carpeta exportacion", subtype="DIR_PATH", default="")
    last_export_dir: StringProperty(name="Ultima carpeta", subtype="DIR_PATH", default="")
    import_fbx_path: StringProperty(name="FBX", subtype="FILE_PATH", default="")
    import_materials_dir: StringProperty(name="Carpeta materiales", subtype="DIR_PATH", default="")
    reset_import_rotation: BoolProperty(name="Rotacion a 0", default=True)
    send_import_to_origin: BoolProperty(name="Posicion a 0,0,0", default=True)
    apply_import_scale: BoolProperty(name="Aplicar escala", default=True)



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
    return {
        "current_dir": current_dir,
        "has_export_dir": bool(current_dir),
        "active_mesh_ok": bool(active and active.type == "MESH"),
        "selected_meshes": selected_meshes,
        "selected_count": len(selected_meshes),
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
            "Validator | "
            f"Objetos con avisos: {summary['warning_count']} | "
            f"Transform: {summary['transform_issues']} | "
            f"Duplicados: {summary['duplicate_issues']} | "
            f"Colecciones: {summary['collection_issues']}",
        )
    else:
        report_fn({"INFO"}, "Validator | Sin avisos en transform, duplicados o colecciones.")

    if report_path:
        report_fn({"INFO"}, f"Informe generado: {report_path}")
    return validation, report_path


class MANWTOOL_OT_check_updates(Operator):
    bl_idname = "manwtool.check_updates"
    bl_label = "Comprobar updates"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        start_update_check(force=True)
        self.report({"INFO"}, "Comprobando updates...")
        return {"FINISHED"}


class MANWTOOL_OT_open_release_page(Operator):
    bl_idname = "manwtool.open_release_page"
    bl_label = "Abrir release"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs and prefs.latest_release_url:
            bpy.ops.wm.url_open(url=prefs.latest_release_url)
            return {"FINISHED"}
        self.report({"ERROR"}, "No hay URL de release.")
        return {"CANCELLED"}


class MANWTOOL_OT_install_update(Operator):
    bl_idname = "manwtool.install_update"
    bl_label = "Actualizar ManWTool"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if not prefs:
            self.report({"ERROR"}, "No se pudieron leer las preferencias.")
            return {"CANCELLED"}

        url = (prefs.latest_download_url or "").strip()
        if not url:
            self.report({"ERROR"}, "Primero ejecuta 'Comprobar ahora'.")
            return {"CANCELLED"}

        tmp_dir = tempfile.mkdtemp(prefix="manwtool_update_")
        installer_path = os.path.join(tmp_dir, "manwtool_update.zip")

        try:
            download_file(url, installer_path, timeout=60)
            call_in_preferences_context(bpy.ops.preferences.addon_install, filepath=installer_path, overwrite=True)
            prefs.restart_required = True
            POST_INSTALL["pending"] = True
            POST_INSTALL["zip_path"] = installer_path
            bpy.app.timers.register(post_install_timer, first_interval=0.2)
            self.report({"INFO"}, "Update instalado. Reinicia Blender.")
            return {"FINISHED"}
        except Exception as exc:
            prefs.last_update_error = str(exc)
            self.report({"ERROR"}, f"Fallo la actualizacion: {exc}")
            return {"CANCELLED"}


class MANWTOOL_OT_update_popup(Operator):
    bl_idname = "manwtool.update_popup"
    bl_label = "Update disponible"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        prefs = get_addon_prefs()
        layout = self.layout
        layout.label(text="Hay una version nueva de ManWTool.", icon="INFO")
        if prefs:
            layout.label(text=f"Instalada: {current_version_str()} | Nueva: {prefs.latest_version}")
        row = layout.row(align=True)
        row.operator("manwtool.install_update", text="Actualizar ahora", icon="IMPORT")
        if prefs and prefs.latest_release_url:
            row.operator("manwtool.open_release_page", text="Ver release", icon="URL")

    def execute(self, context):
        return {"FINISHED"}


class MANWTOOL_OT_restart_required_popup(Operator):
    bl_idname = "manwtool.restart_required_popup"
    bl_label = "Reinicio requerido"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Update instalado correctamente.", icon="CHECKMARK")
        layout.label(text="Reinicia Blender para aplicar los cambios.", icon="INFO")

    def execute(self, context):
        return {"FINISHED"}


class MANWTOOL_OT_clear_restart_flag(Operator):
    bl_idname = "manwtool.clear_restart_flag"
    bl_label = "Ocultar aviso"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        prefs = get_addon_prefs()
        if prefs:
            prefs.restart_required = False
        return {"FINISHED"}


class MANWTOOL_OT_pick_export_dir(Operator):
    bl_idname = "manwtool.pick_export_dir"
    bl_label = "Elegir carpeta"
    bl_options = {"REGISTER"}

    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        props = context.scene.manwtool_props
        self.directory = bpy.path.abspath(get_current_export_dir(props) or "//")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        props = context.scene.manwtool_props
        chosen_dir = bpy.path.abspath((self.directory or "").strip())
        if not chosen_dir:
            self.report({"ERROR"}, "No se ha seleccionado ninguna carpeta.")
            return {"CANCELLED"}
        try:
            os.makedirs(chosen_dir, exist_ok=True)
        except Exception:
            self.report({"ERROR"}, "No se pudo usar esa carpeta.")
            return {"CANCELLED"}
        props.export_dir = chosen_dir
        self.report({"INFO"}, f"Carpeta seleccionada: {chosen_dir}")
        return {"FINISHED"}


class MANWTOOL_OT_pick_import_fbx(Operator, ImportHelper):
    bl_idname = "manwtool.pick_import_fbx"
    bl_label = "Seleccionar FBX"
    bl_options = {"REGISTER"}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def execute(self, context):
        context.scene.manwtool_props.import_fbx_path = self.filepath
        self.report({"INFO"}, f"FBX seleccionado: {os.path.basename(self.filepath)}")
        return {"FINISHED"}


class MANWTOOL_OT_pick_materials_dir(Operator):
    bl_idname = "manwtool.pick_materials_dir"
    bl_label = "Seleccionar materiales"
    bl_options = {"REGISTER"}

    directory: StringProperty(subtype="DIR_PATH")

    def invoke(self, context, event):
        props = context.scene.manwtool_props
        self.directory = bpy.path.abspath(props.import_materials_dir or "//")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        chosen_dir = bpy.path.abspath((self.directory or "").strip())
        context.scene.manwtool_props.import_materials_dir = chosen_dir
        self.report({"INFO"}, f"Carpeta de materiales: {chosen_dir}")
        return {"FINISHED"}


class MANWTOOL_OT_create_folders(Operator):
    bl_idname = "manwtool.create_folders"
    bl_label = "Crear estructura"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.manwtool_props
        base = (props.root_name or "").strip()
        if not base:
            self.report({"ERROR"}, "Escribe un nombre para la raiz.")
            return {"CANCELLED"}

        root_name = base
        high_name = f"{base}_High"
        low_name = f"{base}_Low"
        ref_name = f"{base}_Reference"

        root_col = bpy.data.collections.get(root_name)
        if root_col is None:
            root_col = bpy.data.collections.new(root_name)
            context.scene.collection.children.link(root_col)
        elif context.scene.collection.children.get(root_col.name) is None:
            context.scene.collection.children.link(root_col)

        def ensure_child(parent, child_name):
            col = bpy.data.collections.get(child_name)
            if col is None:
                col = bpy.data.collections.new(child_name)
            if not collection_has_child(parent, child_name):
                parent.children.link(col)
            return col

        ensure_child(root_col, high_name).color_tag = "COLOR_01"
        ensure_child(root_col, low_name).color_tag = "COLOR_03"
        ensure_child(root_col, ref_name).color_tag = "COLOR_05"
        self.report({"INFO"}, f"Estructura creada: {root_name}, {high_name}, {low_name}, {ref_name}")
        return {"FINISHED"}


class MANWTOOL_OT_rename_geo_data_material(Operator):
    bl_idname = "manwtool.rename_geo_data_material"
    bl_label = "Aplicar nombre"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Necesitas un objeto MESH activo.")
            return {"CANCELLED"}

        props = context.scene.manwtool_props
        final_name = f"{(props.rename_prefix or '').strip()}{(props.rename_base or '').strip()}"
        if not final_name.strip():
            self.report({"ERROR"}, "Escribe un nombre.")
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

        self.report({"INFO"}, f"Nombre aplicado a objeto, data y material: {final_name}")
        return {"FINISHED"}


class MANWTOOL_OT_export_fbx(Operator, ExportHelper):
    bl_idname = "manwtool.export_fbx"
    bl_label = "Exportar FBX"
    bl_options = {"REGISTER"}

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def invoke(self, context, event):
        props = context.scene.manwtool_props
        obj = context.active_object
        default_name = f"{clean_export_name(obj.name)}.fbx" if obj else "Export.fbx"
        base_dir = get_current_export_dir(props)
        self.filepath = os.path.join(bpy.path.abspath(base_dir), default_name) if base_dir else default_name
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        chosen_dir = os.path.dirname(self.filepath) if self.filepath else ""
        if not chosen_dir:
            self.report({"ERROR"}, "Ruta de exportacion no valida.")
            return {"CANCELLED"}

        props = context.scene.manwtool_props
        props.export_dir = chosen_dir
        props.last_export_dir = chosen_dir
        run_export_validation_and_report(context, [context.active_object], chosen_dir, self.report)
        ok = export_mesh_object_to_fbx(context, context.active_object, chosen_dir, self.report)
        return {"FINISHED"} if ok else {"CANCELLED"}


class MANWTOOL_OT_reexport_fbx(Operator):
    bl_idname = "manwtool.reexport_fbx"
    bl_label = "ReExport"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.manwtool_props
        base_dir = get_current_export_dir(props)
        if not base_dir:
            self.report({"ERROR"}, "Selecciona primero una carpeta de exportacion.")
            return {"CANCELLED"}
        props.last_export_dir = base_dir
        run_export_validation_and_report(context, [context.active_object], base_dir, self.report)
        ok = export_mesh_object_to_fbx(context, context.active_object, base_dir, self.report)
        return {"FINISHED"} if ok else {"CANCELLED"}


class MANWTOOL_OT_select_all_meshes(Operator):
    bl_idname = "manwtool.select_all_meshes"
    bl_label = "Seleccionar toda la geometria"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        bpy.ops.object.select_all(action="DESELECT")
        meshes = get_visible_mesh_objects(context)
        for obj in meshes:
            obj.select_set(True)
        if meshes:
            context.view_layer.objects.active = meshes[0]
        self.report({"INFO"}, f"{len(meshes)} geometria(s) seleccionada(s).")
        return {"FINISHED"}


class MANWTOOL_OT_export_multiple_fbx(Operator):
    bl_idname = "manwtool.export_multiple_fbx"
    bl_label = "Exportar multiple"
    bl_options = {"REGISTER"}

    def execute(self, context):
        props = context.scene.manwtool_props
        base_dir = get_current_export_dir(props)
        if not base_dir:
            self.report({"ERROR"}, "Selecciona primero una carpeta de exportacion.")
            return {"CANCELLED"}

        selected_meshes = get_mesh_objects_from_selection(context)
        if not selected_meshes:
            self.report({"ERROR"}, "No hay objetos MESH seleccionados.")
            return {"CANCELLED"}

        props.last_export_dir = base_dir
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
            if export_mesh_object_to_fbx(context, obj, base_dir, self.report):
                exported += 1
            else:
                failed += 1

        self.report(
            {"INFO"},
            f"Export multiple terminado | Exportados: {exported} | Duplicados omitidos: {skipped_duplicates} | Fallidos: {failed}",
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
        self.report({"INFO"}, f"Informe generado: {report_path}")
        return {"FINISHED"}


class MANWTOOL_OT_import_fbx_pack(Operator):
    bl_idname = "manwtool.import_fbx_pack"
    bl_label = "Importar FBX + materiales"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.manwtool_props
        status = get_import_requirements_status(props)

        if not status["fbx_ok"]:
            self.report({"ERROR"}, "Selecciona un archivo FBX valido.")
            return {"CANCELLED"}
        if not status["materials_ok"]:
            self.report({"ERROR"}, "Selecciona una carpeta de materiales valida.")
            return {"CANCELLED"}

        before_names = {obj.name for obj in bpy.data.objects}
        try:
            bpy.ops.import_scene.fbx(filepath=status["fbx_path"], automatic_bone_orientation=True)
        except Exception as exc:
            self.report({"ERROR"}, f"No se pudo importar el FBX: {exc}")
            return {"CANCELLED"}

        imported_objects = [obj for obj in context.selected_objects if obj.name not in before_names]
        if not imported_objects:
            imported_objects = list(context.selected_objects)
        if not imported_objects:
            self.report({"ERROR"}, "El FBX no ha generado objetos importados detectables.")
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
            "Importacion completada | "
            f"Objetos: {len(imported_objects)} | "
            f"MESH: {imported_meshes} | "
            f"Preparados: {prepared} | "
            f"Materiales actualizados: {material_summary['materials_updated']} | "
            f"Objetos con texturas: {material_summary['objects_with_matches']}",
        )
        return {"FINISHED"}



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
    box.label(text="Actualizaciones", icon="FILE_REFRESH")

    if prefs.last_update_error:
        err = box.box()
        err.alert = True
        err.label(text=prefs.last_update_error, icon="ERROR")

    if prefs.update_available:
        box.label(text=f"Nueva version: {prefs.latest_version} (tu: {current_version_str()})", icon="INFO")
        row = box.row(align=True)
        row.scale_y = 1.2
        row.operator("manwtool.install_update", text="Actualizar", icon="IMPORT")
        row.operator("manwtool.check_updates", text="Revisar", icon="VIEWZOOM")
        if prefs.latest_release_url:
            row.operator("manwtool.open_release_page", text="", icon="URL")
    else:
        box.operator("manwtool.check_updates", text="Comprobar updates", icon="VIEWZOOM")

    if prefs.restart_required:
        warn = box.box()
        warn.alert = True
        warn.label(text="Update instalado. Reinicia Blender para aplicarlo.", icon="ERROR")
        warn.operator("manwtool.clear_restart_flag", text="Ocultar aviso", icon="CHECKMARK")


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
        row.label(text=f"Update: {prefs.latest_version}", icon="FILE_REFRESH")

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

    shown_value = bpy.path.abspath(current_value) if current_value else "-"
    info = box.box()
    info.enabled = False
    info.label(text=shown_value)
    return box


def draw_status_lines(layout, lines):
    info = layout.box()
    info.enabled = False
    for line in lines:
        info.label(text=line)


def draw_section_folders(layout, context, props):
    box = layout.box()
    box.label(text="Estructura de colecciones", icon="OUTLINER_COLLECTION")
    box.prop(props, "root_name", text="Raiz")

    preview = box.box()
    preview.enabled = False
    base = (props.root_name or "").strip() or "Asset"
    preview.label(text=f"Se crearan: {base}, {base}_High, {base}_Low, {base}_Reference")

    big_button(box).operator("manwtool.create_folders", icon="PLUS")


def draw_section_rename(layout, context, props):
    box = layout.box()
    box.label(text="Naming consistente", icon="FILE_TEXT")
    col = box.column(align=True)
    col.prop(props, "rename_prefix")
    col.prop(props, "rename_base")

    final_name = f"{(props.rename_prefix or '').strip()}{(props.rename_base or '').strip()}"
    preview = box.box()
    preview.enabled = False
    preview.label(text=f"Resultado: {final_name}", icon="CHECKMARK")

    obj = context.active_object
    hint = box.box()
    hint.enabled = False
    if obj and obj.type == "MESH":
        hint.label(text=f"Se aplicara a: {obj.name}")
    else:
        hint.label(text="Necesitas un objeto MESH activo.")

    btn = big_button(box)
    btn.enabled = bool(obj and obj.type == "MESH")
    btn.operator("manwtool.rename_geo_data_material", icon="FILE_TICK")


def draw_section_export(layout, context, props):
    status = get_export_requirements_status(context, props)
    active_name = context.active_object.name if context.active_object else "Ninguno"

    draw_path_picker(
        layout,
        title="Carpeta de exportacion",
        button_text="Seleccionar carpeta de exportacion",
        current_value=status["current_dir"],
        operator_id="manwtool.pick_export_dir",
        icon="FILE_FOLDER",
    )

    draw_status_lines(
        layout,
        [
            f"Objeto activo: {active_name}",
            f"MESH seleccionados: {status['selected_count']}",
            "El export crea una carpeta por objeto y un FBX dentro.",
        ],
    )

    box_single = layout.box()
    box_single.label(text="FBX individual", icon="EXPORT")
    info = box_single.column(align=True)
    info.enabled = False
    info.label(text="Aplica rotacion y escala en una copia temporal")
    info.label(text="Centra origen y posiciona a 0,0,0")

    row = box_single.row(align=True)
    row.scale_y = 1.35
    row.enabled = status["active_mesh_ok"]
    row.operator("manwtool.export_fbx", text="Export", icon="EXPORT")

    row2 = box_single.row(align=True)
    row2.scale_y = 1.35
    row2.enabled = status["active_mesh_ok"] and status["has_export_dir"]
    row2.operator("manwtool.reexport_fbx", text="ReExport", icon="FILE_REFRESH")

    box_multi = layout.box()
    box_multi.label(text="Exportacion multiple", icon="COPYDOWN")
    draw_status_lines(
        box_multi,
        [
            "Selecciona varios MESH para exportarlos en lote.",
            "Los nombres duplicados se omiten una sola vez.",
        ],
    )
    big_button(box_multi).operator("manwtool.select_all_meshes", icon="RESTRICT_SELECT_OFF")
    btn = big_button(box_multi)
    btn.enabled = status["has_export_dir"] and status["selected_count"] > 0
    btn.operator("manwtool.export_multiple_fbx", icon="EXPORT")


def draw_section_import(layout, context, props):
    status = get_import_requirements_status(props)
    box = layout.box()
    box.label(text="Importacion automatica", icon="IMPORT")

    draw_path_picker(
        box,
        title="1. FBX a importar",
        button_text="Seleccionar archivo FBX",
        current_value=props.import_fbx_path,
        operator_id="manwtool.pick_import_fbx",
        icon="FILE",
    )

    draw_path_picker(
        box,
        title="2. Carpeta de materiales",
        button_text="Seleccionar carpeta de materiales",
        current_value=props.import_materials_dir,
        operator_id="manwtool.pick_materials_dir",
        icon="FILE_FOLDER",
    )

    opts = box.box()
    opts.label(text="3. Preparacion del import", icon="SETTINGS")
    col = opts.column(align=True)
    col.prop(props, "apply_import_scale")
    col.prop(props, "reset_import_rotation")
    col.prop(props, "send_import_to_origin")

    readiness = box.box()
    readiness.alert = not (status["fbx_ok"] and status["materials_ok"])
    readiness.label(text="Estado del flujo", icon="INFO")
    readiness.label(text=f"FBX listo: {'Si' if status['fbx_ok'] else 'No'}")
    readiness.label(text=f"Materiales listos: {'Si' if status['materials_ok'] else 'No'}")

    info = box.box()
    info.enabled = False
    info.label(text="Importa el FBX, prepara transformaciones y busca texturas.")
    info.label(text="La carpeta de materiales debe contener archivos reconocibles por nombre.")

    btn = big_button(box)
    btn.enabled = status["fbx_ok"] and status["materials_ok"]
    btn.operator("manwtool.import_fbx_pack", icon="IMPORT")


class MANWTOOL_PT_main(Panel):
    bl_label = "ManWTool"
    bl_idname = "MANWTOOL_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ManWTool"

    def draw(self, context):
        layout = self.layout
        props = context.scene.manwtool_props

        draw_header(self, context, show_status=True)
        draw_update_box_if_needed(layout)
        layout.separator()

        split = layout.split(factor=0.16, align=True)
        nav = split.column(align=True)
        nav.scale_y = 1.3
        nav.prop_enum(props, "ui_section", "FOLDERS", text="", icon="FILE_FOLDER")
        nav.prop_enum(props, "ui_section", "RENAME", text="", icon="FILE_TEXT")
        nav.prop_enum(props, "ui_section", "EXPORT", text="", icon="EXPORT")
        nav.prop_enum(props, "ui_section", "IMPORT", text="", icon="IMPORT")

        content = split.column(align=True)
        if props.ui_section == "FOLDERS":
            draw_section_folders(content, context, props)
        elif props.ui_section == "RENAME":
            draw_section_rename(content, context, props)
        elif props.ui_section == "EXPORT":
            draw_section_export(content, context, props)
        else:
            draw_section_import(content, context, props)




classes = (
    MANWTOOL_Preferences,
    MANWTOOL_Properties,
    MANWTOOL_OT_check_updates,
    MANWTOOL_OT_open_release_page,
    MANWTOOL_OT_install_update,
    MANWTOOL_OT_update_popup,
    MANWTOOL_OT_restart_required_popup,
    MANWTOOL_OT_clear_restart_flag,
    MANWTOOL_OT_pick_export_dir,
    MANWTOOL_OT_pick_import_fbx,
    MANWTOOL_OT_pick_materials_dir,
    MANWTOOL_OT_create_folders,
    MANWTOOL_OT_rename_geo_data_material,
    MANWTOOL_OT_export_fbx,
    MANWTOOL_OT_reexport_fbx,
    MANWTOOL_OT_select_all_meshes,
    MANWTOOL_OT_export_multiple_fbx,
    MANWTOOL_OT_import_fbx_pack,
    MANWTOOL_PT_main,
)


def register():
    init_preview_collection()

    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    for cls in classes:
        bpy.utils.register_class(cls)

    if hasattr(bpy.types.Scene, "manwtool_props"):
        del bpy.types.Scene.manwtool_props
    bpy.types.Scene.manwtool_props = PointerProperty(type=MANWTOOL_Properties)

    try:
        reload_logo()
    except Exception:
        pass

    try:
        bpy.app.timers.register(startup_update_check_timer, first_interval=2.0)
    except Exception:
        pass


def unregister():
    if hasattr(bpy.types.Scene, "manwtool_props"):
        del bpy.types.Scene.manwtool_props

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    clear_preview_collection()


if __name__ == "__main__":
    register()
