from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parent
PACKAGE_DIR = ROOT / "ManWTool"
OUTPUT_ZIP = ROOT / "ManWTool.zip"


def build_zip():
    if not PACKAGE_DIR.is_dir():
        raise SystemExit(
            f"No existe el paquete del addon: {PACKAGE_DIR}. "
            "Ejecuta primero sync_commercial.py desde ConstruccionManwTool."
        )

    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE_DIR.rglob("*.py")):
            zf.write(path, path.relative_to(ROOT).as_posix())

        # Modulo protegido compilado (puede estar en la raiz o dentro del paquete)
        compiled = sorted(ROOT.glob("manwtool_protected*.pyd")) + sorted(ROOT.glob("manwtool_protected*.so"))
        compiled += sorted(PACKAGE_DIR.glob("manwtool_protected*.pyd")) + sorted(PACKAGE_DIR.glob("manwtool_protected*.so"))
        seen = set()
        for binary in compiled:
            if binary.name in seen:
                continue
            seen.add(binary.name)
            zf.write(binary, f"ManWTool/{binary.name}")

        for extra_name in ("README.md", "LICENSE", "RELEASE_CHECKLIST.md", "COMMERCIALIZATION_NOTES.md"):
            extra_path = ROOT / extra_name
            if extra_path.is_file():
                zf.write(extra_path, extra_name)

    print(f"ZIP generado: {OUTPUT_ZIP}")


if __name__ == "__main__":
    build_zip()
