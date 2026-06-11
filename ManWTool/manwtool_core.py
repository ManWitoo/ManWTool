import json
import hashlib
import os
import platform
import re
import shutil
import threading
import time
import traceback
import urllib.request
import urllib.error
import uuid
import zipfile

import bpy
import bpy.utils.previews
import bmesh

from .manwtool_collections import VALID_COLLECTION_SUFFIXES
from .manwtool_export import get_export_settings_for_props
from .manwtool_i18n import get_effective_language, tr

try:
    from .manwtool_edition import REQUIRE_LICENSE
except Exception:
    REQUIRE_LICENSE = False

try:
    from .manwtool_protected import match_texture_files as protected_match_texture_files
except Exception:
    try:
        from manwtool_protected import match_texture_files as protected_match_texture_files
    except Exception:
        protected_match_texture_files = None

def _addon_bl_info():
    # bl_info vive en __init__.py (Blender lo exige ahi de forma literal).
    import sys

    pkg = sys.modules.get(__package__ or "ManWTool")
    return getattr(pkg, "bl_info", None) or {}


ADDON_ID = "ManWTool"
DEFAULT_REPO_OWNER = "ManWitoo"
DEFAULT_REPO_NAME = "ManWTool"
DEFAULT_ADDON_FILE = "ManWTool/__init__.py"
EXPECTED_ZIP_ROOT = "ManWTool/"

_preview_col = None

UPDATER_LOCK = threading.Lock()

TRANSFORM_WARNING_STATE = {
    "affected_count": 0,
    "affected_names": [],
    "negative_scale_count": 0,
    "inverted_normals_count": 0,
}

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

LICENSE_CACHE_FILE = "license_cache.json"
LOG_FILE_NAME = "manwtool.log"
LOG_FILE_MAX_BYTES = 1024 * 1024


def updater_state_update(values):
    with UPDATER_LOCK:
        UPDATER_STATE.update(values)


def updater_state_get(key, default=None):
    with UPDATER_LOCK:
        return UPDATER_STATE.get(key, default)


TEXTURE_RULES = {
    "BASE_COLOR": ("basecolor", "base_color", "albedo", "diffuse", "color", "col"),
    "NORMAL": ("normal", "nor", "nrm"),
    "ROUGHNESS": ("roughness", "rough"),
    "METALLIC": ("metallic", "metalness", "metal"),
    "AO": ("ao", "ambientocclusion", "occlusion"),
    "EMISSION": ("emission", "emissive"),
    "OPACITY": ("opacity", "alpha", "transparency"),
}

def current_version_str():
    return ".".join(map(str, _addon_bl_info().get("version", (0, 0, 0))))


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


def build_rename_name(props):
    mode = (getattr(props, "rename_affix_mode", "PREFIX") or "PREFIX").upper()
    prefix = (getattr(props, "rename_prefix", "") or "").strip()
    base = (getattr(props, "rename_base", "") or "").strip()
    suffix = (getattr(props, "rename_suffix", "") or "").strip()

    if mode == "SUFFIX":
        return f"{base}{suffix}"
    if mode == "BOTH":
        return f"{prefix}{base}{suffix}"
    return f"{prefix}{base}"


def get_addon_prefs():
    try:
        addon = bpy.context.preferences.addons.get(ADDON_ID)
        return addon.preferences if addon else None
    except Exception:
        return None


def get_license_cache_path():
    cache_dir = bpy.utils.user_resource("CONFIG", path="manwtool", create=True)
    if not cache_dir:
        raise RuntimeError("No se pudo resolver la carpeta de configuracion del addon.")
    return os.path.join(cache_dir, LICENSE_CACHE_FILE)


