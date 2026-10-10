import sqlite3
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    # Les chemins réels produits par scanner.py sont toujours sous
    # <bibliothèque>/models/... — on reproduit cette structure pour que le
    # garde-fou de suppression (_is_within_library_models) s'applique comme
    # en production.
    model_dir = tmp_path / "models" / "model_1"
    model_dir.mkdir(parents=True)
    (model_dir / "model.stl").write_bytes(b"fake")
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (1, 'A', ?, '2026-01-01')",
        (str(model_dir / "model.stl"),),
    )
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES "
        "(2, 'B', '/already/gone/model.stl', '2026-01-01')"
    )
    conn.commit()
    conn.close()
    return db_path


def _client(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    return TestClient(webapp.app)


def test_trash_hides_model_from_default_listing(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.post("/api/models/1/trash")

    ids = [m["id"] for m in client.get("/api/models").json()]
    assert 1 not in ids


def test_trashed_model_appears_in_trash_listing_with_purge_date(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/models/1/trash")

    trash = client.get("/api/trash").json()

    entry = next(m for m in trash if m["id"] == 1)
    assert entry["purge_at"] > entry["deleted_at"]


def test_restore_makes_model_visible_again(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/models/1/trash")

    client.post("/api/models/1/restore")

    ids = [m["id"] for m in client.get("/api/models").json()]
    assert 1 in ids
    trash_ids = [m["id"] for m in client.get("/api/trash").json()]
    assert 1 not in trash_ids


def test_permanent_delete_removes_db_row_and_files(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    model = client.get("/api/models/1").json()
    folder = model["path"]

    r = client.delete("/api/models/1")

    assert r.status_code == 200
    assert client.get("/api/models/1").status_code == 404
    from pathlib import Path
    assert not Path(folder).parent.exists()


def test_permanent_delete_never_rmtrees_outside_library_root(tmp_path, monkeypatch):
    """Une ligne dont le chemin sort de <bibliothèque>/models (legacy, ou
    insérée à la main) ne doit jamais faire supprimer un dossier arbitraire
    du disque — seule la ligne DB doit disparaître."""
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    outside_dir = tmp_path / "outside_the_library"
    outside_dir.mkdir()
    (outside_dir / "model.stl").write_bytes(b"fake")
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (99, 'Outside', ?, '2026-01-01')",
        (str(outside_dir / "model.stl"),),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    client = TestClient(webapp.app)

    r = client.delete("/api/models/99")

    assert r.status_code == 200
    assert client.get("/api/models/99").status_code == 404
    assert outside_dir.exists()  # jamais supprimé : hors de <library>/models


def test_permanent_delete_tolerates_already_missing_files(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.delete("/api/models/2")

    assert r.status_code == 200
    assert client.get("/api/models/2").status_code == 404


def test_permanent_delete_cascades_model_lists_rows(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    list_id = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [list_id]})

    client.delete("/api/models/1")

    lists = client.get("/api/lists").json()
    assert next(l for l in lists if l["id"] == list_id)["model_count"] == 0


def test_trashing_an_already_trashed_model_does_not_reset_the_purge_clock(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/models/1/trash")
    first_deleted_at = next(m for m in client.get("/api/trash").json() if m["id"] == 1)["deleted_at"]

    client.post("/api/models/1/trash")

    second_deleted_at = next(m for m in client.get("/api/trash").json() if m["id"] == 1)["deleted_at"]
    assert second_deleted_at == first_deleted_at


def test_list_trash_tolerates_a_malformed_deleted_at_without_500(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/models/1/trash")
    conn = sqlite3.connect(webapp.DB_PATH)
    conn.execute("UPDATE models SET deleted_at = 'not-a-date' WHERE id = 2")
    conn.commit()
    conn.close()

    r = client.get("/api/trash")

    assert r.status_code == 200
    by_id = {m["id"]: m for m in r.json()}
    assert "purge_at" in by_id[1]
    assert by_id[2]["purge_at"] is None
