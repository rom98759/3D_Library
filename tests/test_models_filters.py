from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    rows = [
        (1, "Zèbre", "/z", "2026-01-01T10:00:00", 50.0, 10.0, 0),
        (2, "Abeille", "/a", "2026-01-03T10:00:00", 10.0, 50.0, 1),
        (3, "Mouche", "/m", "2026-01-02T10:00:00", 30.0, 30.0, 0),
    ]
    for id_, name, path, added_at, weight, volume, printed in rows:
        conn.execute(
            "INSERT INTO models (id, name, path, added_at, estimated_weight_g, volume, printed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id_, name, path, added_at, weight, volume, printed),
        )
    conn.commit()
    conn.close()
    return db_path


def _client(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    return TestClient(webapp.app)


def test_sort_by_name_asc(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    names = [m["name"] for m in client.get("/api/models?sort=name_asc").json()]

    assert names == ["Abeille", "Mouche", "Zèbre"]


def test_sort_by_weight_desc(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    ids = [m["id"] for m in client.get("/api/models?sort=weight_desc").json()]

    assert ids == [1, 3, 2]


def test_default_sort_is_added_desc(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    ids = [m["id"] for m in client.get("/api/models").json()]

    assert ids == [2, 3, 1]


def test_filter_by_printed_true(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    ids = [m["id"] for m in client.get("/api/models?printed=true").json()]

    assert ids == [2]


def test_filter_by_lists_is_and_combined(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    a = client.post("/api/lists", json={"name": "A"}).json()["id"]
    b = client.post("/api/lists", json={"name": "B"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [a, b]})
    client.put("/api/models/2/lists", json={"list_ids": [a]})

    ids = [m["id"] for m in client.get(f"/api/models?lists={a},{b}").json()]

    assert ids == [1]


def test_filter_lists_combined_with_printed_and_q(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    a = client.post("/api/lists", json={"name": "A"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [a]})
    client.put("/api/models/2/lists", json={"list_ids": [a]})

    ids = [m["id"] for m in client.get(f"/api/models?lists={a}&printed=true&q=Abeille").json()]

    assert ids == [2]


def test_update_model_sets_printed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.put("/api/models/1", json={"printed": True})

    assert client.get("/api/models/1").json()["printed"] == 1


def test_stats_includes_trash_count_and_recent(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/models/1/trash")

    stats = client.get("/api/stats").json()

    assert stats["trash_count"] == 1
    assert stats["total_models"] == 2
    assert [m["id"] for m in stats["recent"]] == [2, 3]
