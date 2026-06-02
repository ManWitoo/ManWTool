# Comercializacion y proteccion

## Recomendaciones de release

- Publicar siempre un asset ZIP versionado en GitHub Releases
- Mantener desactivada por defecto la instalacion directa de updates
- Probar cada release en Blender antes de publicarla

## Licencias

El addon ya puede hacer `POST` JSON a `license_server_url` con:

- `addon_id`
- `addon_version`
- `email`
- `license_key`
- `machine_id`

Respuesta esperada:

```json
{
  "valid": true,
  "status": "Activa",
  "valid_until": "2027-06-01"
}
```

## Proteccion realista

Python no evita copia por si solo. Si quieres subir la barrera de verdad, el siguiente paso es mover la logica valiosa a un modulo compilado o a un servicio externo.
