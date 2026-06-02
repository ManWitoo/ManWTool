# ManWTool

Addon para Blender orientado a acelerar tareas de pipeline de assets: organizacion de colecciones, naming consistente, exportacion FBX y validacion automatica antes de exportar.

## Que hace

ManWTool centraliza varias tareas repetitivas de produccion en una sola herramienta:

- crea estructura de colecciones para assets
- mueve y organiza seleccion automaticamente en `High`, `Low` y `Reference`
- renombra objeto, mesh data y material con una sola accion
- exporta FBX generando una carpeta por objeto
- usa presets de export para `Unreal`, `Unity`, `Highpoly Bake`, `Lowpoly Game` y `Custom`
- aplica transformaciones en lote aunque haya meshes compartidos
- guarda la ultima carpeta para `ReExport`
- comprueba actualizaciones desde GitHub
- valida automaticamente el asset al exportar
- genera un informe `.txt` con incidencias del export

## Apartados del addon

### 1. Colecciones

Permite crear una estructura base para trabajar un asset:

- `Asset`
- `Asset_High`
- `Asset_Low`
- `Asset_Reference`

Esto ayuda a mantener una organizacion estable para modelado, baking y export.

Ahora tambien permite:

- mover la seleccion a la coleccion objetivo con un click
- autoorganizar por nombre detectando `high`, `low` o `reference`

### 2. Renombrado

Permite aplicar naming consistente al objeto activo:

- cambia el nombre del objeto
- cambia el nombre de la mesh data
- crea o asigna un material con el mismo nombre

Pensado para evitar errores de naming y acelerar la preparacion del asset.

### 3. Export

El export:

- trabaja sobre una copia temporal
- bakea modificadores
- aplica rotacion y escala
- centra el origen
- mueve la copia a `0,0,0`
- crea una carpeta por objeto
- exporta un `.fbx` dentro de esa carpeta

Tambien incluye `ReExport`, usando la ultima ruta guardada.

Ahora incluye presets de export para:

- `Unreal`
- `Unity`
- `Highpoly Bake`
- `Lowpoly Game`
- `Custom`

### 4. Transformaciones en lote

Incluye un apartado especifico para:

- seleccionar muchas geometrias
- convertir automaticamente a `single-user` los meshes compartidos cuando haga falta
- aplicar `location`, `rotation` y `scale` en lote

Esto evita el error de Blender al intentar aplicar transformaciones sobre datos compartidos.

### 5. Asset Validator automatico

Al darle a export no aparece un boton nuevo: la validacion se ejecuta sola.

Actualmente revisa:

- `Transforms`
  - location distinta de `0,0,0`
  - rotacion distinta de `0,0,0`
  - escala distinta de `1,1,1`
- `Duplicados`
  - nombres que colisionan tras limpiar sufijos como `.001`
- `Colecciones`
  - objeto sin coleccion
  - objeto en varias colecciones
  - objeto fuera de las colecciones esperadas `_High`, `_Low`, `_Reference`

### 6. Informe automatico

Cada export genera un informe `.txt` en la carpeta de exportacion con:

- resumen general
- objetos revisados
- incidencias detectadas
- detalle por objeto

Esto permite revisar rapidamente si el asset esta limpio antes de seguir con Substance, Unreal u otro flujo.

### 7. Auto update por GitHub

El addon puede:

- comprobar si existe una release nueva
- abrir la release publicada
- instalar la actualizacion desde Blender solo si activas la opcion de instalacion directa

### 8. Licencias

El addon ya incluye una base para activacion comercial:

- email y clave de licencia
- `hardware id` local
- cache local de licencia
- validacion contra un `license server` configurable

## Instalacion

1. Descarga `ManWTool.zip` desde `Releases`.
2. En Blender ve a `Edit > Preferences > Add-ons > Install`.
3. Selecciona el `.zip`.
4. Activa el addon.

## Ubicacion en Blender

`View3D > Sidebar (N) > ManWTool`

## Flujo recomendado

1. Crear estructura de colecciones.
2. Renombrar el asset.
3. Colocar cada objeto en su coleccion correcta.
4. Exportar.
5. Revisar el informe automatico si hay avisos.

## Version actual

`v1.0.5`

## Preparar releases

Este repositorio `E:\GitHub\ManWTool` es el repositorio de release.

1. Ejecuta `py build_addon.py`
2. Sube `ManWTool.zip` a GitHub Releases
3. Sigue la checklist de `RELEASE_CHECKLIST.md`

## Roadmap corto

- backend real de licencias
- compilar parte sensible del addon
- ampliar el validator con reglas opcionales
- mejorar import y materiales para casos de produccion
