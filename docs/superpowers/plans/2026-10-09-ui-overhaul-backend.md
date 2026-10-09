# UI Overhaul — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the data model and API surface needed by the new UI — manual lists (replacing the auto-category as the organizing concept), a soft-delete trash with timed purge, a "printed" flag, batch actions, and extended filter/sort on `GET /api/models`.

**Architecture:** Additive SQLite migration (new `lists`/`model_lists` tables, two new columns on `models`) applied idempotently from `scanner.py`, surfaced through new/extended FastAPI endpoints in `webapp.py`, with a standalone `purge_trash.py` script (same pattern as `watch_trigger.py`) run by a new systemd timer. No change to `auto_tag.py` itself — only to how its `category` return value is (not) used.

**Tech Stack:** Python, FastAPI, Pydantic, sqlite3 (stdlib), pytest, systemd (timer unit).

**Spec:** `docs/superpowers/specs/2026-10-09-ui-overhaul-design.md`

This plan implements the **Modèle de données**, **Scanner**, **API**, **Purge
automatique**, and backend parts of **Gestion d'erreurs** / **Tests** sections
of the spec. The **Frontend** section is implemented by a separate plan
(`docs/superpowers/plans/2026-10-09-ui-overhaul-frontend.md`) that consumes
the API this plan produces.

## Global Constraints

- SQLite migration must be additive and idempotent — never drop or rewrite existing columns/data (spec: "Modèle de données").
- `auto_tag.py` itself is not modified; only its `category` return value stops being used to create/assign a list (spec: "Scanner"). `tags` continue to populate the `tags` column unchanged.
- All "normal" read endpoints filter `deleted_at IS NULL` by default; the trash is only visible through `GET /api/trash` (spec: "Modèle de données", "API").
- `TRASH_RETENTION_DAYS` is an environment variable, default `30` (spec: "Purge automatique").
- Batch operations on invalid/missing ids are skipped, not fatal — the rest of the batch still runs (spec: "Gestion d'erreurs").
- Deleting files that are already missing from disk logs a warning and continues — never raises (spec: "Gestion d'erreurs").
- No new frontend test tooling is in scope for this plan (frontend has no code yet); backend changes are covered by pytest, following the existing test style in `tests/`.

## Review Focus

- A `model_id` reused across two different batch actions in the same request after being deleted by an earlier action in that same batch — must not crash the remaining items.
- Renaming a list to a name that collides with another existing list (case-insensitive, since lists are rendered with `COLLATE NOCASE` ordering) — must return a clear conflict, not a silent overwrite or a 500.
- `PUT /api/models/{id}/lists` with a `list_id` that doesn't exist in `lists` — must reject with 400, not insert a dangling `model_lists` row (the `lists` table has no `ON DELETE CASCADE` protection against inserting garbage, only against deleting a referenced row).
- A model whose on-disk folder was already removed manually, then trashed and purged — `purge_trash.py` must still remove its DB row instead of leaving an orphaned entry forever.
- `GET /api/models?lists=1,2` combined with `q=` and `printed=true` all at once — the AND-combination across list membership, text search, and printed status must each narrow the result set independently, not override each other.

---

## File Structure

- Modify `scanner.py`: extend `DB_SCHEMA` (new `lists`/`model_lists` tables, new `models` columns for fresh DBs), add `ensure_schema(conn)` for idempotent migration of existing DBs, update `init_db()` to call it and enable `PRAGMA foreign_keys`.
- Modify `webapp.py`: new Pydantic models, new endpoints (`/api/lists*`, `/api/models/{id}/lists`, `/api/models/{id}/trash`, `/api/models/{id}/restore`, `DELETE /api/models/{id}`, `/api/trash`, `/api/models/batch`), extended `GET /api/models` and `GET /api/stats`, `printed` on `ModelUpdate`, `_attach_lists()` helper, migration call at startup.
- Create `purge_trash.py`: standalone purge script, same shape as `watch_trigger.py`.
- Create `systemd/3d-library-purge.service` and `systemd/3d-library-purge.timer`.
- Create `tests/test_scanner_schema.py`, `tests/test_lists_api.py`, `tests/test_trash.py`, `tests/test_batch.py`, `tests/test_models_filters.py`, `tests/test_purge_trash.py`.

---

### Task 1: Schema migration in `scanner.py`

