import sqlite3
import zipfile
from pathlib import Path

import pytest

import scanner


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(scanner.DB_SCHEMA)
    yield connection
    connection.close()


def _patch_pipeline(monkeypatch, *, analysis_ok=True):
    """Isole scanner.py de trimesh/f3d : les tests ne valident pas le
    contenu réel des fichiers 3D, seulement la logique de routage par
    extension."""
    def fake_analyze_stl(path):
        if not analysis_ok:
            raise ValueError("fichier illisible")
        return {
            "size_x": 10.0, "size_y": 10.0, "size_z": 10.0,
            "volume": 1.0, "is_watertight": True, "material": "PLA",
            "estimated_weight_g": 1.0, "estimated_print_time_h": 0.1,
        }

    monkeypatch.setattr(scanner, "analyze_stl", fake_analyze_stl)
    monkeypatch.setattr(scanner, "auto_tag", lambda name, text: ("Atelier", ["test"]))
    monkeypatch.setattr(scanner, "f3d_is_available", lambda: False)


def test_find_stl_files_includes_3mf(tmp_path):
    (tmp_path / "a.stl").write_text("x")
    (tmp_path / "b.3mf").write_text("x")
    (tmp_path / "c.STL").write_text("x")
    (tmp_path / "d.3MF").write_text("x")
    (tmp_path / "e.pdf").write_text("x")

    found = {p.name for p in scanner.find_stl_files(tmp_path)}

    assert found == {"a.stl", "b.3mf", "c.STL", "d.3MF"}


def test_insert_model_names_file_by_extension(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    library_root = tmp_path / "library"
    source_3mf = tmp_path / "Support batterie.3mf"
    source_3mf.write_text("fake 3mf content")

    name, status = scanner.insert_model(conn, source_3mf, None, library_root)

    assert name is not None, status
    row = conn.execute("SELECT path FROM models WHERE name = ?", (name,)).fetchone()
    assert row[0].endswith("model.3mf")
    assert Path(row[0]).exists()


def test_insert_model_populates_tags_but_assigns_no_list(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    library_root = tmp_path / "library"
    source = tmp_path / "Support batterie.stl"
    source.write_text("fake stl content")

    name, status = scanner.insert_model(conn, source, None, library_root)

    assert name is not None, status
    row = conn.execute("SELECT tags FROM models WHERE name = ?", (name,)).fetchone()
    assert row[0] == "test"  # vient du auto_tag patché, pas de catégorie assignée en liste
    list_count = conn.execute("SELECT COUNT(*) FROM model_lists").fetchone()[0]
    assert list_count == 0


def test_scan_source_processes_loose_3mf_and_leaves_unrelated_files(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"
    (source / "piece.3mf").write_text("fake 3mf")
    (source / "notes.pdf").write_text("not a 3d file")

    stats = scanner.scan_source(source, library_root, conn)

    assert stats["added"] == 1
    assert stats["errors"] == 0
    # Le fichier non pertinent n'est ni déplacé ni supprimé.
    assert (source / "notes.pdf").exists()
    # Le fichier traité a quitté le dossier source : un ajout réussi (pas un
    # doublon) est déplacé directement par insert_model() vers models/,
    # jamais vers _originals/ (ce chemin ne sert qu'aux doublons ignorés).
    assert not (source / "piece.3mf").exists()
    assert list(library_root.glob("models/**/model.3mf"))


def test_scan_source_processes_3mf_inside_zip(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"

    zpath = source / "thing_12345.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model.3mf", "fake 3mf content")
        zf.writestr("README.txt", "info")

    stats = scanner.scan_source(source, library_root, conn)

    assert stats["added"] == 1
    assert stats["zips"] == 1
    assert stats["errors"] == 0
    rows = conn.execute("SELECT path FROM models").fetchall()
    assert rows[0][0].endswith("model.3mf")


def test_scan_source_corrupt_3mf_does_not_crash_whole_scan(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch, analysis_ok=False)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"
    (source / "broken.3mf").write_text("not really a 3mf")

    stats = scanner.scan_source(source, library_root, conn)

    # analyze_stl échoue, mais insert_model catche déjà l'exception (comme
    # pour un STL cassé) : le modèle est quand même catalogué avec des
    # champs d'analyse vides, le scan ne plante pas.
    assert stats["errors"] == 0
    assert stats["added"] == 1
    row = conn.execute("SELECT size_x, is_watertight FROM models").fetchone()
    assert row == (None, None)
