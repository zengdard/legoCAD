# text2legoCAD — génération de sets LEGO constructibles

Génère des sets LEGO à partir de texte, d'une image, d'un volume ou d'un
modèle LDraw existant, puis produit **une notice, une nomenclature et un
aperçu** — avec une garantie : chaque pièce est posée sur des studs, le
modèle tient en un bloc, l'ordre de montage est vérifié.

Le pipeline actif est **v2 — volume → briques** : texte (LLM
structure-as-code), image, `.vox.json`, `.ldr` ou forme procédurale. L'ancien
pipeline **v1** (blueprint sémantique + CP-SAT, templates, génération LLM
one-shot) est conservé dans [`archive/`](archive/README.md) mais n'est plus
maintenu.

La validité suit le contrat de **BrickBench** (brickben.ch, 2026) : pièces
réelles, zéro collision, zéro pièce flottante, **un seul composant**, stable.
Le benchmark local (`tools/bench.py`) donne **9/9 formes valides** à 100 %
de couverture en moins de 0,5 s par modèle (2,2 s pour le château de
3 662 pièces).

```
 forme / texte / image / .ldr
        │
        ▼
   volume de voxels (1 voxel = 1 stud × 1 plaque)      tools/voxel.py
        │
        ▼
   compilateur : cours de briques, appareillage,      tools/brickify.py
   support réel, tiles, réparation des îlots
        │
        ▼
   validation : graphe étud → tube, amas, stabilité   tools/studs.py
        │                                              tools/stability.py
        ▼
   .ldr + bom.csv/json + wanted_list.xml + notice.html + aperçu
```

```bash
pip install -r requirements.txt

# formes prêtes à l'emploi (sans LLM, sans réseau)
python3 tools/make_model.py --shape house --name maison
python3 tools/make_model.py --shape diorama --name village --views
python3 tools/make_model.py --shape diorama --name village2 --studs 0.35
python3 tools/make_model.py --shape diorama --name duo --max-components 2
python3 - <<'PY'
from scene import Scene
s = Scene(20); s.cottage(2, 2, 8, 6, "19", "320"); s.figure(12, 8)
s.build()   # -> VoxelGrid compilable
PY
python3 tools/make_model.py --shape rocket --name fusee --video

# importer un modèle existant ou une image
python3 tools/make_model.py --ldr models/mon_modele.ldr
python3 tools/make_model.py --image photo.jpg --name portrait
# depth réelle : Depth Anything V2 ONNX (téléchargé une fois)
python3 tools/snot.py --out out/snot_demo.ldr   # démo SNOT 3D
python3 tools/depth_onnx.py photo.jpg depth.png
python3 tools/depth_to_voxel.py --depth depth.png --color photo.jpg \
  --width 32 --out models/relief.vox.json
python3 tools/make_model.py --vox models/relief.vox.json --name relief
python3 tools/make_model.py --shape house --name maison
python3 tools/make_model.py --shape diorama --name village --views
python3 tools/make_model.py --shape diorama --name village2 --studs 0.35
python3 tools/make_model.py --shape diorama --name duo --max-components 2
python3 - <<'PY'
from scene import Scene
s = Scene(20); s.cottage(2, 2, 8, 6, "19", "320"); s.figure(12, 8)
s.build()   # -> VoxelGrid compilable
PY --pdf --rebrickable

# texte -> volume -> briques (nécessite une clé LLM)
export DEEPSEEK_API_KEY=sk-...
python3 tools/text_to_voxel.py "un château avec deux tours" --bricks
python3 tools/text_to_voxel.py "un vaisseau spatial" --reference ref.png --bricks

# serveur web
python3 web/server.py --port 8000
```

Sorties dans `out/web/<nom>/` : `*.ldr`, `preview.png` (LeoCAD) ou
`preview.svg`, `notice.html` (A4 imprimable), `*.bom.csv`, `*.bom.json`,
`*.wanted_list.xml`, `source.json` (provenance), `report.json` ; avec
`--views`, `views/` (8 PNG + `contact.png` + `views.json`).

