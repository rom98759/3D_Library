import sqlite3

import pytest

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


def test_lists_name_unique_index_rejects_case_variant_at_db_level(tmp_path):
    conn = scanner.init_db(tmp_path / "library.db")
    conn.execute("INSERT INTO lists (name, created_at) VALUES ('Atelier', '2026-01-01')")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO lists (name, created_at) VALUES ('atelier', '2026-01-01')")
    conn.close()
