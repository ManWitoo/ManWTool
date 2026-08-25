# ManWTool v1.2.1

## Aplicar transforms en jerarquias

Corregido el fallo principal de esta version: al seleccionar un padre (grupo vacio o malla con hijos)
y ejecutar **Aplicar transforms**, las transformaciones solo se aplicaban al objeto seleccionado.
Los hijos conservaban la escala y rotacion heredadas, asi que el resultado no coincidia con lo que
se ve en el visor.

Ahora la seleccion se expande de forma recursiva a todos los descendientes MESH/EMPTY, y el aplicado
se hace en **una sola pasada** sobre la jerarquia completa (`transform_apply` con padre e hijos
seleccionados a la vez). Es el equivalente exacto al Ctrl+A de Blender sobre toda la jerarquia:
la escala/rotacion del padre se hornea en la geometria de los hijos y todos terminan con transform
identidad.

## Detalles

- Nueva funcion `get_transform_targets_from_selection()`: devuelve los MESH/EMPTY seleccionados mas
  todos sus descendientes, sin duplicados.
- Nuevo modo lote en `apply_transformations_to_objects(..., batch=True)`, con implementacion en
  `_apply_transformations_batch()`. Solo se activa cuando unicamente se aplican transformaciones
  (sin `set_origin`, `move_to_origin` ni `reset_rotation_after`), que es donde el aplicado por
  objeto daba un resultado incorrecto.
- Los datos multi-usuario se pasan a single-user **antes** de aplicar, porque `transform_apply`
  falla sobre mallas compartidas.
- Si el aplicado en lote falla por cualquier motivo, se reintenta objeto a objeto (menos correcto
  para jerarquias, pero nunca deja la operacion a medias) y se registra la excepcion en el log.
- La seleccion y el objeto activo previos se restauran siempre al terminar.
- La deteccion de escala negativa y normales invertidas ahora tiene en cuenta tambien los hijos
  incluidos automaticamente, no solo lo que el usuario habia seleccionado a mano.
