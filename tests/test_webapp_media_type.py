import sqlite3

from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path):
    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(scanner.DB_SCHEMA)

    stl_file = tmp_path / "model.stl"
    stl_file.write_bytes(b"fake stl content")
    mf_file = tmp_path / "model.3mf"
    mf_file.write_bytes(b"fake 3mf content")

    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (1, 'A', ?, '2026-01-01')",
        (str(stl_file),),
    )
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (2, 'B', ?, '2026-01-01')",
        (str(mf_file),),
    )
    conn.commit()
    conn.close()
    return db_path


def test_get_stl_file_media_type_by_extension(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    client = TestClient(webapp.app)

    stl_response = client.get("/api/models/1/stl")
    mf_response = client.get("/api/models/2/stl")

    assert stl_response.status_code == 200
    assert stl_response.headers["content-type"] == "model/stl"
    assert mf_response.status_code == 200
    assert mf_response.headers["content-type"] == "model/3mf"
