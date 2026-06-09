import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "licenses.db"


with sqlite3.connect(DB_PATH) as conn:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            email TEXT NOT NULL,
            license_key TEXT NOT NULL,
            status TEXT NOT NULL,
            valid_until TEXT,
            max_activations INTEGER NOT NULL DEFAULT 2,
            PRIMARY KEY(email, license_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            license_key TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            activated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO licenses(email, license_key, status, valid_until, max_activations)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("demo@manwtool.local", "MANW-DEMO-2026-0001", "active", "2027-06-01", 2),
    )
    conn.commit()

print(f"Demo DB preparada en {DB_PATH}")