def get_machine_fingerprint():
    raw = "|".join(
        [
            platform.system(),
            platform.release(),
            platform.machine(),
            hex(uuid.getnode()),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def load_license_cache():
    path = get_license_cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log_exception("No se pudo leer la cache de licencia", exc)
        return {}


def save_license_cache(data):
    path = get_license_cache_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=True)
    return path


def clear_license_cache():
    path = get_license_cache_path()
    if os.path.isfile(path):
        os.remove(path)


def apply_license_state_to_prefs(data):
    prefs = get_addon_prefs()
    if not prefs:
        return

    prefs.license_active = bool(data.get("valid"))
    prefs.license_status = data.get("status", tr("state.license.inactive"))
    prefs.license_valid_until = data.get("valid_until", "")
    prefs.license_last_check = data.get("last_check", "")
    prefs.license_hardware_id = data.get("hardware_id", get_machine_fingerprint())


def validate_license_key_format(license_key: str):
    key = (license_key or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9\-]{10,128}", key):
        raise RuntimeError("License key format is not valid." if get_effective_language() == "en" else "La clave de licencia no tiene un formato valido.")
    return key


def validate_license_with_server(email: str, license_key: str, server_url: str, timeout=15):
    machine_id = get_machine_fingerprint()
    payload = json.dumps(
        {
            "addon_id": ADDON_ID,
            "addon_version": current_version_str(),
            "email": (email or "").strip(),
            "license_key": validate_license_key_format(license_key),
            "machine_id": machine_id,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        (server_url or "").strip(),
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"{ADDON_ID}/{current_version_str()} (License Check)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Servidor de licencias respondio {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"No se pudo contactar el servidor de licencias: {exc.reason}") from exc

    valid = bool(data.get("valid"))
    status = data.get("status") or ("Activa" if valid else "Licencia no valida")
    result = {
        "valid": valid,
        "status": status,
        "valid_until": (data.get("valid_until") or "").strip(),
        "last_check": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware_id": machine_id,
        "email": (email or "").strip(),
    }
    save_license_cache(result)
    apply_license_state_to_prefs(result)
    return result


def load_cached_license_into_prefs():
    cached = load_license_cache()
    if cached:
        apply_license_state_to_prefs(cached)
    else:
        apply_license_state_to_prefs(
            {
                "valid": False,
                "status": tr("state.license.inactive"),
                "last_check": "",
                "valid_until": "",
                "hardware_id": get_machine_fingerprint(),
            }
        )


def is_license_active():
    if not REQUIRE_LICENSE:
        return True
    prefs = get_addon_prefs()
    return bool(getattr(prefs, "license_active", False)) if prefs else False


def ensure_license_active(report_fn=None, message=None):
    if is_license_active():
        return True
    if report_fn:
        report_fn({"ERROR"}, message or tr("report.license_required"))
    return False


def is_debug_enabled():
    prefs = get_addon_prefs()
    return bool(getattr(prefs, "debug_logging", False)) if prefs else False


def get_log_file_path():
    try:
        log_dir = bpy.utils.user_resource("CONFIG", path="manwtool", create=True)
        return os.path.join(log_dir, LOG_FILE_NAME) if log_dir else ""
    except Exception:
        return ""


def _write_log_line(line: str):
    path = get_log_file_path()
    if not path:
        return
    try:
        if os.path.isfile(path) and os.path.getsize(path) > LOG_FILE_MAX_BYTES:
            backup = f"{path}.old"
            if os.path.isfile(backup):
                os.remove(backup)
            os.replace(path, backup)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
    except Exception:
        pass


def log_info(message: str):
    print(f"[{ADDON_ID}] {message}")
    _write_log_line(message)


def log_debug(message: str):
    if is_debug_enabled():
        log_info(f"DEBUG | {message}")


def log_exception(message: str, exc: Exception):
    log_info(f"ERROR | {message}: {exc}")
    if is_debug_enabled():
        traceback.print_exc()


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


def validate_release_zip(zip_path: str, expected_version: str = ""):
    if not os.path.isfile(zip_path):
        raise RuntimeError("El ZIP descargado no existe.")

    if os.path.getsize(zip_path) > 150 * 1024 * 1024:
        raise RuntimeError("El ZIP descargado es demasiado grande para ser una release valida.")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if not names:
            raise RuntimeError("El ZIP descargado esta vacio.")

        init_matches = [name for name in names if name.endswith("ManWTool/__init__.py")]
        if not init_matches and "ManWTool.py" in names:
            init_matches = ["ManWTool.py"]
        if not init_matches:
            raise RuntimeError("El ZIP no contiene un addon ManWTool valido.")

        init_member = init_matches[0]
        source_text = zf.read(init_member).decode("utf-8", errors="replace")
        version_tuple = version_tuple_from_source_text(source_text)
        version_label = ".".join(map(str, version_tuple))
        if expected_version and version_tuple_from_any(expected_version) != version_tuple:
            raise RuntimeError(
                f"La version descargada ({version_label}) no coincide con la esperada ({expected_version})."
            )
        return {
            "version": version_label,
            "addon_init_member": init_member,
        }


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
    release_candidate = None

    try:
        release_data = http_get_json(github_latest_release_url(owner, repo))
        tag = (release_data.get("tag_name") or release_data.get("name") or "").strip()
        if not tag:
            raise RuntimeError("No se encontro una version valida en GitHub.")

        download_url = select_best_zip_asset(release_data, asset_filter)
        if not download_url:
            raise RuntimeError("No se encontro un asset ZIP descargable en la release.")
        release_candidate = {
            "version_tuple": version_tuple_from_any(tag),
            "version_label": tag,
            "download_url": download_url,
            "download_kind": "ZIP",
            "release_html_url": (release_data.get("html_url") or "").strip(),
        }
    except Exception as exc:
        release_error = str(exc)
        log_exception("Fallo comprobando release de GitHub", exc)

    selected = release_candidate

    if selected:
        updater_state_update(
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

    updater_state_update(
        {
            "done": True,
            "ok": False,
            "latest_version": "",
            "download_url": "",
            "download_kind": "ZIP",
            "release_html_url": "",
            "error": release_error or "No se pudo comprobar GitHub.",
        }
    )


def start_update_check(force=False):
    prefs = get_addon_prefs()
    if not prefs:
        return

    owner = (prefs.repo_owner or "").strip()
    repo = (prefs.repo_name or "").strip()
    if not owner or not repo:
        prefs.last_update_error = tr("report.update_config_missing")
        return

    now = time.time()
    interval_sec = max(1, int(prefs.check_interval_days)) * 86400
    if not force:
        if not prefs.auto_check_updates:
            return
        if prefs.last_check_time > 0 and (now - prefs.last_check_time) < interval_sec:
            return

    if updater_state_get("checking"):
        return

    updater_state_update(
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
    updater_state_update({"thread": thread})
    thread.start()
    if not bpy.app.timers.is_registered(poll_update_check_timer):
        bpy.app.timers.register(poll_update_check_timer, first_interval=0.2)


def poll_update_check_timer():
    prefs = get_addon_prefs()
    if not prefs:
        updater_state_update({"checking": False})
        return None

    if not updater_state_get("done"):
        return 0.2

    prefs.last_check_time = time.time()
    if updater_state_get("ok"):
        latest_tag = updater_state_get("latest_version", "")
        prefs.latest_version = latest_tag
        prefs.latest_download_url = updater_state_get("download_url", "")
        prefs.latest_download_kind = updater_state_get("download_kind", "ZIP")
        prefs.latest_release_url = updater_state_get("release_html_url", "")
        prefs.last_update_error = ""
        prefs.update_available = version_tuple_from_any(latest_tag) > tuple(_addon_bl_info().get("version", (0, 0, 0)))
        if prefs.update_available and prefs.last_notified_version != prefs.latest_version:
            prefs.last_notified_version = prefs.latest_version
            try:
                bpy.ops.manwtool.update_popup("INVOKE_DEFAULT")
            except Exception:
                pass
    else:
        prefs.last_update_error = updater_state_get("error", tr("report.unknown_error"))
        prefs.update_available = False

    updater_state_update({"checking": False})
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
            log_debug("No se pudo limpiar el logo anterior.")

    path = bpy.path.abspath(prefs.logo_path) if prefs.logo_path else ""
    if not path or not os.path.isfile(path):
        return

    try:
        _preview_col.load(key, path, "IMAGE")
    except Exception:
        log_debug(f"No se pudo cargar el logo desde {path}.")


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
            log_debug("No se pudo liberar la preview collection.")
        _preview_col = None


def collection_has_child(parent, child_name):
    return parent.children.get(child_name) is not None


def ensure_valid_export_dir(base_dir, report_fn):
    if not base_dir:
        report_fn({"ERROR"}, tr("report.invalid_export_path"))
        return None
    base_dir = bpy.path.abspath(base_dir)
    if not os.path.isdir(base_dir):
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            report_fn({"ERROR"}, tr("report.cannot_use_folder"))
            return None
    return base_dir


def get_mesh_objects_from_selection(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def get_empty_objects_from_selection(context):
    return [obj for obj in context.selected_objects if obj.type == "EMPTY"]


def get_visible_mesh_objects(context):
    return [obj for obj in context.view_layer.objects if obj.visible_get() and obj.type == "MESH"]


def get_visible_empty_objects(context):
    return [obj for obj in context.view_layer.objects if obj.visible_get() and obj.type == "EMPTY"]


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

    log_debug(f"Informe de validacion escrito en {report_path}")
    return report_path


def ensure_object_mode():
    obj = bpy.context.active_object
    if obj and obj.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def count_multi_user_meshes(objects):
    count = 0
    for obj in objects:
        if obj and obj.type == "MESH" and obj.data and obj.data.users > 1:
            count += 1
    return count


def has_negative_scale(obj):
    return any(value < 0.0 for value in getattr(obj, "scale", (0.0, 0.0, 0.0)))


def get_negative_scale_mesh_objects(objects):
    return [obj for obj in objects if obj and obj.type == "MESH" and has_negative_scale(obj)]


def is_closed_manifold_mesh(obj):
    if obj is None or obj.type != "MESH" or obj.data is None:
        return False
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        if not bm.faces:
            return False
        return all(edge.is_manifold for edge in bm.edges)
    finally:
        bm.free()


def has_inverted_normals_closed_mesh(obj):
    if not is_closed_manifold_mesh(obj):
        return False
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        if not bm.faces:
            return False
        volume = bm.calc_volume(signed=True)
        return volume < 0.0
    except Exception:
        return False
    finally:
        bm.free()


def get_inverted_normals_mesh_objects(objects):
    return [obj for obj in objects if obj and obj.type == "MESH" and has_inverted_normals_closed_mesh(obj)]


def recalculate_normals_for_objects(context, objects):
    mesh_objects = [obj for obj in objects if obj and obj.name in bpy.data.objects and obj.type == "MESH"]
    if not mesh_objects:
        return {"processed": 0, "failed": 0}

    ensure_object_mode()
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = list(context.selected_objects)
    processed = 0
    failed = 0

    try:
        for obj in mesh_objects:
            try:
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_all(action="SELECT")
                bpy.ops.mesh.normals_make_consistent(inside=False)
                bpy.ops.object.mode_set(mode="OBJECT")
                processed += 1
            except Exception as exc:
                failed += 1
                try:
                    bpy.ops.object.mode_set(mode="OBJECT")
                except Exception:
                    pass
                log_exception(f"Fallo recalculando normales en {getattr(obj, 'name', '<desconocido>')}", exc)
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in prev_selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if prev_active and prev_active.name in bpy.data.objects:
            view_layer.objects.active = prev_active

    return {"processed": processed, "failed": failed}


def run_apply_selected_transforms(context, report_fn, recalc_suspect_normals=False):
    selected_meshes = get_mesh_objects_from_selection(context)
    selected_empties = get_empty_objects_from_selection(context)
    selected_objects = selected_meshes + selected_empties
    if not selected_objects:
        report_fn({"ERROR"}, tr("report.no_mesh_or_empty_selected"))
        return {"CANCELLED"}

    negative_scale_meshes = get_negative_scale_mesh_objects(selected_meshes)
    inverted_normals_meshes = get_inverted_normals_mesh_objects(selected_meshes)
    suspect_meshes = []
    for obj in negative_scale_meshes + inverted_normals_meshes:
        if obj not in suspect_meshes:
            suspect_meshes.append(obj)

    result = apply_transformations_to_objects(
        context,
        selected_objects,
        apply_location=True,
        apply_rotation=True,
        apply_scale=True,
        make_single_user=True,
    )

    if result["processed"] == 0:
        report_fn({"ERROR"}, tr("report.transforms_failed"))
        return {"CANCELLED"}

    normals_result = {"processed": 0, "failed": 0}
    if recalc_suspect_normals and suspect_meshes:
        normals_result = recalculate_normals_for_objects(context, suspect_meshes)

    level = {"WARNING"} if result["failed"] or normals_result["failed"] else {"INFO"}
    message = tr(
        "report.transforms_applied",
        processed=result["processed"],
        single_user=result["single_user_made"],
        failed=result["failed"],
    )
    if recalc_suspect_normals and suspect_meshes:
        message += " | " + tr(
            "report.normals_recalculated",
            processed=normals_result["processed"],
            failed=normals_result["failed"],
        )
    report_fn(level, message)
    return {"FINISHED"}


def apply_transformations_to_objects(
    context,
    objects,
    *,
    apply_location=True,
    apply_rotation=True,
    apply_scale=True,
    set_origin=False,
    move_to_origin=False,
    reset_rotation_after=False,
    make_single_user=False,
):
    if not objects:
        return {"processed": 0, "single_user_made": 0, "failed": 0}

    ensure_object_mode()
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = list(context.selected_objects)
    processed = 0
    single_user_made = 0
    failed = 0

    try:
        for obj in objects:
            if obj is None or obj.name not in bpy.data.objects or obj.type not in {"MESH", "EMPTY"}:
                continue

            try:
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                view_layer.objects.active = obj
                if obj.type == "MESH" and make_single_user and obj.data and obj.data.users > 1:
                    obj.data = obj.data.copy()
                    single_user_made += 1

                bpy.ops.object.transform_apply(
                    location=bool(apply_location),
                    rotation=bool(apply_rotation),
                    scale=bool(apply_scale),
                )
                if set_origin:
                    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
                if move_to_origin:
                    obj.location = (0.0, 0.0, 0.0)
                if reset_rotation_after:
                    obj.rotation_euler = (0.0, 0.0, 0.0)
                processed += 1
            except Exception as exc:
                failed += 1
                log_exception(f"Fallo aplicando transformaciones a {getattr(obj, 'name', '<desconocido>')}", exc)
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in prev_selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if prev_active and prev_active.name in bpy.data.objects:
            view_layer.objects.active = prev_active

    return {
        "processed": processed,
        "single_user_made": single_user_made,
        "failed": failed,
    }


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


def export_mesh_object_to_fbx(context, src, base_dir, report_fn, export_settings=None):
    if src is None:
        report_fn({"ERROR"}, "No object to export." if get_effective_language() == "en" else "No hay objeto para exportar.")
        return False
    if src.type != "MESH":
        report_fn({"ERROR"}, f"{src.name} is not a MESH." if get_effective_language() == "en" else f"{src.name} no es un MESH.")
        return False

    base_dir = ensure_valid_export_dir(base_dir, report_fn)
    if not base_dir:
        return False

    export_name = clean_export_name(src.name)
    export_dir = os.path.join(base_dir, export_name)
    try:
        os.makedirs(export_dir, exist_ok=True)
    except Exception as exc:
        report_fn(
            {"ERROR"},
            (
                f"Could not prepare export folder for {src.name}: {exc}"
                if get_effective_language() == "en"
                else f"No se pudo preparar la carpeta de exportacion para {src.name}: {exc}"
            ),
        )
        log_exception(f"No se pudo crear la carpeta de exportacion {export_dir}", exc)
        return False
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

    settings = export_settings or get_export_settings_for_props(context.scene.manwtool_props)

    try:
        apply_export_prep_to_object(context, tmp_obj)
        bpy.ops.object.select_all(action="DESELECT")
        tmp_obj.select_set(True)
        context.view_layer.objects.active = tmp_obj
        bpy.ops.export_scene.fbx(
            filepath=final_fbx_path,
            use_selection=True,
            object_types={"MESH"},
            apply_unit_scale=bool(settings["apply_unit_scale"]),
            axis_forward=settings["axis_forward"],
            axis_up=settings["axis_up"],
            add_leaf_bones=False,
            use_mesh_modifiers=bool(settings["use_mesh_modifiers"]),
        )
    except Exception as exc:
        report_fn(
            {"ERROR"},
            f"Error exporting {src.name}: {exc}" if get_effective_language() == "en" else f"Error exportando {src.name}: {exc}",
        )
        log_exception(f"Error exportando {src.name}", exc)
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

    report_fn({"INFO"}, f"Exported: {final_fbx_path}" if get_effective_language() == "en" else f"Exportado: {final_fbx_path}")
    return True


_TEXTURE_ALIAS_INDEX = tuple(
    (alias, map_type)
    for map_type, aliases in TEXTURE_RULES.items()
    for alias in sorted(aliases, key=len, reverse=True)
)

_MATERIALS_DIR_CACHE = {"dir": None, "mtime": None, "files": ()}


def _list_material_files(materials_dir: str):
    try:
        mtime = os.path.getmtime(materials_dir)
    except OSError:
        return ()
    if _MATERIALS_DIR_CACHE["dir"] == materials_dir and _MATERIALS_DIR_CACHE["mtime"] == mtime:
        return _MATERIALS_DIR_CACHE["files"]
    files = tuple(
        entry.path
        for entry in os.scandir(materials_dir)
        if entry.is_file()
    )
    _MATERIALS_DIR_CACHE.update({"dir": materials_dir, "mtime": mtime, "files": files})
    return files


def find_matching_textures(material_name: str, obj_name: str, materials_dir: str):
    if not os.path.isdir(materials_dir):
        return {}

    normalized_targets = {normalize_name(material_name), normalize_name(clean_export_name(obj_name))}
    files = list(_list_material_files(materials_dir))

    if protected_match_texture_files is not None:
        try:
            return protected_match_texture_files(files, tuple(normalized_targets), TEXTURE_RULES)
        except Exception as exc:
            log_debug(f"Fallo el modulo protegido, usando fallback Python: {exc}")

    matched = {}
    for path in files:
        if len(matched) == len(TEXTURE_RULES):
            break
        base_name = normalize_name(os.path.splitext(os.path.basename(path))[0])
        if not any(token and token in base_name for token in normalized_targets):
            continue
        for alias, map_type in _TEXTURE_ALIAS_INDEX:
            if map_type in matched:
                continue
            if alias in base_name:
                matched[map_type] = path
                break
    return matched


def load_image(image_path, colorspace="sRGB"):
    image = bpy.data.images.load(image_path, check_existing=True)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        log_debug(f"No se pudo asignar el colorspace {colorspace} a {image_path}.")
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
            log_debug(f"No se pudo eliminar un nodo de textura previo en {material.name}.")


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
    result = apply_transformations_to_objects(
        context,
        objects,
        apply_location=False,
        apply_rotation=bool(reset_rotation),
        apply_scale=bool(apply_scale),
        set_origin=True,
        move_to_origin=bool(move_to_origin),
        reset_rotation_after=bool(reset_rotation),
        make_single_user=True,
    )
    return result["processed"]


def active_obj_status(context):
    obj = context.active_object
    if obj is None:
        return (tr("ui.summary_status.none"), "ERROR", "ERROR")
    if obj.type != "MESH":
        if obj.type == "EMPTY":
            return (tr("ui.summary_status.empty", name=obj.name), "WARNING", "ERROR")
        return (tr("ui.summary_status.other", name=obj.name), "WARNING", "ERROR")
    return (tr("ui.summary_status.mesh", name=obj.name), "INFO", "MESH_CUBE")
