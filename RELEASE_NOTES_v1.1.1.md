# ManWTool v1.1.1

Hotfix: en v1.1.0 el addon no aparecia en la lista de addons de Blender porque `bl_info` no estaba definido literalmente en `__init__.py` (Blender lo lee parseando ese archivo, sin importarlo). Ahora `bl_info` vive en `__init__.py` y el resto del codigo lo consulta en runtime.

Si vienes de v1.0.x recuerda desinstalar antes la version antigua de archivo unico.
