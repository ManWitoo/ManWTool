import bpy

from .manwtool_i18n import tr


COLLECTION_TARGET_SUFFIXES = {
    "HIGH": "_High",
    "LOW": "_Low",
    "REFERENCE": "_Reference",
}

COLLECTION_COLOR_TAGS = {
    "HIGH": "COLOR_01",
    "LOW": "COLOR_03",
    "REFERENCE": "COLOR_05",
}

VALID_COLLECTION_SUFFIXES = tuple(COLLECTION_TARGET_SUFFIXES.values())


def get_collection_target_label(target):
    mapping = {
        "HIGH": tr("collection.high"),
        "LOW": tr("collection.low"),
        "REFERENCE": tr("collection.reference"),
    }
    return mapping.get(target, target)


def get_collection_target_items(_self=None, _context=None):
    return [
        ("HIGH", tr("collection.high"), tr("collection.desc.high")),
        ("LOW", tr("collection.low"), tr("collection.desc.low")),
        ("REFERENCE", tr("collection.reference"), tr("collection.desc.reference")),
    ]


COLLECTION_TARGET_ITEMS = [
    ("HIGH", "High", "Move to the High collection"),
    ("LOW", "Low", "Move to the Low collection"),
    ("REFERENCE", "Reference", "Move to the Reference collection"),
]


def get_collection_structure_names(base_name: str):
    base = (base_name or "").strip() or "Asset"
    return {
        "ROOT": base,
        "HIGH": f"{base}{COLLECTION_TARGET_SUFFIXES['HIGH']}",
        "LOW": f"{base}{COLLECTION_TARGET_SUFFIXES['LOW']}",
        "REFERENCE": f"{base}{COLLECTION_TARGET_SUFFIXES['REFERENCE']}",
    }


def ensure_collection_structure(scene, base_name: str):
    names = get_collection_structure_names(base_name)
    root_col = bpy.data.collections.get(names["ROOT"])
    if root_col is None:
        root_col = bpy.data.collections.new(names["ROOT"])

    if scene.collection.children.get(root_col.name) is None:
        scene.collection.children.link(root_col)

    collections = {"ROOT": root_col}
    for target, child_name in names.items():
        if target == "ROOT":
            continue
        col = bpy.data.collections.get(child_name)
        if col is None:
            col = bpy.data.collections.new(child_name)
        if root_col.children.get(col.name) is None:
            root_col.children.link(col)
        col.color_tag = COLLECTION_COLOR_TAGS[target]
        collections[target] = col
    return collections


def move_object_to_collection(obj, target_collection, unlink_existing=True):
    if obj is None or target_collection is None:
        return False

    if unlink_existing:
        for collection in list(obj.users_collection):
            try:
                collection.objects.unlink(obj)
            except Exception:
                pass

    if target_collection.objects.get(obj.name) is None:
        target_collection.objects.link(obj)
    return True


def move_objects_to_target_collection(scene, objects, base_name: str, target: str):
    structure = ensure_collection_structure(scene, base_name)
    target_collection = structure.get(target)
    moved = 0
    for obj in objects:
        if move_object_to_collection(obj, target_collection, unlink_existing=True):
            moved += 1
    return moved


def infer_collection_target_from_name(name: str, default_target="HIGH"):
    normalized = (name or "").lower()
    if "reference" in normalized or "_ref" in normalized or " ref" in normalized:
        return "REFERENCE"
    if "low" in normalized:
        return "LOW"
    if "high" in normalized:
        return "HIGH"
    return default_target


def auto_organize_objects(scene, objects, base_name: str, default_target="HIGH"):
    structure = ensure_collection_structure(scene, base_name)
    summary = {"HIGH": 0, "LOW": 0, "REFERENCE": 0, "TOTAL": 0}

    for obj in objects:
        target = infer_collection_target_from_name(obj.name, default_target=default_target)
        if move_object_to_collection(obj, structure.get(target), unlink_existing=True):
            summary[target] += 1
            summary["TOTAL"] += 1
    return summary
