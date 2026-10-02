import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "db" / "migrations"


def connect() -> psycopg.Connection:
    load_dotenv(ROOT / ".env")
    return psycopg.connect(
        host="127.0.0.1",
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        user=os.environ.get("POSTGRES_USER", "streetwalker"),
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ.get("POSTGRES_DB", "streetwalker"),
    )


def migrate(conn: psycopg.Connection) -> None:
    """Apply every migration file in order. Files are written to be re-runnable."""
    for path in sorted(MIGRATIONS.glob("*.sql")):
        conn.execute(path.read_text())
    conn.commit()