**Pourquoi c'est constructible** — trois règles du compilateur :

1. un cours de briques n'est posé que si l'empreinte **ne s'élargit pas**
   (sinon la brique bloque le débord de la couche suivante) ;
2. les joints sont **décalés** d'un cours à l'autre (appareillage) et une
   pièce qui enjambe deux pièces du dessous est récompensée ;
3. une pièce n'est acceptée que si **au moins un de ses studs** repose sur
   une pièce déjà posée ; l'accolement latéral ne compte pas.

**v2.5 — les deux verrous.** Les **cheese slopes 2 plaques** sont actives :
la passe de pentes traite les marches de 2 plaques avec `54200`/`85984`/
`15068`, et corrige l'origine LDraw de ces pièces (modélisées par le bas,
elles flottaient d'une plaque). Le **SNOT** n'est plus un prototype : un
décorateur attache de vraies bannières 1×2 verticales à des briques 4070
(tenon latéral), avec matrice complète, contrôle de collision, export LDraw
et ligne de BOM. `--no-snot` désactive la couche.

**v2.4 — sets détaillés.** Le compilateur sait maintenant poser de vraies
pièces de détail sur les débords :

- **plaque de base 32×32/48×48** (3811/4186) quand l'empreinte le permet :
  le socle est une seule pièce, comme dans un set, et les rangées du
  soubassement sont reliées ;
- **passes de corbeaux** (`_cover_overhangs`) : une cellule en porte-à-faux
  qui n'a aucun appui vertical est d'abord couverte par une pièce posée
  **en travers** de l'appui (1×2, 1×4, 1×6, 2×N), exactement comme un
  corbeau de mâchicoulis ;
- **re-pavage local** (`_repair_gaps`) quand aucune pièce ne peut enjamber :
  les pièces du niveau autour du trou sont retirées puis re-pavées, avec
  restauration si le pavage échoue ;
- **pièces rondes** : un 1×1 isolé (merlon, tourelle, poteau) devient une
  pièce ronde réelle (`3062b`, `6141`, `98138`) — même empreinte, même
  hauteur, mais un crénelage et des tourelles qui ressemblent au jeu ;
- **SNOT décoratif** : bannières suspendues par tenon latéral (4070 + plaque
  1×2), sur les murs extérieurs du château ;
- **cheese slopes** : pentes 31° de 2 plaques sur les petites marches ;
- **formes enrichies** : château (enceinte, contreforts, mâchicoulis, tours
  rondes à toit conique, châtelet à trois tours, donjon à lanterne, cour
  vivante) et
  maison (colombages, fenêtres à volets, porche, cheminée, haie fleurie,
  jardin arboré) ; voiture et vaisseau ont reçu phares, galerie, bandes et
  trains d'atterrissage ;
- **rendu LeoCAD corrigé** : la CLI n'affiche que le premier pas d'un
  fichier à étapes ; l'aperçu rend une copie aplatie du modèle complet.

v2.3 avait apporté les pentes 45/33, les tiles, **Depth Anything V2 ONNX**
(image → depth → relief), le prototype **SNOT 3D**, les sous-ensembles dans
la notice et les intégrations Rebrickable/LPub3D.

Le détail de l'approche, l'état de l'art (BrickGPT, BrickWright, BrickNet,
BrickBench, StableLego) et la feuille de route sont dans
[`docs/APPROACH.md`](docs/APPROACH.md). L'historique et les productions des
versions précédentes sont dans [`archive/README.md`](archive/README.md).

---

## Installation

