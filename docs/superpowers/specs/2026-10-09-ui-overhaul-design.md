# Refonte de l'interface — Listes, corbeille, tri/filtre, React

## Contexte et objectif

L'interface actuelle (`static/index.html`, vanilla JS + Three.js) est une grille
plate de modèles avec une seule recherche texte. L'objectif est une interface
qui serve réellement l'usage quotidien :

- Vue d'ensemble (où j'en suis, derniers téléchargements)
- Organisation manuelle en listes libres (classer, ranger)
- Tri et filtres combinés (trier)
- Sélection multiple pour agir en masse (réarranger)
- Suppression réelle avec corbeille à purge différée (supprimer en faisant le tri)

La catégorie auto-détectée (`category`, via `auto_tag.py`) est remplacée comme
mécanisme de rangement par un système de listes manuelles. `auto_tag.py` est
conservé uniquement pour les **tags** de recherche (mots-clés libres,
`EXTRA_TAG_KEYWORDS` + mots-clés de catégorie convertis en tags) — il n'assigne
plus aucune liste automatiquement.

## Modèle de données

Migration additive sur la base SQLite existante (`scanner.py` / `webapp.py`).

```sql
CREATE TABLE lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE model_lists (
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    PRIMARY KEY (model_id, list_id)
);

ALTER TABLE models ADD COLUMN deleted_at TEXT;   -- NULL = actif, sinon horodatage de mise en corbeille
ALTER TABLE models ADD COLUMN printed INTEGER DEFAULT 0;
```

- `category` (colonne existante) : conservée en base pour compatibilité mais
  plus utilisée par l'UI ni par le scanner pour créer des associations. Elle
  peut rester NULL/inutilisée pour les nouveaux modèles.
- `tags` (colonne existante) : continue d'être alimentée par `auto_tag.py` au
  scan, inchangé.
- Toutes les requêtes "normales" de l'API filtrent `deleted_at IS NULL` par défaut.

## Scanner (`scanner.py`)

- Au moment de l'insertion (`insert_model`), `auto_tag()` est toujours appelé
  mais seul le retour `tags` est utilisé pour peupler la colonne `tags`. Le
  retour `category` n'est plus utilisé pour créer/assigner une liste.
- Aucune liste n'est créée automatiquement : un nouveau modèle scanné
  n'appartient à aucune liste tant que l'utilisateur ne l'y ajoute pas.

## API (`webapp.py`)

### Listes
- `GET /api/lists` — toutes les listes, avec compteur de modèles actifs (`deleted_at IS NULL`)
- `POST /api/lists` `{name}` — créer (409 si le nom existe déjà)
- `PUT /api/lists/{id}` `{name}` — renommer
- `DELETE /api/lists/{id}` — supprime la liste et ses associations `model_lists` (ne touche à aucun modèle)

### Appartenance aux listes
- `PUT /api/models/{id}/lists` `{list_ids: [int, ...]}` — remplace l'ensemble des listes du modèle (diff interne : ajoute les nouvelles associations, retire celles qui ne sont plus dans `list_ids`)

