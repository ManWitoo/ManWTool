from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
ADDON_FILE = ROOT / "ManWTool.py"
OUTPUT_ZIP = ROOT / "ManWTool.zip"


def build_zip():
    if not ADDON_FILE.is_file():
        raise SystemExit(f"No existe el addon: {ADDON_FILE}")

    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(ADDON_FILE, "ManWTool.py")
        for compiled in sorted(ROOT.glob("manwtool_protected*.pyd")) + sorted(ROOT.glob("manwtool_protected*.so")):
            zf.write(compiled, compiled.name)
        for extra_name in ("README.md", "LICENSE", "RELEASE_CHECKLIST.md", "COMMERCIALIZATION_NOTES.md"):
            extra_path = ROOT / extra_name
            if extra_path.is_file():
                zf.write(extra_path, extra_name)

    print(f"ZIP generado: {OUTPUT_ZIP}")


if __name__ == "__main__":
    build_zip()