**Files:**
- Modify: `scanner.py:28-59` (`DB_SCHEMA`), `scanner.py:126-130` (`init_db`)
- Test: `tests/test_scanner_schema.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `scanner.ensure_schema(conn: sqlite3.Connection) -> None` (idempotent migration, callable by `webapp.py` and `purge_trash.py`); `scanner.init_db(db_path)` now also enables `PRAGMA foreign_keys = ON` and calls `ensure_schema`. `models` table gains `deleted_at TEXT` and `printed INTEGER DEFAULT 0`. New tables `lists(id, name, created_at)` and `model_lists(model_id, list_id)` with `ON DELETE CASCADE` on both foreign keys.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scanner_schema.py
import sqlite3

import scanner


def test_init_db_creates_lists_and_model_lists_tables(tmp_path):
    conn = scanner.init_db(tmp_path / "library.db")

    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    assert "lists" in tables
    assert "model_lists" in tables
    conn.close()


def test_init_db_adds_deleted_at_and_printed_columns(tmp_path):
    conn = scanner.init_db(tmp_path / "library.db")

    cols = {row[1] for row in conn.execute("PRAGMA table_info(models)")}

    assert "deleted_at" in cols
    assert "printed" in cols
    conn.close()


def test_ensure_schema_is_idempotent_on_legacy_db_without_new_columns(tmp_path):
    db_path = tmp_path / "library.db"
    # Simule une base créée avant cette migration : schéma `models` sans les
    # nouvelles colonnes, pas de table lists/model_lists.
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.execute(
        "CREATE TABLE models (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
        "path TEXT NOT NULL UNIQUE, added_at TEXT NOT NULL)"
    )
    legacy_conn.execute(
        "INSERT INTO models (name, path, added_at) VALUES ('Old', '/x', '2025-01-01')"
    )
    legacy_conn.commit()
    legacy_conn.close()

    conn = sqlite3.connect(db_path)
    scanner.ensure_schema(conn)
    scanner.ensure_schema(conn)  # un second appel ne doit pas lever d'erreur

    cols = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
    row = conn.execute("SELECT name, deleted_at, printed FROM models WHERE name = 'Old'").fetchone()

    assert "deleted_at" in cols
    assert "printed" in cols
    assert row == ("Old", None, 0)
    conn.close()


def test_init_db_enables_foreign_key_cascade_on_model_delete(tmp_path):
    conn = scanner.init_db(tmp_path / "library.db")
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (1, 'A', '/a', '2026-01-01')"
    )
    conn.execute("INSERT INTO lists (id, name, created_at) VALUES (1, 'Atelier', '2026-01-01')")
    conn.execute("INSERT INTO model_lists (model_id, list_id) VALUES (1, 1)")
    conn.commit()

    conn.execute("DELETE FROM models WHERE id = 1")
    conn.commit()

    remaining = conn.execute("SELECT COUNT(*) FROM model_lists").fetchone()[0]
    assert remaining == 0
    conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_scanner_schema.py -v`
Expected: FAIL — `lists`/`model_lists` tables don't exist, `ensure_schema` is not defined, `deleted_at`/`printed` columns missing.

- [ ] **Step 3: Implement the migration**

Replace `DB_SCHEMA` in `scanner.py:28-59` with:

```python
DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    original_filename TEXT,
    path TEXT NOT NULL UNIQUE,
    file_hash TEXT UNIQUE,
    size_bytes INTEGER,
    source_archive TEXT,
    category TEXT,
    tags TEXT,
    size_x REAL,
    size_y REAL,
    size_z REAL,
    volume REAL,
    is_watertight INTEGER,
    material TEXT,
    estimated_weight_g REAL,
    estimated_print_time_h REAL,
    thumbnail_path TEXT,
    added_at TEXT NOT NULL,
    print_count INTEGER DEFAULT 0,
    deleted_at TEXT,
    printed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_path TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    scanned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_lists (
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    PRIMARY KEY (model_id, list_id)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crée les tables manquantes et ajoute les colonnes introduites après la
    création initiale de la base, sans toucher aux données existantes.
    Idempotent : peut être appelé à chaque démarrage (scanner, webapp,
    purge_trash)."""
    conn.executescript(DB_SCHEMA)  # CREATE TABLE IF NOT EXISTS : sûr à rejouer

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
    if "deleted_at" not in existing_cols:
        conn.execute("ALTER TABLE models ADD COLUMN deleted_at TEXT")
    if "printed" not in existing_cols:
        conn.execute("ALTER TABLE models ADD COLUMN printed INTEGER DEFAULT 0")
    conn.commit()
```

