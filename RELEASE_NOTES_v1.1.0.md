# ManWTool v1.1.0

## Cambio estructural importante

A partir de esta version el addon se distribuye en **formato paquete** (carpeta `ManWTool/` dentro del ZIP) en lugar de un unico archivo `ManWTool.py`. El codigo es ahora identico entre el repositorio de desarrollo y el comercial; la unica diferencia es `manwtool_edition.py` (exigencia de licencia) y el modulo protegido compilado.

> **Actualizacion desde v1.0.x:** desinstala primero la version antigua (archivo unico) desde las preferencias de Blender y despues instala este ZIP. El actualizador integrado de versiones antiguas no puede instalar este formato automaticamente.

## Novedades

- Deteccion de escala negativa y de normales invertidas en mallas cerradas, con menu de confirmacion para recalcular normales al aplicar transformaciones (ahora tambien en la version de desarrollo).
- Registro de eventos a archivo con rotacion (`manwtool.log` en la carpeta de configuracion del addon), util para soporte.
- Matching de texturas mas rapido: indice de alias precompilado, cache del listado de la carpeta de materiales y salida temprana.
- Editor de presets de exportacion por preferencias (Unreal/Unity/Highpoly/Lowpoly/Custom) unificado en ambas ediciones.
- Todos los textos del aviso de licencia y del menu de normales estan traducidos (ES/EN/FR/DE/IT/PT).

## Robustez

- Acceso al estado del actualizador protegido con lock (sin riesgo de carreras entre el hilo de red y el timer de Blender).
- El validador de ZIP de releases acepta tanto el formato paquete nuevo como el formato antiguo de archivo unico.
- El modulo protegido (Cython) se carga con fallback transparente a Python puro si no esta presente.

## Infraestructura

- `sync_commercial.py`: un comando sincroniza el codigo de desarrollo al repo comercial.
- GitHub Actions: al subir un tag `v*` se construye el ZIP y se publica la release automaticamente.
