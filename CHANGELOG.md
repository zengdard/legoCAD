# Journal des versions

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