Replace `init_db` in `scanner.py:126-130` with:

```python
def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_scanner_schema.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full existing suite to check for regressions**

Run: `python3 -m pytest -v`
Expected: PASS — no existing test should break (the new columns/tables are additive).

- [ ] **Step 6: Commit**

```bash
git add scanner.py tests/test_scanner_schema.py
git commit -m "feat(db): add lists/model_lists tables and deleted_at/printed columns"
```

---

### Task 2: Lists CRUD + model↔list association API

**Files:**
- Modify: `webapp.py` (imports, `get_conn`, `get_model_or_404`, new Pydantic models, new endpoints)
- Test: `tests/test_lists_api.py`

**Interfaces:**
- Consumes: `scanner.ensure_schema` (Task 1), existing `get_conn()`/`get_model_or_404()` shape.
- Produces: `_attach_lists(conn, models: list[dict]) -> None` (mutates each dict in place, adding `"lists": [{"id": int, "name": str}, ...]`); endpoints `GET /api/lists`, `POST /api/lists`, `PUT /api/lists/{list_id}`, `DELETE /api/lists/{list_id}`, `PUT /api/models/{model_id}/lists`. `get_model_or_404()` now returns a dict that always includes a `"lists"` key — later tasks (3, 4, 5) can rely on that key being present.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lists_api.py
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


def test_get_lists_includes_model_count_excluding_deleted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    list_id = client.post("/api/lists", json={"name": "Atelier"}).json()["id"]
    client.put("/api/models/1/lists", json={"list_ids": [list_id]})
    client.put("/api/models/2/lists", json={"list_ids": [list_id]})
    client.post("/api/models/2/trash")

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_lists_api.py -v`
Expected: FAIL — endpoints don't exist (404s), `lists` key missing from model dicts.

- [ ] **Step 3: Implement the endpoints**

Add imports near the top of `webapp.py` (alongside the existing ones):

```python
from datetime import datetime, timedelta
from typing import Literal

import scanner
```

(`timedelta` isn't used until Task 3's `list_trash`, but importing it now avoids touching this line twice.)

Update `get_conn()` (`webapp.py:143-151`) to enable foreign keys:

```python
def get_conn():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Base introuvable : {DB_PATH}. Lance d'abord scanner.py.",
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

Add the `_attach_lists` helper and update `get_model_or_404` (`webapp.py:154-160`):

```python
def _attach_lists(conn, models: list[dict]) -> None:
    if not models:
        return
    ids = [m["id"] for m in models]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT ml.model_id AS model_id, l.id AS id, l.name AS name
            FROM model_lists ml
            JOIN lists l ON l.id = ml.list_id
            WHERE ml.model_id IN ({placeholders})
            ORDER BY l.name COLLATE NOCASE""",
        ids,
    ).fetchall()
    by_model: dict[int, list[dict]] = {}
    for r in rows:
        by_model.setdefault(r["model_id"], []).append({"id": r["id"], "name": r["name"]})
    for m in models:
        m["lists"] = by_model.get(m["id"], [])


def get_model_or_404(model_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    model = dict(row)
    _attach_lists(conn, [model])
    conn.close()
    return model
```

Add new Pydantic models near `ModelUpdate` (`webapp.py:135-140`):

```python
class ListCreate(BaseModel):
    name: str


class ListRename(BaseModel):
    name: str


class ModelListsUpdate(BaseModel):
    list_ids: list[int]
```

Add the endpoints (anywhere after `get_model_or_404`, e.g. right before `@app.get("/api/models")`):

```python
@app.get("/api/lists")
def get_lists():
    conn = get_conn()
    rows = conn.execute(
        """SELECT l.id, l.name,
                  (SELECT COUNT(*) FROM model_lists ml
                   JOIN models m ON m.id = ml.model_id
                   WHERE ml.list_id = l.id AND m.deleted_at IS NULL) AS model_count
           FROM lists l ORDER BY l.name COLLATE NOCASE"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/lists", status_code=201)
