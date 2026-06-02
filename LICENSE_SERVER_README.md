# License Server

Servidor mínimo de licencias para ManWTool.

## Arranque

1. `py license_server\\seed_demo_data.py`
2. `py license_server\\app.py`

Servidor por defecto: `http://127.0.0.1:8787/validate`

## Request esperado por el addon

```json
{
  "addon_id": "ManWTool",
  "addon_version": "1.0.6",
  "email": "cliente@correo.com",
  "license_key": "MANW-XXXX-XXXX",
  "machine_id": "ABCDEF1234567890"
}
```

## Response

```json
{
  "valid": true,
  "status": "Activa",
  "valid_until": "2027-06-01"
}
```
