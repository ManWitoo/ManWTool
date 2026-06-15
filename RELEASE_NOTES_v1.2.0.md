# ManWTool v1.2.0

## Actualizacion sin reiniciar Blender

El gran cambio de esta version: cuando instalas un update desde el propio addon, ManWTool se recarga en caliente y **no hace falta reiniciar Blender**. Antes cada update obligaba a reiniciar.

Como funciona por dentro: tras descargar y validar el ZIP de la release e instalarlo, se programa un timer que (fuera del operador) desactiva el addon, purga sus modulos de `sys.modules` y lo vuelve a activar, cargando ya el codigo nuevo. Si esa recarga falla (caso tipico: un modulo nativo `.pyd` cargado y bloqueado en Windows), se cae al comportamiento anterior y se pide reiniciar.

## Otras mejoras

- El ZIP temporal del update ya no se queda en disco: se borra automaticamente tras instalar.
- El validador de export ya no recalcula el mapa de nombres de toda la escena en cada repintado del panel; se cachea y solo se rehace al anadir, borrar o renombrar mallas. Menos lag en escenas grandes.
- La deteccion de normales invertidas usa una sola pasada de bmesh por objeto.
- Mensajes de exportacion totalmente traducidos (i18n).
- Limpieza de codigo muerto interno.

## Nota para la edicion comercial

El modulo protegido `manwtool_protected.pyd` no viaja en el ZIP de release (el build solo empaqueta `.py`). En esos casos el addon usa el fallback en Python puro y la recarga en caliente funciona sin problema. Si distribuyes el binario nativo, la recarga en caliente de ese modulo concreto puede no aplicarse hasta el siguiente reinicio (se gestiona con el plan B).
