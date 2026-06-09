# Release Checklist

1. Actualizar `bl_info["version"]` en `ManWTool.py`
2. Revisar `README.md`
3. Compilar modulo protegido si aplica: `build_protected.bat`
4. Ejecutar `py build_addon.py`
4. Probar en Blender:
   - Registro del addon
   - Export FBX individual
   - Export FBX multiple
   - Import FBX con materiales
   - Comprobacion de updates
   - Activacion de licencia contra el servidor
5. Levantar `license_server/app.py` y comprobar una activacion demo
6. Subir `ManWTool.zip` como asset de GitHub Release
7. Crear tag de version