```bash
pip install Pillow onnxruntime openai   # + fastmcp pour le serveur MCP
# bibliothèque LDraw (CC BY 4.0, ~615 Mo, non incluse) :
mkdir ldraw && cd ldraw
curl -LO https://library.ldraw.org/library/updates/complete.zip && unzip complete.zip
# rendu : LeoCAD via Flatpak + ffmpeg
flatpak install org.leocad.LeoCAD   # + ffmpeg dans le PATH
```

`ldraw/` n'est nécessaire que pour importer des pièces LDraw arbitraires ou
pour le rendu LeoCAD. Le pipeline volume → briques → notice fonctionne avec
le seul `pieces_catalog.json` (et Pillow pour les images).

## Structure

| Fichier | Rôle |
|---|---|
| `tools/voxel.py` | grille de voxels (plaques), primitives, import ASCII/images/LDraw, nettoyage des couleurs |
| `tools/brickify.py` | compilateur volume → briques constructibles (cours, appareillage, support, tiles, réparation) |
| `tools/studs.py` | graphe de connexions réel étud → tube, amas, pièces faibles |
| `tools/stability.py` | stabilité : appui, porte-à-faux, basculement par joint |
| `tools/bom.py` | nomenclature pièce × couleur, exports CSV/JSON/BrickLink XML, disponibilité |
| `tools/instructions.py` | notice A4 : inventaire, étapes, pièces ajoutées, avertissements |
| `tools/preview_svg.py` | rendu isométrique SVG (aperçu + étapes) sans LeoCAD |
| `tools/make_model.py` | CLI : forme/volume/.ldr/image → tous les livrables |
| `tools/text_to_voxel.py` | texte → programme de volume (LLM) → volume, avec bac à sable |
| `tools/voxel_runner.py` | exécution bornée du script de volume |
| `tools/shapes.py` | formes procédurales : maison, village (diorama), château fort, fusée, vaisseau Classic Space, canard (mosaïque), voiture, sapin, brique, mosaïque |
| `tools/scene.py` | composeur de scènes : sol, cottage, personnage, arbre, étang, étal, mur de fond (`Scene`) |
| `tools/quality.py` | score multi-critères et contrôles |
| `tools/availability.py` | calibration de la disponibilité sur le corpus OMR |
| `tools/fetch_omr.py` | téléchargement reproductible d'un échantillon OMR |
| `tools/lcd.py` | rendu + nomenclature de modèles LeoCAD 0.7 (`.lcd`), galerie Classic Space |
| `tools/ldr_io.py` | import natif d'un `.ldr/.mpd` (conserve les pièces, poses axis-aligned) |
| `tools/slopes.py` | pentes 45°/33° (marches de 3 plaques) et cheese slopes 31° (2 plaques) |
| `tools/depth_to_voxel.py` | depth map / modèle de profondeur → relief 2.5D constructible |
| `tools/depth_onnx.py` | Depth Anything V2 (ONNX, 26 Mo) → depth map, sans PyTorch |
| `tools/snot.py` | SNOT : bannières 1×2 tenues par un tenon latéral (4070), frames de connecteurs, export LDraw |
| `tools/rebrickable.py` | vérification de disponibilité en ligne (API Rebrickable v3) |
| `tools/pdf_notice.py` | notice PDF via LPub3D (repli HTML) |
| `tools/bench.py` | benchmark validité / couverture / stabilité (inspiré de BrickBench) |
| `tools/views.py` | banc visuel 8 vues + planche contact + métriques de silhouette (protocole BrickBench) |
| `web/server.py`, `web/index.html` | générateur en ligne (stdlib, Docker) |
| `data/part_colors.json` | couples pièce/couleur observés dans 493 sets officiels |
| `data/bricklink_colors.json` | correspondance LDraw → BrickLink |
| `CHANGELOG.md` | journal des versions et du remaniement |

### Infrastructure partagée

