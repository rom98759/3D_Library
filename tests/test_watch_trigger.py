import os
import time
from pathlib import Path

import watch_trigger


def _age(path: Path, seconds_ago: float) -> None:
    t = time.time() - seconds_ago
    os.utime(path, (t, t))


def test_ready_to_scan_false_for_fresh_relevant_file(tmp_path):
    (tmp_path / "fresh.stl").write_text("x")

    assert watch_trigger.ready_to_scan(tmp_path, stable_seconds=10) is False


def test_ready_to_scan_true_once_relevant_file_old_enough(tmp_path):
    f = tmp_path / "old.stl"
    f.write_text("x")
    _age(f, 20)

    assert watch_trigger.ready_to_scan(tmp_path, stable_seconds=10) is True


def test_ready_to_scan_ignores_irrelevant_files_entirely(tmp_path):
    """
    Bug trouvé en revue finale : has_stable_entries() d'origine renvoyait
    True dès qu'UN SEUL fichier (n'importe lequel) était vieux de plus de
    stable_seconds — y compris un .pdf ou .gcode qui ne sera jamais
    consommé par le scanner. Un vieux fichier non pertinent qui traîne ne
    doit jamais, à lui seul, déclencher un scan.
    """
    old_pdf = tmp_path / "notice.pdf"
    old_pdf.write_text("x")
    _age(old_pdf, 20)

    assert watch_trigger.ready_to_scan(tmp_path, stable_seconds=10) is False


def test_ready_to_scan_waits_for_every_relevant_file_not_just_one(tmp_path):
    """
    Même bug, autre facette : si un vieux .stl stable coexiste avec un
    .stl tout juste déposé, l'ancienne logique aurait lancé le scan
    immédiatement à cause du fichier stable, traitant le fichier frais
    avant qu'il soit complet.
    """
    old_stl = tmp_path / "old.stl"
    old_stl.write_text("x")
    _age(old_stl, 20)
    (tmp_path / "fresh.stl").write_text("x")

    assert watch_trigger.ready_to_scan(tmp_path, stable_seconds=10) is False


def test_main_skips_scan_when_nothing_ever_becomes_ready(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    (source / "fresh.stl").write_text("x")
    library = tmp_path / "library"

    # Simule un fichier qui ne se stabilise jamais pendant toute la fenêtre
    # d'attente bornée (ex. téléchargement anormalement long) : main() doit
    # finir par abandonner sans scanner, plutôt que d'attendre indéfiniment.
    monkeypatch.setattr(watch_trigger, "ready_to_scan", lambda *a, **k: False)
    called = []
    monkeypatch.setattr(watch_trigger, "scan_source", lambda *a, **k: called.append(True))

    result = watch_trigger.main(source=source, library=library, poll_interval=0.01, max_polls=2)

    assert result == 0
    assert called == []


def test_main_scans_once_file_becomes_ready_during_the_same_run(tmp_path, monkeypatch):
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

    # Pas encore prêt aux deux premiers checks, prêt à partir du troisième
    # (et pour tout appel suivant, y compris la vérification finale post-boucle).
    call_count = {"n": 0}

    def fake_ready_to_scan(*a, **k):
        call_count["n"] += 1
        return call_count["n"] >= 3

    monkeypatch.setattr(watch_trigger, "ready_to_scan", fake_ready_to_scan)
    calls = []
    monkeypatch.setattr(
        watch_trigger, "scan_source",
        lambda source, library_root, conn, **k: calls.append(True) or {"added": 0},
    )

    result = watch_trigger.main(source=source, library=library, poll_interval=0.01, max_polls=5)

    assert result == 0
    assert calls == [True]


def test_main_runs_scan_when_ready_file_present(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    f = source / "old.stl"
    f.write_text("x")
    _age(f, 20)
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
