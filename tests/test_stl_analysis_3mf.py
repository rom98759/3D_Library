"""
Test d'intégration réel (sans mock) pour l'analyse d'un .3mf : vérifie que
trimesh peut effectivement charger un .3mf avec les dépendances installées
(networkx + lxml, requises par le loader 3mf de trimesh en plus de la
dépendance trimesh elle-même déclarée dans requirements.txt). Découvert
pendant la migration du stock existant (Task 5) : sans ces deux paquets,
chaque .3mf était catalogué avec des champs d'analyse vides (dimensions,
volume, poids) au lieu des vraies valeurs géométriques.
"""

import zipfile
from pathlib import Path

from stl_analysis import analyze_stl

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""

# Cube 10x10x10 mm (volume attendu : 1000 mm3 = 1 cm3), étanche.
_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <resources>
  <object id="1" type="model">
   <mesh>
    <vertices>
     <vertex x="0" y="0" z="0"/>
     <vertex x="10" y="0" z="0"/>
     <vertex x="10" y="10" z="0"/>
     <vertex x="0" y="10" z="0"/>
     <vertex x="0" y="0" z="10"/>
     <vertex x="10" y="0" z="10"/>
     <vertex x="10" y="10" z="10"/>
     <vertex x="0" y="10" z="10"/>
    </vertices>
    <triangles>
     <triangle v1="0" v2="1" v3="2"/>
     <triangle v1="0" v2="2" v3="3"/>
     <triangle v1="4" v2="6" v3="5"/>
     <triangle v1="4" v2="7" v3="6"/>
     <triangle v1="0" v2="5" v3="1"/>
     <triangle v1="0" v2="4" v3="5"/>
     <triangle v1="1" v2="6" v3="2"/>
     <triangle v1="1" v2="5" v3="6"/>
     <triangle v1="2" v2="7" v3="3"/>
     <triangle v1="2" v2="6" v3="7"/>
     <triangle v1="3" v2="4" v3="0"/>
     <triangle v1="3" v2="7" v3="4"/>
    </triangles>
   </mesh>
  </object>
 </resources>
 <build>
  <item objectid="1"/>
 </build>
</model>"""


def _write_minimal_3mf_cube(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("3D/3dmodel.model", _MODEL)


def test_analyze_stl_reads_real_3mf_geometry(tmp_path):
    cube_3mf = tmp_path / "cube.3mf"
    _write_minimal_3mf_cube(cube_3mf)

    result = analyze_stl(cube_3mf)

    assert result["is_watertight"] is True
    assert result["volume"] == 1.0  # 10x10x10mm = 1000mm3 = 1cm3
    assert result["size_x"] == 10.0
    assert result["size_y"] == 10.0
    assert result["size_z"] == 10.0
