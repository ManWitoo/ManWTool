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

Python no evita copia por si solo. Este repo ya incluye una base para:

- mover matching/logica sensible a `manwtool_protected.pyx`
- compilarla con `setup_protected.py`
- validar licencias con un servicio externo simple

Si quieres subir aun mas la barrera, el siguiente paso es llevar mas logica de export/import al modulo compilado o al backend.
