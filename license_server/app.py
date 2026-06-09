import json
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "licenses.db"
HOST = "127.0.0.1"
PORT = 8787


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def validate_license(email, license_key, machine_id):
    with db() as conn:
        row = conn.execute(
            """
            SELECT email, license_key, status, valid_until, max_activations
            FROM licenses
            WHERE email = ? AND license_key = ?
            """,
            (email, license_key),
        ).fetchone()
        if not row:
            return {"valid": False, "status": "Licencia no encontrada"}
        if row["status"] != "active":
            return {"valid": False, "status": f"Licencia en estado {row['status']}"}
        if row["valid_until"] and row["valid_until"] < datetime.utcnow().strftime("%Y-%m-%d"):
            return {"valid": False, "status": "Licencia expirada", "valid_until": row["valid_until"]}

        activation = conn.execute(
            """
            SELECT id FROM activations
            WHERE email = ? AND license_key = ? AND machine_id = ?
            """,
            (email, license_key, machine_id),
        ).fetchone()

        if activation is None:
            count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM activations
                WHERE email = ? AND license_key = ?
                """,
                (email, license_key),
            ).fetchone()["count"]
            if count >= row["max_activations"]:
                return {"valid": False, "status": "Maximo de activaciones alcanzado", "valid_until": row["valid_until"]}
            conn.execute(
                """
                INSERT INTO activations(email, license_key, machine_id, activated_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, license_key, machine_id, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()

        return {"valid": True, "status": "Activa", "valid_until": row["valid_until"]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/validate":
            self._send(404, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = validate_license(
                (payload.get("email") or "").strip(),
                (payload.get("license_key") or "").strip(),
                (payload.get("machine_id") or "").strip(),
            )
            self._send(200, result)
        except Exception as exc:
            self._send(500, {"valid": False, "status": f"Server error: {exc}"})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"License server running on http://{HOST}:{PORT}/validate")
    server.serve_forever()
