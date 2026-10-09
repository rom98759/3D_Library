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


def test_main_skips_scan_when_nothing_ever_becomes_stable(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    (source / "fresh.stl").write_text("x")
    library = tmp_path / "library"

    # Simule un fichier qui ne se stabilise jamais pendant toute la fenêtre
    # d'attente bornée (ex. téléchargement anormalement long) : main() doit
    # finir par abandonner sans scanner, plutôt que d'attendre indéfiniment.
    monkeypatch.setattr(watch_trigger, "has_stable_entries", lambda *a, **k: False)
    called = []
    monkeypatch.setattr(watch_trigger, "scan_source", lambda *a, **k: called.append(True))

    result = watch_trigger.main(source=source, library=library, poll_interval=0.01, max_polls=2)

    assert result == 0
    assert called == []


def test_main_scans_once_file_becomes_stable_during_the_same_run(tmp_path, monkeypatch):
    """
    Reproduit le bug trouvé lors de la validation de bout en bout : un
    `systemd --user path unit` ne se redéclenche que sur un NOUVEL événement
    inotify. Si un seul fichier est déposé et que rien d'autre ne change
    ensuite dans ~/3D, aucun second événement n'arrivera jamais — le fichier
    doit donc être traité en attendant sa stabilité DANS la même exécution,
    jamais en comptant sur un futur événement externe.
    """
    source = tmp_path / "3D"
    source.mkdir()
    (source / "downloading.stl").write_text("x")
    library = tmp_path / "library"

    # Pas encore stable aux deux premiers checks, stable à partir du troisième
    # (et pour tout appel suivant, y compris la vérification finale post-boucle).
    call_count = {"n": 0}

    def fake_has_stable_entries(*a, **k):
        call_count["n"] += 1
        return call_count["n"] >= 3

    monkeypatch.setattr(watch_trigger, "has_stable_entries", fake_has_stable_entries)
    calls = []
    monkeypatch.setattr(
        watch_trigger, "scan_source",
        lambda source, library_root, conn, **k: calls.append(True) or {"added": 0},
    )

    result = watch_trigger.main(source=source, library=library, poll_interval=0.01, max_polls=5)

    assert result == 0
    assert calls == [True]


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
