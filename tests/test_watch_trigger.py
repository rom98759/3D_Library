import os
import time
from pathlib import Path

import watch_trigger


def test_has_stable_entries_false_for_fresh_file(tmp_path):
    (tmp_path / "fresh.stl").write_text("x")

    assert watch_trigger.has_stable_entries(tmp_path, stable_seconds=10) is False


def test_has_stable_entries_true_once_old_enough(tmp_path):
    f = tmp_path / "old.stl"
    f.write_text("x")
    old_time = time.time() - 20
    os.utime(f, (old_time, old_time))

    assert watch_trigger.has_stable_entries(tmp_path, stable_seconds=10) is True


def test_main_skips_scan_when_nothing_stable(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    (source / "fresh.stl").write_text("x")
    library = tmp_path / "library"

    called = []
    monkeypatch.setattr(watch_trigger, "scan_source", lambda *a, **k: called.append(True))

    result = watch_trigger.main(source=source, library=library)

    assert result == 0
    assert called == []


def test_main_runs_scan_when_stable_file_present(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    f = source / "old.stl"
    f.write_text("x")
    old_time = time.time() - 20
    os.utime(f, (old_time, old_time))
    library = tmp_path / "library"

    calls = []
    monkeypatch.setattr(
        watch_trigger, "scan_source",
        lambda source, library_root, conn, **k: calls.append((source, library_root)) or {"added": 0},
    )

    result = watch_trigger.main(source=source, library=library)

    assert result == 0
    assert calls == [(source, library)]
    assert library.exists()  # init_db a bien créé le dossier bibliothèque


def test_main_returns_0_on_missing_source(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = watch_trigger.main(source=missing, library=tmp_path / "library")

    assert result == 0
