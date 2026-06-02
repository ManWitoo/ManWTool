# cython: language_level=3

def match_texture_files(files, normalized_targets, texture_rules):
    matched = {}
    for path in files:
        base_name = path.replace("\\", "/").split("/")[-1].rsplit(".", 1)[0].lower()
        normalized = "".join(ch for ch in base_name if ch.isalnum())
        if not any(token and token in normalized for token in normalized_targets):
            continue
        for map_type, aliases in texture_rules.items():
            if map_type in matched:
                continue
            for alias in aliases:
                if alias in normalized:
                    matched[map_type] = path
                    break
    return matched
