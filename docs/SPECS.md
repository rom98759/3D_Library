# Projet : 3D Library Manager — Gestionnaire intelligent de fichiers 3D

## Objectif

Créer une bibliothèque personnelle intelligente pour organiser automatiquement tous tes fichiers d'impression 3D.

Aujourd'hui un dossier ressemble souvent à :

```
3D/
├── thingiverse_492837.zip
├── new_part_final_v3.stl
├── support_camera.zip
├── IMG_2025_model.stl
└── thing_839201/
```

Le gestionnaire transforme ça en une vraie base de connaissances :

```
3D Library

├── 🛠 Atelier
│   ├── Boîte à vis
│   ├── Support perceuse
│   └── Organisateur tournevis
│
├── 🏠 Maison
│   ├── Crochet mural
│   ├── Pied de meuble
│   └── Support téléphone
│
├── 🤖 Robotique
│   ├── Support servo SG90
│   ├── Châssis robot
│   └── Boîtier ESP32
│
└── 🔧 Pièces techniques
    ├── Adaptateur tube
    └── Entretoise
```

---

# Architecture

```
                 3D Library Manager

                         |
                         |
                  Scanner fichiers
                         |
        +----------------+----------------+
        |                                 |
 Extraction ZIP                    Fichier STL
        |                                 |
        v                                 v
 Nettoyage nom                 Analyse géométrie
        |                                 |
        +---------------+----------------+
                        |
                        v

                  Base SQLite

                        |
        +---------------+---------------+
        |                               |
   Interface Web                 Assistant IA
        |                               |
 Recherche                 "Trouve une boîte à vis"
```

---

# Fonctionnalités

## 1. Import automatique

Tu déposes :

```
3D/Downloads
└── thingiverse_123456.zip
```

Le système détecte :

```
Nouveau fichier détecté
↓
Extraction
↓
Recherche STL
↓
Analyse
↓
Ajout bibliothèque
```

Exemple :

```
support_batterie.zip

Contenu:
- support.stl
- README.txt
- image.png
- source.scad
```

Résultat :

```
Nom:
Support batterie

Type:
Pièce électronique

Tags:
#battery
#holder
#electronics
```

---

# 2. Analyse STL

Avec Python :

Bibliothèques :

* trimesh
* numpy
* open3d

Extraction :

```
Dimensions:
X : 85 mm
Y : 40 mm
Z : 22 mm

Volume:
32 cm³

Poids PLA:
41 g

Temps impression estimé:
2h15
```

Base :

```sql
CREATE TABLE models (
    id INTEGER PRIMARY KEY,
    name TEXT,
    path TEXT,
    size_x REAL,
    size_y REAL,
    size_z REAL,
    volume REAL,
    material TEXT,
    category TEXT
);
```

---

# 3. Génération miniature

Créer automatiquement une image :

```
support_servo.stl

        ↓

      rendu 3D

        ↓

preview.png
```

Solutions :

### Option simple

Blender en ligne de commande :

```
blender \
--background \
--python render_stl.py
```

### Option légère

OpenSCAD :

```
openscad \
--render \
model.scad
```

---

# 4. Reconnaissance IA

Le système analyse :

* nom du fichier
* forme
* image générée
* description éventuelle

Exemple :

Fichier :

```
thing_847392.stl
```

Image :

```
forme rectangulaire
trous de fixation
```

IA :

```
Probable :
Support mural

Tags :
wall_mount
holder
home
```

---

# 5. Recherche intelligente

Au lieu de :

```
CTRL+F
"tournevis"
```

Tu demandes :

> "Trouve-moi une pièce pour ranger mes tournevis"

L'IA cherche :

```
Recherche sémantique:

tournevis
↓
outil
↓
atelier
↓
rangement
↓
organisateur
```

Résultat :

```
3 résultats trouvés

1. Screwdriver holder
   12 emplacements
   180x80x30mm

2. Wall tool organizer
   fixation murale

3. Modular drawer system
```

---

# Stack technique

## Backend

Python

```
FastAPI
|
├── Scanner fichiers
├── Analyse STL
├── Base SQLite
├── IA
└── API REST
```

---

## Base de données

SQLite :

Tables :

```
models

id
filename
path
category
tags
dimensions
thumbnail


tags

id
name


collections

id
name
```

---

## Interface

Option simple :

Web :

```
FastAPI
+
React
+
Tailwind
```

Vue :

```
[Recherche................]

--------------------------------

🖼 preview

Support téléphone

Dimensions:
120x70x30 mm

Tags:
phone
desk
holder

[Ouvrir dossier]
[Imprimer]
```

---

# Version avec IA locale

Vu ton intérêt pour Ollama :

```
3D Library Manager

        |
        |
     Ollama

        |
   Llama 3 / Qwen

        |
Analyse description
Création tags
Recherche naturelle
```

Pour les images :

```
STL
 |
render PNG
 |
CLIP embedding
 |
base vectorielle
 |
recherche par image
```

Stack :

```
SQLite
+
ChromaDB
+
Ollama
+
CLIP
```

---

# Organisation automatique des fichiers

Le système peut aussi renommer :

Avant :

```
thingiverse_583929.zip
```

Après :

```
atelier/
└── rangement/
    └── organiseur_tournevis_12_emplacements/
        ├── model.stl
        ├── preview.png
        ├── metadata.json
        └── source.zip
```

---

# Fonction bonus intéressante

## Historique d'impression

Connecter ton Ender 3 V3 SE :

```
Modèle:
boite_vis.stl

Impressions:
3

Dernière impression:
22/07/2026

Temps total:
8h42

Filament:
PLA noir
312g
```

---

# Roadmap réaliste

## Version 1 (1 semaine)

✅ Scanner dossier
✅ Extraire ZIP
✅ Lire STL
✅ SQLite
✅ Interface web simple

---

## Version 2

✅ Miniatures
✅ Tags automatiques
✅ Renommage
✅ Recherche

---

## Version 3

✅ IA locale
✅ Recherche naturelle
✅ Similarité visuelle
✅ Statistiques impression

---