| `tools/ldraw_model.py` | Générateur : grille de studs, collisions, steps, export `.ldr`, pièces SNOT hors grille. Accepte toute pièce LDraw |
| `tools/build_catalog.py` | Dimensions réelles des pièces curées → `pieces_catalog.json` |
| `tools/parts_index.py` | Index des ~23 000 pièces LDraw + cache |
| `tools/render.py` | Rendu headless LeoCAD (aperçu, steps, turntable) |
| `tools/mcp_server.py` | Serveur MCP v2 : sessions, recherche de pièces, génération, rendu |
| `archive/` | Pipeline v1, anciens modèles et rendus — voir [`archive/README.md`](archive/README.md) |
| `ldraw/` | Bibliothèque LDraw officielle (~25 000 pièces, non versionnée) |
| `models/` | Modèles de démonstration (`chateau.ldr`, `maison.ldr`) |
| `renders/` | Sorties de rendu locales (ignoré, sauf `.gitkeep`) |

## Ordre de montage

`tools/build_order.py` — les steps ne sont plus les blocs « auteur » du script
de génération (qui peut poser le toit avant les murs) mais un **ordre calculé** :

1. graphe de dépendance : une brique ne peut être posée qu'après celles qui la
   portent ou qui la bordent au même niveau ;
2. tri par vagues, de bas en haut puis de l'avant vers l'arrière (ordre de
   lecture d'une notice) ;
3. découpage en steps de taille raisonnable, briques voisines ensemble.

`plan()` produit la séquence, `validate()` vérifie que **chaque brique a un
appui déjà posé** à son tour (c'est l'I-score de Prompt-to-Parts : un humain
peut-il construire dans cet ordre ?), `apply()` réordonne le modèle et écrit
les `0 STEP` correspondants. La séquence est validée à chaque génération.

## Stabilité physique

`tools/stability.py` — trois contrôles, du plus grave au plus fin :

1. **Appui** : chaque brique doit atteindre le sol par une chaîne de connexions
   (support vertical **ou** accolement latéral — les studs tiennent, un plancher
   fixé à ses quatre coins est solide).
2. **Support direct** : fraction de l'empreinte réellement posée sur une brique
   du dessous.
3. **Basculement** : à chaque joint horizontal, le centre de gravité de la
   charge descendante doit tomber au-dessus de la zone de contact (critère
   d'équilibre des moments de Legolization, en version discrète).

Score : `1.0` = tout est posé, `0.8` = brique simplement accolée (décoratif,
toléré), `0.5` = un joint bascule, `0.0` = brique sans appui. Le harness exige
`min_stability >= 0.8` ; en dessous, le modèle reçoit un message de correction
détaillé (briques fautives et raison) et doit se corriger. C'est la métrique
`min_stability` (le maillon faible) qui compte, comme dans BrickGPT.

## Cadrage caméra

Tous les rendus (aperçu, frames de construction, rotation) calculent
automatiquement le cadre englobant le modèle (`render.frame_of`) : plus de
modèle minuscule ou hors champ. Le cadre est calculé une fois sur le modèle
final, donc la caméra reste stable pendant le timelapse.

## Usage B : serveur MCP

```bash
python3 tools/mcp_server.py            # stdio
python3 tools/mcp_server.py --http 8377
```

Configuration client MCP (ex. Claude Desktop / ZCode) :

```json
{"mcpServers": {"text2legocad": {
    "command": "python3",
    "args": ["/chemin/vers/legoCAD/tools/mcp_server.py"]}}}
```

Le LLM appelle ensuite, dans l'ordre : `session_start` → `search_parts`
("brick 2 x 4", "slope 45"...) pour trouver les ids exacts →
`session_add_part` brique par brique (une erreur de collision est renvoyée
immédiatement et se corrige à l'appel suivant) → `session_add_step` entre les
étapes → `session_screenshot` pour vérifier l'allure → `session_save` →
`render_video`.

C'est le même workflow itératif que le [MCP FreeCAD](https://github.com/neka-nat/freecad-mcp)
(actions petites + feedback visuel), adapté à LeoCAD qui n'a ni RPC interne ni
Python embarqué : la session vit dans le serveur MCP et le `.ldr` est réécrit
à chaque action.

Les outils one-shot (`list_parts`, `generate_model`, `render_preview`) restent
disponibles pour une génération en un seul appel.

## Format de spec (mode one-shot)

```json
{"name": "maison_rouge",
 "steps": [
   [{"part": "3020", "x": 0, "z": 0, "y": 0, "color": "7", "rot": 0}],
   [{"part": "3001", "x": 0, "z": 0, "y": 1, "color": "4", "rot": 0}]
 ]}
```

- `x`, `z` : position en studs du coin de la pièce (0 ou 90° de rotation).
- `y` : niveau vertical en **plaques** (1 brique = 3, 1 plaque = 1).
- `color` : code LDraw (`4` rouge, `1` bleu, `2` vert, `14` jaune, `15` blanc,
  `0` noir, `25` orange, `70` brun… — liste complète dans `list_parts`).

## Usage D : serveur web (`web/`)

Générateur complet dans le navigateur : formes, texte (LLM), import
`.ldr/.mpd` ou image. Chaque génération produit l'aperçu, la notice, le
`.ldr`, la nomenclature et la wanted list.

```bash
python3 web/server.py --host 127.0.0.1 --port 8000
# http://127.0.0.1:8000

# ou en conteneur (rendu SVG, sans LeoCAD)
docker compose up --build
```

En ligne, `LEGOCAD_NO_RENDER=1` désactive LeoCAD et utilise le rendu SVG
isométrique de `tools/preview_svg.py`, qui ne dépend d'aucune bibliothèque
graphique. Pour des rendus photoréalistes, garder LeoCAD côté machine hôte
(ou l'installer dans l'image) et monter `ldraw/`.

## Galerie Classic Space (référence réelle)

Le dossier `~/Téléchargements/clspace` contient les archives **LeoCAD 0.7**
des sets Classic Space 1978-1990 (marutan.net). LeoCAD 25 les ouvre encore
en headless : on en extrait un rendu et la **nomenclature réelle** (CSV), sans
interface graphique. Ils servent de référence de style, de proportions et de
palette — et de test pour la galerie.

```bash
python3 tools/lcd.py --gallery ~/Téléchargements/clspace \
  --sets "0497,6801,6929,6930,6950,6951,6970,6971,6972,6980,6985,6783"
# -> out/web/gallery/index.html + PNG + CSV + index.json
python3 web/server.py --port 8000   # puis /gallery
```

Le vaisseau `spaceship` de `tools/shapes.py` reprend cette grammaire
(gris/bleu, verrière trans-jaune `46`, réacteurs, ailerons, logo) dans un
volume constructible.

## Reprises de BrickBench (galerie « Set », 2026)

L'étude de la galerie <https://gallery.brickben.ch/?s=set> et du papier
[arXiv:2610.12452](https://arxiv.org/abs/2610.12452) est dans
[`docs/BRICKBENCH_SET_GALLERY.md`](docs/BRICKBENCH_SET_GALLERY.md). Ce qui
est déjà repris :

| Action | État | Où |
|---|---|---|
| **A8** banc 8 vues + planche + silhouette | **fait** | `tools/views.py`, `--views` |
| **A9** garde-fous anti-patterns | **fait** | `quality.design_flags` (`report.json`) |
| **A17** variété de pièces | **fait** | `quality.variety` (types, entropie, dominance) |
| **A10** notice + provenance | **déjà là** | steps, notice, BOM, wanted list |
| A1 scène multi-composants | à faire | `studs`/`quality` |
| A2 composeur de diorama | à faire | `scene.py` |
| A3 palette de détail | à faire | `pieces_catalog.json` |
| A4 personnages | à faire | `figures.py` |
| A5 props et végétation | à faire | `props.py` |
| A6 matières/textures | à faire | `brickify` |

```bash
python3 tools/views.py --ldr out/web/chateau/chateau.ldr --out out/web/chateau/views
python3 tools/make_model.py --shape house --name maison
python3 tools/make_model.py --shape diorama --name village --views
python3 tools/make_model.py --shape diorama --name village2 --studs 0.35
python3 tools/make_model.py --shape diorama --name duo --max-components 2
python3 - <<'PY'
from scene import Scene
s = Scene(20); s.cottage(2, 2, 8, 6, "19", "320"); s.figure(12, 8)
s.build()   # -> VoxelGrid compilable
PY --views
# -> views/contact.png, views/views.json, 8 PNG
```

Les métriques sont volontairement **descriptives** (`occupancy`, `symmetry`,
`contour`, `back_non_empty`) : un audit de design, pas un juge automatique.

`report.components` décrit chaque amas (taille, rôle socle/module/prop,
stabilité propre, ancrage). Un objet reste à 1 composant ; une scène peut en
accepter 2–6 avec `--max-components`. `--studs` remplace une fraction des
tuiles de sommet par des plaques pour exposer des tenons (texture).

## Score et validation

Chaque génération écrit `out/web/<nom>/report.json` avec :

- `coverage` (volume couvert), `islands` (amas), `unsupported`, `min_stability` ;
- `build_steps` et `build_errors` (ordre de montage) ;
- `bom.availability` (couples pièce/couleur observés) et `mix_similarity` ;
- un score global (`tools/quality.py`) et une note A/B/C/D.

Un modèle dont `islands > 1` ou `unsupported > 0` est signalé : il n'est pas
publiable en l'état. Le compilateur répare automatiquement les petits îlots
isolés (détails de surface) en les retirant et en recompilant.

## Tests

```bash
python3 -m pytest tests -q
```

Les tests couvrent le compilateur (couverture, collisions, appareillage,
formes qui s'élargissent), la physique (studs, tiles, accolement latéral),
les débords/corbeaux, les cheese slopes, le SNOT, les exports (BOM, XML),
la notice (SVG sans LeoCAD) et les formes de démo. Les tests du pipeline v1
sont dans `archive/v1/tests` (voir `archive/README.md`).

## Références

- [BrickGPT](https://avalovelace1.github.io/BrickGPT/) (ICCV 2025) — dataset
  StableText2Brick, stabilité physique, rollback.
- [BrickNet](https://kulits.github.io/BrickNet/) (CVPR 2026) — graphe de
  connecteurs (stud/hinge/axle/ball/fixed), 100 k objets LDraw.
- [BrickBench / BrickAgent](https://brickben.ch/) (2026) — benchmark
  agentique, métriques Valid/VQA/ELO, galerie de builds téléchargeables.
- [BrickWright](https://avalovelace1.github.io/brickwright/) (2026) —
  structure-as-code + validateur.
- [LDraw](https://www.ldraw.org/), [OMR](https://omr.ldraw.org/),
  [Rebrickable](https://rebrickable.com/), [BrickLink Studio](https://www.bricklink.com/v3/studio/download.page).
- [Classic Space (marutan.net)](https://www.marutan.net/arcsite/lego/index.php)
  — archive LeoCAD 0.7 utilisée pour la galerie de référence.

## Notes techniques


- LeoCAD est utilisé via Flatpak (`flatpak run org.leocad.LeoCAD`), rendu
  headless : `-i out.png --camera-angles <lat> <lon> -f 1 -t <n>` pour une
  image par step de construction.
- Y pointe vers le bas en LDraw : une pièce au niveau y a son centre à
  `-(y*8) - hauteur/2`.
- La détection de collision est voxelisée par cellule (stud × niveau plaque) ;
  les pièces en collision ou inconnues sont rejetées avec message (le client
  DeepSeek les retire et garde le reste).
- Licence : bibliothèque LDraw sous CC BY 4.0 (voir `ldraw/ldraw/CAlicense.txt`).
