import bpy

from .manwtool_i18n import tr, yes_no


AXIS_ITEMS = [
    ("X", "X Forward", ""),
    ("Y", "Y Forward", ""),
    ("Z", "Z Forward", ""),
    ("-X", "-X Forward", ""),
    ("-Y", "-Y Forward", ""),
    ("-Z", "-Z Forward", ""),
]

DEFAULT_EXPORT_PRESETS = {
    "UNREAL": {
        "label": "Unreal",
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_unit_scale": True,
        "use_mesh_modifiers": False,
    },
    "UNITY": {
        "label": "Unity",
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_unit_scale": True,
        "use_mesh_modifiers": False,
    },
    "HIGHPOLY": {
        "label": "Highpoly Bake",
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_unit_scale": True,
        "use_mesh_modifiers": True,
    },
    "LOWPOLY": {
        "label": "Lowpoly Game",
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_unit_scale": True,
        "use_mesh_modifiers": False,
    },
}


PRESET_PREFS_FIELDS = {
    "UNREAL": {
        "axis_forward": "unreal_axis_forward",
        "axis_up": "unreal_axis_up",
        "apply_unit_scale": "unreal_apply_unit_scale",
        "use_mesh_modifiers": "unreal_use_mesh_modifiers",
    },
    "UNITY": {
        "axis_forward": "unity_axis_forward",
        "axis_up": "unity_axis_up",
        "apply_unit_scale": "unity_apply_unit_scale",
        "use_mesh_modifiers": "unity_use_mesh_modifiers",
    },
    "HIGHPOLY": {
        "axis_forward": "highpoly_axis_forward",
        "axis_up": "highpoly_axis_up",
        "apply_unit_scale": "highpoly_apply_unit_scale",
        "use_mesh_modifiers": "highpoly_use_mesh_modifiers",
    },
    "LOWPOLY": {
        "axis_forward": "lowpoly_axis_forward",
        "axis_up": "lowpoly_axis_up",
        "apply_unit_scale": "lowpoly_apply_unit_scale",
        "use_mesh_modifiers": "lowpoly_use_mesh_modifiers",
    },
    "CUSTOM": {
        "axis_forward": "custom_axis_forward",
        "axis_up": "custom_axis_up",
        "apply_unit_scale": "custom_apply_unit_scale",
        "use_mesh_modifiers": "custom_use_mesh_modifiers",
    },
}


def get_addon_preferences():
    context = getattr(bpy, "context", None)
    preferences = getattr(context, "preferences", None)
    addons = getattr(preferences, "addons", None)
    if addons is None:
        return None

    for addon_id in ("ManWTool", ((__package__ or "").split(".")[0] if __package__ else "")):
        if not addon_id:
            continue
        addon = addons.get(addon_id)
        if addon and addon.preferences:
            return addon.preferences
    return None


def get_export_preset_items(_self=None, _context=None):
    return [
        ("UNREAL", "Unreal", tr("preset.unreal.desc")),
        ("UNITY", "Unity", tr("preset.unity.desc")),
        ("HIGHPOLY", "Highpoly Bake", tr("preset.highpoly.desc")),
        ("LOWPOLY", "Lowpoly Game", tr("preset.lowpoly.desc")),
        ("CUSTOM", "Custom", tr("preset.custom.desc")),
    ]


EXPORT_PRESET_ITEMS = [
    ("UNREAL", "Unreal", "Export preset designed for Unreal"),
    ("UNITY", "Unity", "Export preset designed for Unity"),
    ("HIGHPOLY", "Highpoly Bake", "Uses modifiers to export a clean highpoly"),
    ("LOWPOLY", "Lowpoly Game", "Lowpoly export for games"),
    ("CUSTOM", "Custom", "Manual configuration"),
]


def get_preset_pref_fields(preset):
    return PRESET_PREFS_FIELDS.get((preset or "UNREAL").strip().upper(), PRESET_PREFS_FIELDS["UNREAL"])


def get_export_settings_for_preset(preset, prefs=None):
    preset_id = (preset or "UNREAL").strip().upper()
    base = dict(DEFAULT_EXPORT_PRESETS.get(preset_id, DEFAULT_EXPORT_PRESETS["UNREAL"]))
    pref_fields = get_preset_pref_fields(preset_id)
    prefs = prefs or get_addon_preferences()

    if prefs:
        base["axis_forward"] = getattr(prefs, pref_fields["axis_forward"], base["axis_forward"])
        base["axis_up"] = getattr(prefs, pref_fields["axis_up"], base["axis_up"])
        base["apply_unit_scale"] = bool(getattr(prefs, pref_fields["apply_unit_scale"], base["apply_unit_scale"]))
        base["use_mesh_modifiers"] = bool(getattr(prefs, pref_fields["use_mesh_modifiers"], base["use_mesh_modifiers"]))

    return base


def get_export_settings_for_props(props):
    preset = (getattr(props, "export_preset", "UNREAL") or "UNREAL").strip().upper()
    return get_export_settings_for_preset(preset)


def reset_export_preset_to_defaults(preset, prefs=None):
    preset_id = (preset or "UNREAL").strip().upper()
    defaults = DEFAULT_EXPORT_PRESETS.get(preset_id, DEFAULT_EXPORT_PRESETS["UNREAL"])
    pref_fields = get_preset_pref_fields(preset_id)
    prefs = prefs or get_addon_preferences()
    if not prefs:
        return False

    setattr(prefs, pref_fields["axis_forward"], defaults["axis_forward"])
    setattr(prefs, pref_fields["axis_up"], defaults["axis_up"])
    setattr(prefs, pref_fields["apply_unit_scale"], defaults["apply_unit_scale"])
    setattr(prefs, pref_fields["use_mesh_modifiers"], defaults["use_mesh_modifiers"])
    return True


def format_export_settings_lines(settings):
    return [
        f"Preset: {settings['label']}",
        f"Axis: {settings['axis_forward']} / {settings['axis_up']}",
        tr("ui.export.apply_unit_scale", value=yes_no(settings["apply_unit_scale"])),
        tr("ui.export.use_mesh_modifiers", value=yes_no(settings["use_mesh_modifiers"])),
    ]