def create_list(data: ListCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de liste requis")
    conn = get_conn()
    if conn.execute("SELECT id FROM lists WHERE name = ?", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Une liste avec ce nom existe déjà")
    cur = conn.execute(
        "INSERT INTO lists (name, created_at) VALUES (?, ?)",
        (name, datetime.now().isoformat()),
    )
    conn.commit()
    list_id = cur.lastrowid
    conn.close()
    return {"id": list_id, "name": name, "model_count": 0}


@app.put("/api/lists/{list_id}")
def rename_list(list_id: int, data: ListRename):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de liste requis")
    conn = get_conn()
    if not conn.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Liste introuvable")
    if conn.execute("SELECT id FROM lists WHERE name = ? AND id != ?", (name, list_id)).fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Une liste avec ce nom existe déjà")
    conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
    conn.commit()
    conn.close()
    return {"id": list_id, "name": name}


@app.delete("/api/lists/{list_id}")
def delete_list(list_id: int):
    conn = get_conn()
    if not conn.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Liste introuvable")
    conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()
    return {"message": "Liste supprimée", "id": list_id}


@app.put("/api/models/{model_id}/lists")
def set_model_lists(model_id: int, data: ModelListsUpdate):
    get_model_or_404(model_id)
    conn = get_conn()
    valid_ids = {r["id"] for r in conn.execute("SELECT id FROM lists").fetchall()}
    requested = set(data.list_ids)
    unknown = requested - valid_ids
    if unknown:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Liste(s) inconnue(s) : {sorted(unknown)}")
    conn.execute("DELETE FROM model_lists WHERE model_id = ?", (model_id,))
    conn.executemany(
        "INSERT INTO model_lists (model_id, list_id) VALUES (?, ?)",
        [(model_id, lid) for lid in requested],
    )
    conn.commit()
    conn.close()
    return {"model_id": model_id, "list_ids": sorted(requested)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_lists_api.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp.py tests/test_lists_api.py
git commit -m "feat(api): add lists CRUD and model-to-lists association endpoints"
```

---

### Task 3: Trash (soft delete, restore, permanent delete, listing)

**Files:**
- Modify: `webapp.py` (new endpoints, imports)
- Test: `tests/test_trash.py`

**Interfaces:**
- Consumes: `get_model_or_404` and `_attach_lists` from Task 2; `TRASH_RETENTION_DAYS` env var (spec default `30`).
- Produces: `POST /api/models/{id}/trash`, `POST /api/models/{id}/restore`, `DELETE /api/models/{id}`, `GET /api/trash` (each trash row gains a `"purge_at"` ISO timestamp field). `TRASH_RETENTION_DAYS` module-level constant in `webapp.py`, reused by Task 6 (`purge_trash.py` reads its own env var independently, but both default to `30` and the same env var name, per spec).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trash.py
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    model_dir = tmp_path / "model_1"
    model_dir.mkdir()
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_trash.py -v`
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Implement the endpoints**

Add near the top constants of `webapp.py` (alongside `IDLE_TIMEOUT_SECONDS`):

```python
TRASH_RETENTION_DAYS = int(os.environ.get("TRASH_RETENTION_DAYS", "30"))
```

Update `GET /api/models` (`webapp.py:163-183`) to exclude trashed models by
default — this is extended further in Task 5, but the exclusion itself is
needed now:

```python
@app.get("/api/models")
def list_models(q: str = "", category: str = ""):
    """Liste/recherche les modèles. Recherche simple sur le nom et les tags."""
    conn = get_conn()
    query = "SELECT * FROM models WHERE deleted_at IS NULL"
    params = []

    if q:
        query += " AND (name LIKE ? OR tags LIKE ? OR original_filename LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY added_at DESC"

    rows = conn.execute(query, params).fetchall()
    models = [dict(r) for r in rows]
    _attach_lists(conn, models)
    conn.close()
    return models
```

Add the trash endpoints (after `set_model_lists`, before `GET /api/models`).
`shutil` is already imported at the top of `webapp.py` (`webapp.py:20`), no
new import needed:

```python
@app.post("/api/models/{model_id}/trash")
def trash_model(model_id: int):
    get_model_or_404(model_id)
    conn = get_conn()
    conn.execute(
        "UPDATE models SET deleted_at = ? WHERE id = ?",
        (datetime.now().isoformat(), model_id),
    )
    conn.commit()
    conn.close()
    return {"message": "Modèle mis à la corbeille", "id": model_id}


@app.post("/api/models/{model_id}/restore")
def restore_model(model_id: int):
    get_model_or_404(model_id)
    conn = get_conn()
    conn.execute("UPDATE models SET deleted_at = NULL WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()
    return {"message": "Modèle restauré", "id": model_id}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: int):
    model = get_model_or_404(model_id)
    conn = get_conn()
    conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()

    folder = Path(model["path"]).parent
    if folder.exists():
        try:
            shutil.rmtree(folder)
        except OSError as e:
            print(f"[webapp] suppression fichiers échouée pour id={model_id} : {e}")
    return {"message": "Modèle supprimé définitivement", "id": model_id}


@app.get("/api/trash")
def list_trash():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM models WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    models = [dict(r) for r in rows]
    _attach_lists(conn, models)
    conn.close()
    for m in models:
        purge_at = datetime.fromisoformat(m["deleted_at"]) + timedelta(days=TRASH_RETENTION_DAYS)
        m["purge_at"] = purge_at.isoformat()
    return models
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_trash.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp.py tests/test_trash.py
git commit -m "feat(api): add trash (soft delete), restore, and permanent delete"
```

---

### Task 4: Batch actions endpoint

**Files:**
- Modify: `webapp.py`
- Test: `tests/test_batch.py`

**Interfaces:**
- Consumes: trash/restore/delete logic shape from Task 3, list validation shape from Task 2.
- Produces: `POST /api/models/batch` accepting `{ids: list[int], action: "trash"|"restore"|"delete"|"add_list"|"remove_list"|"set_printed", list_id?: int, printed?: bool}`, returning `{"processed": list[int], "skipped": list[int]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_batch.py
from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path, n=3):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    for i in range(1, n + 1):
        model_dir = tmp_path / f"model_{i}"
        model_dir.mkdir()
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_batch.py -v`
Expected: FAIL — `/api/models/batch` doesn't exist.

- [ ] **Step 3: Implement the endpoint**

Add the Pydantic model near the others in `webapp.py`:

```python
class BatchAction(BaseModel):
    ids: list[int]
    action: Literal["trash", "restore", "delete", "add_list", "remove_list", "set_printed"]
    list_id: int | None = None
    printed: bool | None = None
```

Add the endpoint (after the trash endpoints from Task 3):

```python
@app.post("/api/models/batch")
def batch_action(data: BatchAction):
    conn = get_conn()

    if data.action in ("add_list", "remove_list"):
        if data.list_id is None:
            conn.close()
            raise HTTPException(status_code=400, detail="list_id requis pour cette action")
        if not conn.execute("SELECT id FROM lists WHERE id = ?", (data.list_id,)).fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Liste introuvable")
    if data.action == "set_printed" and data.printed is None:
        conn.close()
        raise HTTPException(status_code=400, detail="printed requis pour cette action")

    existing_ids = set()
    if data.ids:
        placeholders = ",".join("?" * len(data.ids))
        existing_ids = {
            r["id"] for r in conn.execute(
                f"SELECT id FROM models WHERE id IN ({placeholders})", data.ids,
            ).fetchall()
        }

    processed, skipped = [], []
    for model_id in data.ids:
        if model_id not in existing_ids:
            skipped.append(model_id)
            continue

        if data.action == "trash":
            conn.execute(
                "UPDATE models SET deleted_at = ? WHERE id = ?",
                (datetime.now().isoformat(), model_id),
            )
        elif data.action == "restore":
            conn.execute("UPDATE models SET deleted_at = NULL WHERE id = ?", (model_id,))
        elif data.action == "delete":
            row = conn.execute("SELECT path FROM models WHERE id = ?", (model_id,)).fetchone()
            conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
            if row:
                folder = Path(row["path"]).parent
                if folder.exists():
                    try:
                        shutil.rmtree(folder)
                    except OSError as e:
                        print(f"[webapp] suppression fichiers échouée pour id={model_id} : {e}")
        elif data.action == "add_list":
            conn.execute(
                "INSERT OR IGNORE INTO model_lists (model_id, list_id) VALUES (?, ?)",
                (model_id, data.list_id),
            )
        elif data.action == "remove_list":
            conn.execute(
                "DELETE FROM model_lists WHERE model_id = ? AND list_id = ?",
                (model_id, data.list_id),
            )
        elif data.action == "set_printed":
            conn.execute(
                "UPDATE models SET printed = ? WHERE id = ?",
                (1 if data.printed else 0, model_id),
            )
        processed.append(model_id)

    conn.commit()
    conn.close()
    return {"processed": processed, "skipped": skipped}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_batch.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp.py tests/test_batch.py
git commit -m "feat(api): add batch actions endpoint for multi-select operations"
```

---

### Task 5: Extended filters/sort on `GET /api/models`, `printed` field, `GET /api/stats` additions

**Files:**
- Modify: `webapp.py`
- Test: `tests/test_models_filters.py`

**Interfaces:**
- Consumes: `_attach_lists` (Task 2), `deleted_at` exclusion pattern (Task 3).
- Produces: `GET /api/models` accepts `lists` (comma-separated ids, AND logic), `printed` (`"true"`/`"false"`), `sort` (one of `added_desc`, `added_asc`, `name_asc`, `name_desc`, `weight_desc`, `weight_asc`, `volume_desc`, `volume_asc` — default `added_desc`). `ModelUpdate` gains `printed: bool | None`. `GET /api/stats` response gains `trash_count: int` and `recent: list[dict]` (5 most recent non-deleted models, full model dicts).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_models_filters.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_models_filters.py -v`
Expected: FAIL — `sort`/`lists`/`printed` params ignored, `printed` not settable, `stats` missing new keys.

- [ ] **Step 3: Implement**

Add a module-level sort map in `webapp.py` (near the top, after imports):

```python
SORT_COLUMNS = {
    "added_desc": "added_at DESC",
    "added_asc": "added_at ASC",
    "name_asc": "name COLLATE NOCASE ASC",
    "name_desc": "name COLLATE NOCASE DESC",
    "weight_desc": "estimated_weight_g DESC",
    "weight_asc": "estimated_weight_g ASC",
    "volume_desc": "volume DESC",
    "volume_asc": "volume ASC",
}
```

Replace `ModelUpdate` (`webapp.py:135-140`):

```python
class ModelUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    material: str | None = None
    tags: str | None = None
    source_archive: str | None = None
    printed: bool | None = None
```

Replace `list_models` (as last written in Task 3) with:

```python
@app.get("/api/models")
def list_models(q: str = "", category: str = "", lists: str = "", printed: str = "", sort: str = "added_desc"):
    """Liste/recherche les modèles actifs (non supprimés), avec filtres combinés."""
    conn = get_conn()
    query = "SELECT * FROM models WHERE deleted_at IS NULL"
    params = []

    if q:
        query += " AND (name LIKE ? OR tags LIKE ? OR original_filename LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]

    if category:
        query += " AND category = ?"
        params.append(category)

    if lists:
        for list_id_str in lists.split(","):
            list_id_str = list_id_str.strip()
            if not list_id_str.isdigit():
                continue
            query += " AND id IN (SELECT model_id FROM model_lists WHERE list_id = ?)"
            params.append(int(list_id_str))

    if printed in ("true", "false"):
        query += " AND printed = ?"
        params.append(1 if printed == "true" else 0)

    query += " ORDER BY " + SORT_COLUMNS.get(sort, SORT_COLUMNS["added_desc"])

    rows = conn.execute(query, params).fetchall()
    models = [dict(r) for r in rows]
    _attach_lists(conn, models)
    conn.close()
    return models
```

Replace `get_stats` (`webapp.py:303-318`):

```python
@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) AS c FROM models WHERE deleted_at IS NULL").fetchone()["c"]
    total_weight = conn.execute(
        "SELECT COALESCE(SUM(estimated_weight_g), 0) AS w FROM models WHERE deleted_at IS NULL"
    ).fetchone()["w"]
    total_time = conn.execute(
        "SELECT COALESCE(SUM(estimated_print_time_h), 0) AS t FROM models WHERE deleted_at IS NULL"
    ).fetchone()["t"]
    trash_count = conn.execute(
        "SELECT COUNT(*) AS c FROM models WHERE deleted_at IS NOT NULL"
    ).fetchone()["c"]
    recent_rows = conn.execute(
        "SELECT * FROM models WHERE deleted_at IS NULL ORDER BY added_at DESC LIMIT 5"
    ).fetchall()
    recent = [dict(r) for r in recent_rows]
    _attach_lists(conn, recent)
    conn.close()
    return {
        "total_models": total,
        "total_weight_g": round(total_weight, 1),
        "total_print_time_h": round(total_time, 1),
        "trash_count": trash_count,
        "recent": recent,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_models_filters.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add webapp.py tests/test_models_filters.py
git commit -m "feat(api): add combined filters, sort options, and printed flag to GET /api/models"
```

---

### Task 6: `purge_trash.py` standalone script

**Files:**
- Create: `purge_trash.py`
- Test: `tests/test_purge_trash.py`

**Interfaces:**
- Consumes: `scanner.init_db(db_path)` (Task 1).
- Produces: `purge_trash.purge_expired(conn, retention_days: int, now: datetime | None = None) -> list[int]` (returns purged ids, tolerant of missing files, never raises on a single item's failure); `purge_trash.main(library: Path, retention_days: int | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_purge_trash.py
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import scanner
import purge_trash


def _make_db_with_trashed_models(tmp_path, now):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    conn.row_factory = sqlite3.Row

    old_dir = tmp_path / "old_model"
    old_dir.mkdir()
    (old_dir / "model.stl").write_bytes(b"fake")
    old_deleted_at = (now - timedelta(days=45)).isoformat()
    conn.execute(
        "INSERT INTO models (id, name, path, added_at, deleted_at) VALUES "
        "(1, 'Old', ?, '2025-01-01', ?)",
        (str(old_dir / "model.stl"), old_deleted_at),
    )

    recent_dir = tmp_path / "recent_model"
    recent_dir.mkdir()
    (recent_dir / "model.stl").write_bytes(b"fake")
    recent_deleted_at = (now - timedelta(days=5)).isoformat()
    conn.execute(
        "INSERT INTO models (id, name, path, added_at, deleted_at) VALUES "
        "(2, 'Recent', ?, '2025-01-01', ?)",
        (str(recent_dir / "model.stl"), recent_deleted_at),
    )

    conn.execute(
        "INSERT INTO models (id, name, path, added_at, deleted_at) VALUES "
        "(3, 'MissingFiles', '/already/gone/model.stl', '2025-01-01', ?)",
        ((now - timedelta(days=60)).isoformat(),),
    )

    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (4, 'Active', '/active', '2025-01-01')"
    )

    conn.commit()
    conn.close()
    return db_path


def test_purge_expired_removes_old_trashed_models_only():
    now = datetime(2026, 6, 1)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = _make_db_with_trashed_models(tmp_path, now)
        conn = scanner.init_db(db_path)
        conn.row_factory = sqlite3.Row

        purged = purge_trash.purge_expired(conn, retention_days=30, now=now)

        assert sorted(purged) == [1, 3]
        remaining_ids = {r["id"] for r in conn.execute("SELECT id FROM models")}
        assert remaining_ids == {2, 4}
        conn.close()


def test_purge_expired_removes_on_disk_files_for_purged_models():
    now = datetime(2026, 6, 1)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = _make_db_with_trashed_models(tmp_path, now)
        conn = scanner.init_db(db_path)
        conn.row_factory = sqlite3.Row

        purge_trash.purge_expired(conn, retention_days=30, now=now)

        assert not (tmp_path / "old_model").exists()
        assert (tmp_path / "recent_model").exists()
        conn.close()


def test_purge_expired_tolerates_already_missing_files_without_raising():
    now = datetime(2026, 6, 1)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = _make_db_with_trashed_models(tmp_path, now)
        conn = scanner.init_db(db_path)
        conn.row_factory = sqlite3.Row

        purged = purge_trash.purge_expired(conn, retention_days=30, now=now)  # ne doit pas lever

        assert 3 in purged  # MissingFiles a bien été purgé malgré l'absence de fichiers
        conn.close()


def test_main_returns_zero_when_db_missing(tmp_path):
    assert purge_trash.main(library=tmp_path / "nowhere") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_purge_trash.py -v`
Expected: FAIL — `purge_trash` module doesn't exist.

- [ ] **Step 3: Implement `purge_trash.py`**

```python
#!/usr/bin/env python3
"""
3D Library Manager - Purge de la corbeille
Appelé par le timer systemd `3d-library-purge.timer` (quotidien) : supprime
définitivement (fichiers + ligne DB) les modèles mis à la corbeille depuis
plus de TRASH_RETENTION_DAYS jours. Un item en échec (fichiers déjà absents,
erreur disque) ne doit jamais bloquer la purge des suivants.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from scanner import init_db

DEFAULT_LIBRARY = Path("~/3D_Library").expanduser()
DEFAULT_RETENTION_DAYS = 30


def _retention_days_from_env() -> int:
    try:
        return int(os.environ.get("TRASH_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS)))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def purge_expired(conn: sqlite3.Connection, retention_days: int, now: datetime | None = None) -> list[int]:
    """Supprime (fichiers + ligne DB) les modèles en corbeille depuis plus de
    `retention_days` jours. Renvoie les ids effectivement purgés. Une erreur
    sur un item (fichiers déjà absents, erreur disque) est loguée et ignorée
    plutôt que de bloquer les suivants."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=retention_days)
    rows = conn.execute(
        "SELECT id, path, deleted_at FROM models WHERE deleted_at IS NOT NULL"
    ).fetchall()

    purged = []
    for row in rows:
        if datetime.fromisoformat(row["deleted_at"]) > cutoff:
            continue
        try:
            folder = Path(row["path"]).parent
            if folder.exists():
                shutil.rmtree(folder)
        except OSError as e:
            print(f"[purge_trash] suppression fichiers échouée pour id={row['id']} : {e}", file=sys.stderr)
        conn.execute("DELETE FROM models WHERE id = ?", (row["id"],))
        purged.append(row["id"])

    conn.commit()
    return purged


def main(library: Path = DEFAULT_LIBRARY, retention_days: int | None = None) -> int:
    retention_days = retention_days if retention_days is not None else _retention_days_from_env()
    db_path = library / "library.db"
    if not db_path.exists():
        print(f"[purge_trash] base introuvable : {db_path}", file=sys.stderr)
        return 0

    conn = init_db(db_path)
    conn.row_factory = sqlite3.Row
    try:
        purged = purge_expired(conn, retention_days)
        print(f"[purge_trash] {len(purged)} modèle(s) purgé(s) définitivement : {purged}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Ne jamais laisser une exception faire échouer le timer systemd :
        # on logue et on sort proprement, la prochaine exécution retentera.
        print(f"[purge_trash] erreur inattendue : {e}", file=sys.stderr)
        sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_purge_trash.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add purge_trash.py tests/test_purge_trash.py
git commit -m "feat(trash): add purge_trash.py to permanently remove expired trashed models"
```

---

### Task 7: Systemd timer for automatic purge

**Files:**
- Create: `systemd/3d-library-purge.service`
- Create: `systemd/3d-library-purge.timer`

**Interfaces:**
- Consumes: `purge_trash.py` (Task 6) as the service's `ExecStart`.
- Produces: an installable systemd timer unit, following the exact pattern of `systemd/3d-library-watch.service` / `.timer`.

- [ ] **Step 1: Create the service unit**

```ini
# systemd/3d-library-purge.service
[Unit]
Description=Purge définitive des modèles en corbeille depuis plus de TRASH_RETENTION_DAYS jours

[Service]
Type=oneshot
Environment=TRASH_RETENTION_DAYS=30
ExecStart=/usr/bin/python3 %h/Documents/Code/3d/library/purge_trash.py
```

- [ ] **Step 2: Create the timer unit**

```ini
# systemd/3d-library-purge.timer
[Unit]
Description=Déclenche quotidiennement la purge de la corbeille (3d-library-purge.service)

[Timer]
OnCalendar=daily
Persistent=true
AccuracySec=1h

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Verify the units parse correctly**

Run: `systemd-analyze verify --user systemd/3d-library-purge.service systemd/3d-library-purge.timer`
Expected: no output (no errors). If `systemd-analyze` isn't on this machine, skip — the units follow the exact same shape as the already-deployed `3d-library-watch.*` units, so this step is a sanity check, not a hard requirement.

- [ ] **Step 4: Commit**

```bash
git add systemd/3d-library-purge.service systemd/3d-library-purge.timer
git commit -m "feat(trash): add systemd timer for daily trash purge"
```

---

## After this plan

The API surface described in `docs/superpowers/specs/2026-10-09-ui-overhaul-design.md`
is now complete and covered by pytest. The frontend plan
(`docs/superpowers/plans/2026-10-09-ui-overhaul-frontend.md`) consumes these
exact endpoints and response shapes — no further backend changes should be
needed to implement it. If the frontend work surfaces a gap in this API,
fix it here first (with a test) rather than working around it in the
frontend.
