import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from .config import settings

def db_path() -> str:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("This starter supports SQLite only; configure a database adapter before using a non-SQLite DATABASE_URL.")
    path = url.removeprefix("sqlite:///")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path

@contextmanager
def connection():
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, topic TEXT NOT NULL, style TEXT NOT NULL,
            format TEXT NOT NULL, duration_minutes INTEGER NOT NULL, status TEXT NOT NULL,
            scenes_json TEXT NOT NULL DEFAULT '[]', render_url TEXT, error TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")

def encode(row):
    result = dict(row)
    result["scenes"] = json.loads(result.pop("scenes_json", "[]"))
    return result

def update(project_id: str, **values):
    allowed = {"status", "render_url", "error", "scenes_json"}
    fields = {k: json.dumps(v) if k == "scenes_json" and not isinstance(v, str) else v
              for k, v in values.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    assignments = ", ".join(f"{key}=?" for key in fields)
    with connection() as conn:
        conn.execute(f"UPDATE projects SET {assignments} WHERE id=?",
                     (*fields.values(), project_id))
