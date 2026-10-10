import sqlite3

from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (1, 'Boîte à vis', '/a', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (2, 'Crochet', '/b', '2026-01-02')"
    )
    conn.commit()
    conn.close()
    return db_path


def _client(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    return TestClient(webapp.app)


def test_create_list_returns_id_and_zero_count(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.post("/api/lists", json={"name": "Atelier"})

    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Atelier"
    assert body["model_count"] == 0


def test_create_list_rejects_duplicate_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/lists", json={"name": "Atelier"})

    r = client.post("/api/lists", json={"name": "Atelier"})

    assert r.status_code == 409


def test_create_list_rejects_duplicate_name_case_insensitively(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/lists", json={"name": "Atelier"})

    r = client.post("/api/lists", json={"name": "atelier"})

    assert r.status_code == 409


def test_rename_list_rejects_collision_case_insensitively(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/lists", json={"name": "Atelier"})
    other_id = client.post("/api/lists", json={"name": "Maison"}).json()["id"]

    r = client.put(f"/api/lists/{other_id}", json={"name": "ATELIER"})

    assert r.status_code == 409


def test_get_lists_includes_model_count_excluding_deleted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    list_id = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [list_id]})
    client.put("/api/models/2/lists", json={"list_ids": [list_id]})
    # La corbeille (POST /api/models/{id}/trash) n'existe qu'à partir de la
    # Tâche 3 — on simule directement l'état "supprimé" en base pour tester
    # ici le filtre deleted_at IS NULL de la requête model_count.
    conn = sqlite3.connect(webapp.DB_PATH)
    conn.execute("UPDATE models SET deleted_at = '2026-01-03T00:00:00' WHERE id = 2")
    conn.commit()
    conn.close()

    r = client.get("/api/lists")

    assert r.status_code == 200
    atelier = next(l for l in r.json() if l["name"] == "Atelier")
    assert atelier["model_count"] == 1


def test_rename_list_rejects_collision_with_existing_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/lists", json={"name": "Atelier"})
    other_id = client.post("/api/lists", json={"name": "Maison"}).json()["id"]

    r = client.put(f"/api/lists/{other_id}", json={"name": "Atelier"})

    assert r.status_code == 409


def test_delete_list_removes_model_lists_rows_but_not_models(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    list_id = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [list_id]})

    r = client.delete(f"/api/lists/{list_id}")

    assert r.status_code == 200
    model = client.get("/api/models/1").json()
    assert model["lists"] == []


def test_set_model_lists_rejects_unknown_list_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.put("/api/models/1/lists", json={"list_ids": [999]})

    assert r.status_code == 400


def test_set_model_lists_replaces_full_set(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    a = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]
    b = client.post("/api/lists", json={"name": "Favoris"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [a, b]})

    client.put("/api/models/1/lists", json={"list_ids": [b]})

    names = {l["name"] for l in client.get("/api/models/1").json()["lists"]}
    assert names == {"Favoris"}


def test_get_model_includes_lists_key_even_when_empty(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.get("/api/models/1")

    assert r.json()["lists"] == []
