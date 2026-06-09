# ManWTool

Addon para Blender orientado a acelerar tareas de pipeline de assets: organización de colecciones, naming consistente, exportación FBX y validación automática antes de exportar.

## Qué hace

ManWTool centraliza varias tareas repetitivas de producción en una sola herramienta:

- Crea estructura de colecciones para assets
- Mueve y organiza la selección automáticamente en `High`, `Low` y `Reference`
- Renombra objeto, mesh data y material con una sola acción
- Exporta FBX generando una carpeta por objeto
- Usa presets de export para `Unreal`, `Unity`, `Highpoly Bake`, `Lowpoly Game` y `Custom`
- Aplica transformaciones en lote aunque haya meshes compartidos
- Avisa antes de aplicar transformaciones si detecta meshes con escala negativa
- Detecta meshes cerradas con normales potencialmente invertidas
- Recalcula normales automáticamente durante la aplicación de transformaciones (opcional)
- Guarda la última carpeta para `ReExport`
- Comprueba actualizaciones desde GitHub
- Valida automáticamente el asset al exportar
- Genera un informe `.txt` con incidencias del export

## Apartados del addon

### 1. Colecciones

Permite crear una estructura base para trabajar un asset:

- `Asset`
- `Asset_High`
- `Asset_Low`
- `Asset_Reference`

Esto ayuda a mantener una organización estable para modelado, baking y export.

También permite:

- Mover la selección a la colección objetivo con un click
- Autoorganizar por nombre detectando `high`, `low` o `reference`

### 2. Renombrado

Permite aplicar naming consistente al objeto activo:

- Cambia el nombre del objeto
- Cambia el nombre de la mesh data
- Crea o asigna un material con el mismo nombre

Pensado para evitar errores de naming y acelerar la preparación del asset.

### 3. Export

El export:

- Trabaja sobre una copia temporal
- Bakea modificadores
- Aplica rotación y escala
- Centra el origen
- Mueve la copia a `0,0,0`
- Crea una carpeta por objeto
- Exporta un `.fbx` dentro de esa carpeta

También incluye `ReExport`, usando la última ruta guardada.

Presets de export disponibles:

- `Unreal`
- `Unity`
- `Highpoly Bake`
- `Lowpoly Game`
- `Custom`

### 4. Transformaciones en lote

Incluye un apartado específico para:

- Seleccionar muchas geometrías
- Convertir automáticamente a `single-user` los meshes compartidos cuando haga falta
- Aplicar `location`, `rotation` y `scale` en lote
- Recibir aviso previo si se detectan meshes con escala negativa
- Recalcular normales automáticamente si se activa la opción

Esto evita el error de Blender al intentar aplicar transformaciones sobre datos compartidos.

### 5. Asset Validator automático

Al exportar, la validación se ejecuta sola antes de generar el FBX.

Actualmente revisa:

- `Transforms`
  - Location distinta de `0,0,0`
  - Rotación distinta de `0,0,0`
  - Escala distinta de `1,1,1`
- `Duplicados`
  - Nombres que colisionan tras limpiar sufijos como `.001`
- `Colecciones`
  - Objeto sin colección
  - Objeto en varias colecciones
  - Objeto fuera de las colecciones esperadas `_High`, `_Low`, `_Reference`
- `Normales`
  - Meshes cerradas con normales potencialmente invertidas

### 6. Informe automático

Cada export genera un informe `.txt` en la carpeta de exportación con:

- Resumen general
- Objetos revisados
- Incidencias detectadas
- Detalle por objeto

Esto permite revisar rápidamente si el asset está limpio antes de seguir con Substance, Unreal u otro flujo.

### 7. Auto update por GitHub

El addon puede:

- Comprobar si existe una release nueva
- Abrir la release publicada
- Instalar la actualización desde Blender solo si activas la opción de instalación directa (desactivada por defecto)

### 8. Licencias

El addon incluye una base para activación comercial:

- Email y clave de licencia
- `Hardware ID` local
- Cache local de licencia
- Validación contra un `license server` configurable

## Instalación

1. Descarga `ManWTool.zip` desde `Releases`.
2. En Blender ve a `Edit > Preferences > Add-ons > Install`.
3. Selecciona el `.zip`.
4. Activa el addon.

## Ubicación en Blender

`View3D > Sidebar (N) > ManWTool`

## Flujo recomendado

1. Crear estructura de colecciones.
2. Renombrar el asset.
3. Colocar cada objeto en su colección correcta.
4. Exportar.
5. Revisar el informe automático si hay avisos.

## Versión actual

`v1.0.12`

## Preparar releases

1. Ejecuta `py build_addon.py`
2. Si quieres usar el módulo protegido, ejecuta `build_protected.bat`
3. Sube `ManWTool.zip` a GitHub Releases
4. Sigue la checklist de `RELEASE_CHECKLIST.md`

## Roadmap

- Backend real de licencias
- Compilar parte sensible del addon
- Ampliar el validator con reglas opcionales
- Mejorar import y materiales para casos de producción

## Servidor de licencias

Documentación y código del servidor de licencias:

- [LICENSE_SERVER_README.md](LICENSE_SERVER_README.md)
- [license_server/app.py](license_server/app.py)
- [license_server/seed_demo_data.py](license_server/seed_demo_data.py)
