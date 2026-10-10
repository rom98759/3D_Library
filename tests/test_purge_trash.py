import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import scanner
import purge_trash


def _make_db_with_trashed_models(tmp_path, now):
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    conn.row_factory = sqlite3.Row

    # Les chemins réels produits par scanner.py sont toujours sous
    # <bibliothèque>/models/... — on reproduit cette structure pour que le
    # garde-fou de suppression (purge_trash._is_within_library_models)
    # s'applique comme en production.
    old_dir = tmp_path / "models" / "old_model"
    old_dir.mkdir(parents=True)
    (old_dir / "model.stl").write_bytes(b"fake")
    old_deleted_at = (now - timedelta(days=45)).isoformat()
    conn.execute(
        "INSERT INTO models (id, name, path, added_at, deleted_at) VALUES "
        "(1, 'Old', ?, '2025-01-01', ?)",
        (str(old_dir / "model.stl"), old_deleted_at),
    )

    recent_dir = tmp_path / "models" / "recent_model"
    recent_dir.mkdir(parents=True)
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

        assert not (tmp_path / "models" / "old_model").exists()
        assert (tmp_path / "models" / "recent_model").exists()
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


def test_purge_expired_never_rmtrees_outside_library_root():
    now = datetime(2026, 6, 1)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "library.db"
        conn = scanner.init_db(db_path)
        conn.row_factory = sqlite3.Row
        outside_dir = tmp_path / "outside_the_library"
        outside_dir.mkdir()
        (outside_dir / "model.stl").write_bytes(b"fake")
        conn.execute(
            "INSERT INTO models (id, name, path, added_at, deleted_at) VALUES "
            "(1, 'Outside', ?, '2025-01-01', ?)",
            (str(outside_dir / "model.stl"), (now - timedelta(days=45)).isoformat()),
        )
        conn.commit()

        purged = purge_trash.purge_expired(conn, retention_days=30, now=now)

        assert purged == [1]  # la ligne DB disparaît quand même
        assert outside_dir.exists()  # jamais supprimé : hors de <library>/models
        conn.close()


def test_purge_expired_keeps_db_row_when_rmtree_fails_for_a_real_reason(tmp_path, monkeypatch):
    # Utilise le fixture tmp_path de pytest (nettoyage différé, hors de ce
    # test) plutôt que tempfile.TemporaryDirectory : on va rendre shutil.rmtree
    # défaillant pour toute la durée du test, et un `with` manuel appellerait
    # lui-même rmtree pendant son __exit__, avant que monkeypatch ne restaure
    # l'original.
    now = datetime(2026, 6, 1)
    db_path = tmp_path / "library.db"
    conn = scanner.init_db(db_path)
    conn.row_factory = sqlite3.Row
    model_dir = tmp_path / "models" / "stuck_model"
    model_dir.mkdir(parents=True)
    (model_dir / "model.stl").write_bytes(b"fake")
    conn.execute(
        "INSERT INTO models (id, name, path, added_at, deleted_at) VALUES "
        "(1, 'Stuck', ?, '2025-01-01', ?)",
        (str(model_dir / "model.stl"), (now - timedelta(days=45)).isoformat()),
    )
    conn.commit()

    def _boom(path):
        raise OSError("disque verrouillé")

    monkeypatch.setattr(purge_trash.shutil, "rmtree", _boom)

    purged = purge_trash.purge_expired(conn, retention_days=30, now=now)

    assert purged == []  # échec disque réel : on retentera au prochain passage
    remaining_ids = {r["id"] for r in conn.execute("SELECT id FROM models")}
    assert remaining_ids == {1}
    conn.close()


def test_purge_expired_skips_a_malformed_deleted_at_without_crashing_the_batch():
    now = datetime(2026, 6, 1)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = _make_db_with_trashed_models(tmp_path, now)
        conn = scanner.init_db(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE models SET deleted_at = 'not-a-date' WHERE id = 1")
        conn.commit()

        purged = purge_trash.purge_expired(conn, retention_days=30, now=now)

        assert 1 not in purged  # ligne malformée ignorée, pas de crash
        assert 3 in purged  # le reste du lot est traité normalement
        remaining_ids = {r["id"] for r in conn.execute("SELECT id FROM models")}
        assert 1 in remaining_ids  # laissée en place pour inspection manuelle
        conn.close()
