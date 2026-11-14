# Journal des versions

## 2026-11-14 — pain d'épice contre le château (v2.9)

- `scene.gingerbread_castle` : scène 48×48 avec château 32×32, colosse
  pain d'épice (glaçage, boutons, visage, bras au sol), deux gardes,
  cuve de lait renversée, jet/flaque et petit pain d'épice sur l'épaule.
- `scene.gingerbread`, `gingerbread_mini`, `milk_vat`.
- Modèle : 4 765 pièces, 100 %, 1 amas, stabilité 0,90, score 0,94 A ;
  8 vues + notice + BOM + `source.json`.
- `--shape gingerbread` ; 10/10 formes valides ; tests 65.

## 2026-11-14 — composeur de scènes (v2.8)

- `tools/scene.py` : API `Scene` (sol, cottage, personnage, arbre, étang,
  étal, tonneau, lampe, mur de fond) + `village()`.
- `shapes.diorama` n'est plus codé en dur : il compose via `Scene`.
- Personnages 4 studs (épaules, mains, yeux, bouche) au lieu de 2×2.
- Village 1 453 pièces, 100 %, 1 amas, 8 vues, score 0,93 A.
- Tests : 64 passés (composeur + visage + scène).
- `source.json` : provenance du build (forme, options, pipeline) à côté du
  `.ldr`, comme le `.py` de BrickAgent. Steps, notice et BOM restent liés.

## 2026-11-14 — scènes et matières (v2.7)

- **Composants** : `report.components` (taille, rôle socle/module/prop,
  stabilité propre, ancrage) et `--max-components` (1 = objet, 2–6 = scène).
  `quality.validity/score` acceptent une scène si chaque composant est stable.
- **Studs exposés** : `--studs F` remplace une fraction des tuiles de sommet
  par des plaques (même empreinte, même hauteur) ; le village utilise 0,20
  par défaut. Couverture et stabilité inchangées.
- Tests : 61 passés ; village 1 279 pièces, 8 vues, score 0,94 A.

## 2026-11-14 — reprise de BrickBench (v2.6)

- Étude de la galerie `?s=set` et du papier arXiv:2610.12452 dans
  `docs/BRICKBENCH_SET_GALLERY.md` (100 prompts, 17 `.mpd` analysés).
- **Banc 8 vues** (`tools/views.py`, `--views`) : planche contact, vue
  frontale, occupation, symétrie, contour, contrôle « dos non vide ».
- **Garde-fous** (`quality.design_flags`) : type dominant > 60 %, 1×1
  > 40 %, tuiles > 50 %, composants > 10, plancher 400, socle vide.
- **Variété** (`quality.variety`) : types, entropie, part du type dominant.
- `quality.validity` accepte `max_components` (préparation des scènes).
- **Village (diorama)** : 1 279 pièces, deux cottages, place, étang,
  marché, arbres, personnages brick-built, mur de fond crénelé ; 8 vues
  et notice. Un « Set » 400–4 000 pièces sur plaque de base.

## 2026-11-14 — remaniement

- Pipeline v1 (solver CP-SAT, blueprint IR, templates, clients LLM) déplacé
  dans `archive/v1/`, avec ses tests et son mode d'emploi.
- Anciens modèles et rendus dans `archive/models/` et `archive/renders/`.
- `tools/` ne contient plus que le pipeline v2 et l'infrastructure partagée.
- `out/` nettoyé (367 Mo → 81 Mo) ; `renders/` vidé et ignoré.
- README recentré sur la v2 ; historique et documentation v1 dans
  `archive/README.md`.

## v2.5 — les deux verrous

- **Cheese slopes 2 plaques** : `54200`/`85984`/`15068` sur les marches de
  2 plaques, complément en 1×1, correction de l'origine LDraw
  (`_BOTTOM_ORIGIN`) et de l'empreinte à 180°.
- **SNOT réel** : bannières 1×2 verticales tenues par le tenon latéral d'une
  `4070`, matrice complète, collision, export LDraw, BOM. Couche de
  décoration ; la structure reste la grille verticale.
- `--no-snot`, rapport `snot_banners` / `snot_extras` / `pieces_total`.

## v2.4 — sets détaillés

- Plaque de base 32×32 (`3811`) quand l'empreinte correspond.
- Corbeaux (`_cover_overhangs`) et re-pavage local (`_repair_gaps`) pour les
  débords, mâchicoulis et tours rondes.
- Pièces rondes 1×1 isolées (`3062b`/`6141`/`98138`).
- Château (3 600+ pièces) et maison (900+ pièces) enrichis.
- Rendu LeoCAD : aplatissement des étapes pour afficher le modèle complet.

## v2.3 — vision et SNOT prototype

- Depth Anything V2 ONNX (`tools/depth_onnx.py`), masque `--mask`.
- Prototype SNOT 3D (`tools/snot.py`), sous-ensembles dans la notice.
- Rebrickable, LPub3D.

## v2.2 — pentes et PDF

- Pentes 45/33, tiles, fondation 2D, réparation des débords.
- LPub3D installé/testé, `--pdf`.
- Hauteurs par pièce (`part_levels`).

## v2.1 — surface

- Pentes et tiles, plaques 2D, sous-ensembles, familles de connecteurs.

## v2 — volume → briques

- Pipeline `voxel.py` → `brickify.py` → `studs.py`/`stability.py` → notice.
- Garanties BrickBench : pièces réelles, zéro collision, zéro pièce
  flottante, un seul composant, stabilité.
- Formes procédurales, BOM, notice HTML, serveur web.

## v1 — blueprint + CP-SAT (archivé)

- Blueprint sémantique, solver OR-Tools CP-SAT, templates, génération LLM
  one-shot/script. Conservé dans `archive/v1/`.
