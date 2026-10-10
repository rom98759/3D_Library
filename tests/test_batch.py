from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path, n=3):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    for i in range(1, n + 1):
        # Les chemins réels produits par scanner.py sont toujours sous
        # <bibliothèque>/models/... — on reproduit cette structure pour que
        # le garde-fou de suppression (_is_within_library_models) s'applique
        # comme en production.
        model_dir = tmp_path / "models" / f"model_{i}"
        model_dir.mkdir(parents=True)
        (model_dir / "model.stl").write_bytes(b"fake")
        conn.execute(
            "INSERT INTO models (id, name, path, added_at) VALUES (?, ?, ?, '2026-01-01')",
            (i, f"Model {i}", str(model_dir / "model.stl")),
        )
    conn.commit()
    conn.close()
    return db_path


def _client(tmp_path, monkeypatch, n=3):
    db_path = _make_db(tmp_path, n)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    return TestClient(webapp.app)


def test_batch_trash_processes_all_valid_ids(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.post("/api/models/batch", json={"ids": [1, 2], "action": "trash"})

    assert r.status_code == 200
    assert sorted(r.json()["processed"]) == [1, 2]
    ids = [m["id"] for m in client.get("/api/models").json()]
    assert ids == [3]


def test_batch_skips_unknown_ids_without_failing_the_rest(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.post("/api/models/batch", json={"ids": [1, 999, 2], "action": "trash"})

    body = r.json()
    assert sorted(body["processed"]) == [1, 2]
    assert body["skipped"] == [999]


def test_batch_set_printed_true_updates_all(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.post("/api/models/batch", json={"ids": [1, 2], "action": "set_printed", "printed": True})

    m1 = client.get("/api/models/1").json()
    m2 = client.get("/api/models/2").json()
    assert m1["printed"] == 1
    assert m2["printed"] == 1


def test_batch_add_list_requires_known_list_id(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    r = client.post("/api/models/batch", json={"ids": [1], "action": "add_list", "list_id": 999})

    assert r.status_code == 404


def test_batch_add_list_adds_membership_to_all_ids(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    list_id = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]

    client.post("/api/models/batch", json={"ids": [1, 2], "action": "add_list", "list_id": list_id})

    names1 = {l["name"] for l in client.get("/api/models/1").json()["lists"]}
    names2 = {l["name"] for l in client.get("/api/models/2").json()["lists"]}
    assert names1 == {"Atelier"}
    assert names2 == {"Atelier"}


def test_batch_remove_list_removes_membership(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    list_id = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [list_id]})

    client.post("/api/models/batch", json={"ids": [1], "action": "remove_list", "list_id": list_id})

    assert client.get("/api/models/1").json()["lists"] == []


def test_batch_delete_removes_rows_and_files(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.post("/api/models/batch", json={"ids": [1, 2], "action": "delete"})

    assert client.get("/api/models/1").status_code == 404
    assert client.get("/api/models/2").status_code == 404
    assert client.get("/api/models/3").status_code == 200


def test_batch_delete_never_rmtrees_outside_library_root(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, n=1)
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

    r = client.post("/api/models/batch", json={"ids": [99], "action": "delete"})

    assert r.json()["processed"] == [99]
    assert client.get("/api/models/99").status_code == 404
    assert outside_dir.exists()  # jamais supprimé : hors de <library>/models
