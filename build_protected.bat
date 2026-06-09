@echo off
py -m pip install cython setuptools wheel
py setup_protected.py build_ext --inplace
