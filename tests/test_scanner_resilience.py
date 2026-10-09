"""
Robustesse du scanner face aux erreurs non prévues par le chemin "heureux" :
trouvé lors de la revue finale de la branche auto-watcher. Avant ce fix,
seule zipfile.BadZipFile était rattrapée autour de l'extraction d'un ZIP,
et aucune exception n'était rattrapée autour de insert_model() pour les
fichiers isolés : une seule archive chiffrée, un ZIP Deflate64 (Windows
Explorer), ou une erreur disque/sqlite inattendue plantait tout le scan —
dans un watcher automatique sans surveillance humaine, un seul fichier
problématique bloque alors silencieusement tout le pipeline pour de bon.
"""

import sqlite3
import zipfile
from unittest.mock import patch

import pytest

import scanner


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(scanner.DB_SCHEMA)
    yield connection
    connection.close()


def _patch_pipeline(monkeypatch):
    monkeypatch.setattr(
        scanner, "analyze_stl",
        lambda path: {
            "size_x": 10.0, "size_y": 10.0, "size_z": 10.0,
            "volume": 1.0, "is_watertight": True, "material": "PLA",
            "estimated_weight_g": 1.0, "estimated_print_time_h": 0.1,
        },
    )
    monkeypatch.setattr(scanner, "auto_tag", lambda name, text: ("Atelier", ["test"]))
    monkeypatch.setattr(scanner, "f3d_is_available", lambda: False)


def test_extract_zip_translates_runtime_error_to_value_error(tmp_path):
    """Archive chiffrée : zipfile.extractall lève RuntimeError, pas BadZipFile."""
    zpath = tmp_path / "encrypted.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model.stl", "fake stl")

    with patch.object(zipfile.ZipFile, "extractall", side_effect=RuntimeError("Bad password")):
        with pytest.raises(ValueError):
            scanner.extract_zip(zpath, tmp_path / "extract_out")


def test_extract_zip_translates_not_implemented_error_to_value_error(tmp_path):
    """ZIP Deflate64 (Windows Explorer) : zipfile lève NotImplementedError."""
    zpath = tmp_path / "deflate64.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model.stl", "fake stl")

    with patch.object(zipfile.ZipFile, "extractall", side_effect=NotImplementedError("deflate64")):
        with pytest.raises(ValueError):
            scanner.extract_zip(zpath, tmp_path / "extract_out")


def test_scan_source_encrypted_zip_does_not_crash_whole_scan(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"

    bad_zip = source / "encrypted.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("model.stl", "fake stl")
    good_stl = source / "fine.stl"
    good_stl.write_text("fake stl content")

    with patch.object(zipfile.ZipFile, "extractall", side_effect=RuntimeError("Bad password")):
        stats = scanner.scan_source(source, library_root, conn)

    assert stats["errors"] == 1
    assert stats["added"] == 1  # le fichier isolé valide est bien traité malgré le zip cassé
    assert bad_zip.exists()  # laissé en place pour inspection manuelle
    assert not good_stl.exists()


def test_scan_source_unexpected_insert_model_error_does_not_crash_whole_scan(tmp_path, conn, monkeypatch):
    """
    Une erreur inattendue dans insert_model() (pas seulement un échec
    d'analyse géométrique, déjà géré) pour un fichier isolé ne doit pas
    empêcher le traitement des autres fichiers.
    """
    _patch_pipeline(monkeypatch)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"

    (source / "broken.stl").write_text("x")
    (source / "fine.stl").write_text("y")

    real_insert_model = scanner.insert_model

    def flaky_insert_model(conn, stl_path, source_archive, library_root):
        if stl_path.name == "broken.stl":
            raise OSError("disque plein (simulé)")
        return real_insert_model(conn, stl_path, source_archive, library_root)

    monkeypatch.setattr(scanner, "insert_model", flaky_insert_model)

    stats = scanner.scan_source(source, library_root, conn)

    assert stats["errors"] == 1
    assert stats["added"] == 1
    assert (source / "broken.stl").exists()  # laissé en place pour inspection
