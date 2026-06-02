from pathlib import Path

from setuptools import Extension, setup

try:
    from Cython.Build import cythonize
except ImportError as exc:
    raise SystemExit("Instala Cython primero: py -m pip install cython setuptools wheel") from exc


ROOT = Path(__file__).resolve().parent


extensions = [
    Extension(
        "manwtool_protected",
        [str(ROOT / "manwtool_protected.pyx")],
    )
]


setup(
    name="manwtool_protected",
    ext_modules=cythonize(extensions, compiler_directives={"language_level": "3"}),
)
