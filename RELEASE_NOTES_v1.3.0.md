# ManWTool v1.3.0

## Sincronizacion automatica de nombres Object -> Data

En Blender el objeto y su datablock son IDs independientes con nombres independientes.
Renombrar un objeto no toca el nombre de su mesh, asi que acabas con `B2M1_LilyFlower_Geo`
conteniendo una mesh llamada `Plane.003`. Eso rompe la trazabilidad en el export FBX y en
cualquier pipeline que resuelva por nombre de datablock, y hasta ahora habia que corregirlo
a mano.

Ahora hay un toggle: **Sincronizar nombres de mesh**. Con el activo, cada vez que renombras
un objeto su datablock se renombra solo.

Funciona **venga el renombrado de donde venga**: Outliner, F2, panel N, scripts u operadores
del propio ManWTool. Esto es asi porque la feature se apoya en el handler
`depsgraph_update_post`, que recibe la lista de IDs actualizados, en lugar de `msgbus` sobre
`Object.name`. `msgbus` no dice *que* objeto cambio y obliga a deducirlo desde el objeto
activo, lo que falla justo en el caso mas comun: renombrar en el Outliner un objeto que no
es el activo.

## Operador batch

**Sincronizar todos los nombres** (`manwtool.sync_all_data_names`) recorre la escena y corrige
todos los desajustes existentes de una pasada. Tres ambitos: Seleccion, Escena y Archivo.
Reporta cuantos datablocks sincronizo y cuantos se saltaron.

Es independiente del toggle: funciona igual con la sincronizacion automatica desactivada.

## Que NO se toca (y por que)

| Caso | Motivo |
|---|---|
| Datablock compartido por varios objetos | Que nombre gana es ambiguo. Se salta y se reporta en el conteo. |
| Datos linkeados desde una libreria | Son read-only, `data.name` no es asignable. |
| Library override | Renombrar rompe el vinculo con el original. |
| Empties y objetos sin datablock | No hay nada que renombrar. |

La regla de los datablocks compartidos es deliberada y esta documentada en el tooltip del
toggle, porque es el caso donde mas se espera que funcione y no lo hace.

Los **fake users** se descuentan del recuento (`data.users - 1` si `use_fake_user`), de modo
que un datablock con fake user y un solo objeto real si se sincroniza. Sin ese descuento
reportaria 2 usuarios y se saltaria siempre.

## Notas de implementacion

- El handler lleva `@persistent`: sin el, Blender lo descarta al cargar un `.blend` y el
  toggle quedaria mintiendo (dice ON, no hace nada).
- Guarda de re-entrancia a nivel de modulo con `try/finally`. Asignar `data.name` marca el ID
  como actualizado y vuelve a disparar `depsgraph_update_post`; sin la guarda hay recursion.
  El `finally` es obligatorio: una excepcion que dejase el flag activo mataria la feature en
  silencio durante el resto de la sesion.
- Se usa `update.id.original` porque el depsgraph puede entregar copias evaluadas, y escribir
  sobre una copia evaluada no persiste en el archivo.
- El handler **no** se registra en `register()` incondicionalmente: se registra y se retira
  desde el callback `update=` de la preferencia, mas una resincronizacion en `register()` para
  restaurar el estado guardado. Con el toggle apagado el handler no esta en la lista y el
  coste es exactamente cero, incluso reproduciendo la timeline.
- `unregister()` retira el handler siempre, comprobando pertenencia antes para no duplicarlo
  ni lanzar `ValueError` al recargar el addon.

## Fuera de alcance en esta version

Sincronizacion inversa (data -> object), sufijos configurables (`X_Geo` -> `X`), extension a
materiales y acciones, y estrategias alternativas para datablocks multiusuario.
