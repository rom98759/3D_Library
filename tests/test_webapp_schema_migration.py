import sqlite3

from fastapi.testclient import TestClient

import webapp


def _make_legacy_db(tmp_path):
    """Base créée avant la migration lists/model_lists/deleted_at/printed —
    simule une bibliothèque de production existante."""
    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE models (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "path TEXT NOT NULL UNIQUE, added_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO models (name, path, added_at) VALUES ('Old', '/x', '2025-01-01')"
    )
    conn.commit()
    conn.close()
    return db_path


def test_webapp_migrates_legacy_db_on_startup(tmp_path, monkeypatch):
    db_path = _make_legacy_db(tmp_path)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)

    with TestClient(webapp.app) as client:
        r = client.get("/api/models")

    assert r.status_code == 200