### Corbeille
- `POST /api/models/{id}/trash` — soft delete (`deleted_at = now`), reste en base avec son fichier
- `POST /api/models/{id}/restore` — annule (`deleted_at = NULL`)
- `DELETE /api/models/{id}` — suppression définitive immédiate : supprime le dossier du modèle sur disque (si présent — sinon log warning, pas d'erreur) puis la ligne DB (cascade sur `model_lists`)
- `GET /api/trash` — modèles avec `deleted_at IS NOT NULL`, triés par date de mise en corbeille, avec date de purge prévue (`deleted_at + TRASH_RETENTION_DAYS`)

### Batch
- `POST /api/models/batch` `{ids: [int,...], action: "trash"|"restore"|"delete"|"add_list"|"remove_list"|"set_printed", list_id?: int, printed?: bool}`
- Les ids invalides ou introuvables sont ignorés silencieusement ; la réponse détaille `{processed: [...], skipped: [...]}`.

### Vues existantes étendues
- `GET /api/models` — nouveaux query params :
  - `lists=1,2` → ET logique (modèle doit appartenir à toutes les listes citées)
  - `printed=true|false`
  - `sort=added_desc|added_asc|name_asc|name_desc|weight_desc|weight_asc|volume_desc|volume_asc`
  - `q` (existant, recherche texte sur nom/tags/fichier d'origine) — se combine avec les filtres ci-dessus
  - `deleted_at IS NULL` toujours implicite (la corbeille passe par `/api/trash`)
- `GET /api/stats` — ajoute `trash_count` et `recent` (5 derniers modèles par `added_at`)
- `PUT /api/models/{id}` (existant) — ajoute `printed` aux champs éditables (nom, catégorie legacy, matériau, tags restent inchangés)

## Purge automatique de la corbeille

- Nouveau script `purge_trash.py`, même pattern que `watch_trigger.py` :
  - Lit `TRASH_RETENTION_DAYS` (variable d'env, défaut `30`)
  - Sélectionne les modèles avec `deleted_at < now - TRASH_RETENTION_DAYS`
  - Supprime le dossier sur disque (tolérant si absent) puis la ligne DB
  - Logue chaque suppression (réutilise `scan_log` ou un nouveau `trash_log`)
  - Continue le traitement du lot même si un item échoue (pas d'arrêt sur erreur)
- Nouveau timer systemd `3d-library-purge.timer` (déclenchement quotidien) +
  `3d-library-purge.service`, posés à côté des unités existantes dans `systemd/`.

## Frontend

**Stack** : React + TypeScript + Vite + Tailwind. Build statique (`npm run build`)
servi par FastAPI à la place de `static/index.html` actuel — pas de serveur
Node en production, pas de SSR.

**Navigation** : sidebar persistante à gauche (toujours visible) —
logo/titre, lien Accueil, lien Bibliothèque, puis la liste des listes
(avec compteur) cliquables, puis le lien Corbeille. Cliquer une liste dans la
sidebar ouvre la Bibliothèque pré-filtrée sur cette liste.

**Écran Accueil**
- Bandeau stats : modèles, poids est., temps d'impression est. (comme aujourd'hui)
- Section "Derniers téléchargements" : rangée horizontale scrollable des 5
  derniers modèles ajoutés (thumbnail, nom, date relative, badge "nouveau"
  pour les ajouts très récents)
- Section "Mes listes" : grille de cards par liste (nom, compteur, mini-aperçus
  de thumbnails), clic → Bibliothèque filtrée sur cette liste

**Écran Bibliothèque**
- Barre d'outils : recherche texte, chips de filtre combinables (listes +
  statut imprimé/non imprimé — multi-sélection, ET logique), sélecteur de tri
  (date d'ajout ↑/↓, nom A→Z/Z→A, poids, volume), toggle mode d'affichage
  grille/liste, bouton Corbeille
- **Mode grille** : cards reprenant le style actuel (thumbnail ou diagramme de
  dimensions SVG, badge QC watertight) + checkbox de sélection, pills cyan pour
  les listes d'appartenance, date d'ajout affichée, badge "imprimé" si applicable.
  Les tags auto ne sont pas affichés sur la card (réservés à la recherche et à
  la fiche détail).
- **Mode liste** : tableau compact, colonnes triables (nom, listes, poids,
  volume, date d'ajout, imprimé), même logique de sélection par checkbox.
- **Barre d'actions flottante** (apparaît dès qu'au moins 1 modèle est
  sélectionné, boutons de taille uniforme) : Ajouter à une liste / Marquer
  imprimé / Mettre à la corbeille / Supprimer définitivement (rouge au survol)
  / Annuler la sélection.
- **Vue Corbeille** (bouton dédié) : mêmes modes grille/liste, affiche la date
  de purge prévue par modèle, actions = Restaurer / Supprimer définitivement.

**Fiche détail** (overlay repris de l'existant, viewer 3D Three.js inchangé) :
dans la zone d'édition, ajout de chips de listes cochables (coché = appartient,
clic = toggle) et d'un toggle "Imprimé". Les champs nom/matériau/tags existants
restent éditables tel quel.

**Identité visuelle** : conservée (fond grille bleu profond, Oswald/JetBrains
Mono/Work Sans, accents cyan #6FC7DA / jaune #F2C14E), traduite en composants
React + classes Tailwind — pas de refonte esthétique, uniquement structurelle
et fonctionnelle. Layout et interactions validés avec le compagnon visuel de
brainstorming (maquettes conservées dans `.superpowers/brainstorm/`, non
commitées).

## Gestion d'erreurs

- Suppression (définitive ou purge) d'un modèle dont le fichier/dossier a
  disparu du disque : on supprime quand même la ligne DB, on logue un
  avertissement, pas d'erreur bloquante côté API.
- `purge_trash.py` : un item en échec n'interrompt pas le traitement du reste
  du lot.
- `DELETE /api/lists/{id}` sur une liste encore utilisée : autorisé sans
  confirmation bloquante côté API (ce n'est qu'une association M2M) ; le
  frontend peut demander confirmation si la liste contient des modèles.
- `POST /api/models/batch` sur des ids invalides/déjà supprimés : ignorés
  silencieusement, détaillés dans la réponse (`processed`/`skipped`), le reste
  du lot est traité normalement.

## Tests

**Backend (pytest, existant)** — nouveaux tests pour :
- CRUD `lists` et association `model_lists`
- Corbeille : trash / restore / delete définitif, visibilité dans `/api/models` vs `/api/trash`
- `purge_trash.py` avec `TRASH_RETENTION_DAYS` mocké (pattern similaire à `test_watch_trigger.py`)
- Endpoint batch : succès partiel, ids invalides
- Tri et filtres combinés sur `GET /api/models` (listes multiples, printed, sort)

**Frontend** : pas de suite de tests JS automatisée pour ce chantier (cohérent
avec l'absence de tests sur `static/index.html` actuel). Vérification manuelle
dans le navigateur à chaque étape. Vitest + React Testing Library pourra être
introduit plus tard si le besoin se confirme.

## Hors périmètre (pour ce chantier)

- Historique des impressions détaillé / `print_count` (reste tel quel, non exposé dans l'UI)
- IA locale / recherche sémantique (V3 du SPECS.md original, non traité ici)
- Suite de tests frontend automatisée
