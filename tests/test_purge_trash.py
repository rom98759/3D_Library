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
