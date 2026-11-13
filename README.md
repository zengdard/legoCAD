# text2legoCAD — génération de sets LEGO constructibles

Génère des sets LEGO à partir de texte, d'une image, d'un volume ou d'un
modèle LDraw existant, puis produit **une notice, une nomenclature et un
aperçu** — avec une garantie : chaque pièce est posée sur des studs, le
modèle tient en un bloc, l'ordre de montage est vérifié.

Deux pipelines coexistent :

| Pipeline | Entrée | Quand l'utiliser |
|---|---|---|
| **v2 — volume → briques** (recommandé) | texte (LLM structure-as-code), image, `.vox.json`, `.ldr`, formes procédurales | modèles réels, notice, web |
| v1 — blueprint sémantique + CP-SAT | blueprint JSON (murs/boîtes/tours) | recherche sur le solver, expérimentation |

La validité suit le contrat de **BrickBench** (brickben.ch, 2026) : pièces
réelles, zéro collision, zéro pièce flottante, **un seul composant**, stable.
Le benchmark local (`tools/bench.py`) donne **7/7 formes valides** à 100 %
de couverture en moins de 0,15 s par modèle.

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
python3 tools/make_model.py --shape rocket --name fusee --video

# importer un modèle existant ou une image
python3 tools/make_model.py --ldr models/mon_modele.ldr
python3 tools/make_model.py --image photo.jpg --name portrait
# depth réelle : Depth Anything V2 ONNX (téléchargé une fois)
python3 tools/depth_onnx.py photo.jpg depth.png
python3 tools/depth_to_voxel.py --depth depth.png --color photo.jpg \
  --width 32 --out models/relief.vox.json
python3 tools/make_model.py --vox models/relief.vox.json --name relief
python3 tools/make_model.py --shape house --name maison --pdf --rebrickable

# texte -> volume -> briques (nécessite une clé LLM)
export DEEPSEEK_API_KEY=sk-...
python3 tools/text_to_voxel.py "un château avec deux tours" --bricks
python3 tools/text_to_voxel.py "un vaisseau spatial" --reference ref.png --bricks

# serveur web
python3 web/server.py --port 8000
```

Sorties dans `out/web/<nom>/` : `*.ldr`, `preview.png` (LeoCAD) ou
`preview.svg` (rendu isométrique sans dépendance), `notice.html` (A4
imprimable), `*.bom.csv`, `*.bom.json`, `*.wanted_list.xml`, `report.json`.

**Pourquoi c'est constructible** — trois règles du compilateur :

1. un cours de briques n'est posé que si l'empreinte **ne s'élargit pas**
   (sinon la brique bloque le débord de la couche suivante) ;
2. les joints sont **décalés** d'un cours à l'autre (appareillage) et une
   pièce qui enjambe deux pièces du dessous est récompensée ;
3. une pièce n'est acceptée que si **au moins un de ses studs** repose sur
   une pièce déjà posée ; l'accolement latéral ne compte pas.

**v2.2** ajoute les pentes 45/33 et les tiles (toits/carrosseries), les
plaques 2D 4×4/4×8 (débords et liaisons), la réparation des débords,
**Depth Anything V2 ONNX** (image → depth → relief constructible), les
sous-ensembles/chapitres dans la notice, les familles de connecteurs
(stud/SNOT/Technic/hinge) et les intégrations Rebrickable/LPub3D. LPub3D a
été installé et testé (PDF de 24 pages pour la maison).

Le détail de l'approche, l'état de l'art (BrickGPT, BrickWright, BrickNet,
BrickBench, StableLego) et la feuille de route sont dans
[`docs/APPROACH.md`](docs/APPROACH.md).

---

## Installation

```bash
pip install ortools openai fastmcp pillow
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
| `tools/shapes.py` | formes procédurales : maison, fusée, vaisseau Classic Space, canard (mosaïque), voiture, sapin, brique, mosaïque |
| `tools/quality.py` | score multi-critères et contrôles |
| `tools/availability.py` | calibration de la disponibilité sur le corpus OMR |
| `tools/fetch_omr.py` | téléchargement reproductible d'un échantillon OMR |
| `tools/lcd.py` | rendu + nomenclature de modèles LeoCAD 0.7 (`.lcd`), galerie Classic Space |
| `tools/ldr_io.py` | import natif d'un `.ldr/.mpd` (conserve les pièces, poses axis-aligned) |
| `tools/slopes.py` | pentes 45°/33° sur les marches de 3 plaques (toits, capots) |
| `tools/depth_to_voxel.py` | depth map / modèle de profondeur → relief 2.5D constructible |
| `tools/depth_onnx.py` | Depth Anything V2 (ONNX, 26 Mo) → depth map, sans PyTorch |
| `tools/rebrickable.py` | vérification de disponibilité en ligne (API Rebrickable v3) |
| `tools/pdf_notice.py` | notice PDF via LPub3D (repli HTML) |
| `tools/bench.py` | benchmark validité / couverture / stabilité (inspiré de BrickBench) |
| `web/server.py`, `web/index.html` | générateur en ligne (stdlib, Docker) |
| `data/part_colors.json` | couples pièce/couleur observés dans 493 sets officiels |
| `data/bricklink_colors.json` | correspondance LDraw → BrickLink |

### Modules hérités (pipeline v1, toujours disponibles)

| `tools/build_catalog.py` | Extrait les dimensions réelles des pièces curées depuis la bibliothèque LDraw officielle → `pieces_catalog.json` |
| `tools/parts_index.py` | Index des ~23 000 pièces de la bibliothèque complète (descriptions, familles, hauteurs) + cache `parts_index_cache.json` |
| `tools/arch.py` | Primitives d'architecture : toits à deux pans, toits pyramidaux, créneaux, escaliers |
| `tools/ldraw_model.py` | Générateur : grille de studs, détection de collision, steps, export `.ldr`. Accepte toute pièce LDraw, pas seulement le catalogue curé |
| `tools/render.py` | Rendu headless LeoCAD (aperçu, steps, turntable) + assemblage FFmpeg |
| `tools/mcp_server.py` | Serveur MCP : session itérative (`session_*`), recherche (`search_parts`, `get_part`), one-shot (`generate_model`), rendu (`render_preview`, `render_video`) |
| `tools/generate.py` | Client autonome texte → vidéo (DeepSeek) |
| `ldraw/` | Bibliothèque LDraw officielle (~25 000 pièces) |
| `models/`, `renders/` | Modèles générés et rendus |

## Usage A : client autonome (DeepSeek)

```bash
export DEEPSEEK_API_KEY=sk-...
python3 tools/generate.py "une petite maison rouge avec un toit vert et une cheminée"
# → models/<nom>.ldr, renders/<nom>.png, renders/<nom>.mp4
```

## Usage A'' : mode script (le modèle code, le harness exécute)

Approche Blender MCP / OpenSCAD : DeepSeek écrit un **script Python** contre
l'API `LDrawModel` (boucles, fonctions, symétries), le sandbox l'exécute
(timeout 120 s, imports système/réseau refusés), les erreurs sont renvoyées
au modèle pour correction (2-3 tours en pratique), puis rendu.

```bash
export DEEPSEEK_API_KEY=sk-...
python3 tools/generate_script.py "un château avec deux tours crénelées"
python3 tools/generate_script.py "..." --visual-rounds 2   # + critique visuelle
```

**Boucle visuelle** : après un build réussi, un modèle vision (`deepseek-flash`,
qui accepte les images) examine 3 rendus et liste les écarts avec la demande ;
le codeur corrige et le harness ne garde la correction que si elle ne dégrade
pas le score géométrique (briques flottantes/rejetées) ni ne supprime plus de
25 % du modèle. Modèles configurables :

```bash
export DEEPSEEK_MODEL=deepseek-chat          # codeur
export DEEPSEEK_VISION_MODEL=deepseek-flash  # critique visuelle
```

Outils MCP correspondants : `build_from_script(name, code)` + `build_screenshot`.
C'est le mode recommandé pour les formes libres ; `sandbox_runner.py` isole
l'exécution (sous-processus borné, imports dangereux interdits) et sauvegarde
le dernier script dans `out/last_build_script.py`.

**Note** : en mode sandbox les collisions sont **fatales** (le modèle doit
corriger sa géométrie) ; les doublons exacts sont ignorés silencieusement pour
éviter les boucles stériles. L'auto-décalage (`model.autofit`) n'est utilisé
que par le mode one-shot, où le LLM ne boucle pas — l'activer dans le sandbox
produit des modèles incohérents. Les erreurs renvoyées au modèle incluent la
**ligne fautive** du script (traceback) : c'est ce qui lui permet de corriger
du premier coup.

### Convention des pièces (piège n°1)

Dans le nom LDraw « Brick A x B », **A est la profondeur (z) et B la largeur
(x)** : une « Brick 2 x 4 » (3001) occupe 4 studs en x et 2 en z. Un LLM qui
suppose l'inverse produit des chevauchements systématiques. `find_parts()`
renvoie donc `footprint_x` / `footprint_z` pour lever l'ambiguïté.

### Primitives de haut niveau

Exposées au script (et donc au LLM) pour éviter les collisions par construction :

| Méthode | Rôle |
|---|---|
| `model.slab(x, z, w, d, y, color, layers, openings)` | pave un rectangle (mur = d=1, sol/toit = layers=1, `openings` pour portes/fenêtres) |
| `model.column(x, z, layers, color, part)` | empile une tour/pilier |
| `model.clearance(x, z, w, d, layers, y)` | teste si un volume est libre |
| `model.connectivity()` | nombre d'amas détachés (`islands` : 1 = modèle d'un seul bloc) |
| `model.stability()` | rapport de stabilité physique (voir ci-dessous) |

`tools/arch.py` — formes composées que les LLM ratent systématiquement :

| Primitive | Rôle |
|---|---|
| `arch.pitched_roof(x, z, w, d, y, color, ridge)` | toit à deux pans, rives en pente, faîtière |
| `arch.pyramid_roof(x, z, size, y, color)` | toit pyramidal / conique de tour (pièce d'angle 3045 + cône 98100) |
| `arch.crenellate(x, z, w, d, y, color)` | créneaux sur un chemin de ronde |
| `arch.stairs(x, z, height, color, direction)` | escalier |
| `arch.hull/wing/cockpit/engine` | éléments de vaisseau : fuselage effilé, aile, verrière, propulseur |

| `arch.hull(x, z, w, d, layers, color, y)` | fuselage plein avec nez effilé vers -z |
| `arch.wing(x, z, w, d, y, color)` | aile plate à bord d'attente en pente |
| `arch.cockpit(x, z, w, d, y, color)` | verrière vitrée |
| `arch.engine(x, z, w, d, y, color)` | propulseur avec tuyère lumineuse |

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

## Usage A' : mode templates (recommandé)

Le LLM ne choisit que des **paramètres** (dimensions, couleurs, style) ; la
géométrie est générée par du code déterministe — résultat toujours propre.

```bash
export DEEPSEEK_API_KEY=sk-...
python3 tools/generate_template.py "une grande maison beige, toit rouge, porte bleue"
python3 tools/generate_template.py "maison" --params '{"type": "house", "width": 18}'  # sans LLM
```

Archétypes disponibles dans `tools/templates.py` : `house` (murs, toit à
gradins deux pans, porte, fenêtres vitrées), `tower` (créneaux + toit
pyramidal), `spaceship` (fuselage effilé, ailes, cockpit, propulseurs). Le LLM
voit uniquement un schéma de paramètres (~100 tokens) au lieu de générer des
centaines de briques : coût dérisoire et zéro erreur géométrique.

## Usage C : mode solver (LLM architecte + CP-SAT constructeur)

Le LLM ne place **jamais** de briques : il produit un **blueprint LEGO IR**
(composants `wall` / `tower` / `slab` / `box` en studs, objectifs globaux —
`tools/lego_ir.py`), le **solver OR-Tools CP-SAT** (`tools/solver.py`) choisit
les briques concrètes : couverture exacte de chaque cellule (zéro collision
par construction), support vertical ou accolade latérale (linteaux de portes),
objectif `min λ1·N_pièces + λ2·N_types`. Les patterns (`tools/patterns.py` :
`cheap` = moins de pièces, `strong` = joints décalés, `decorative` = bandes
bicolores) sont choisis par le LLM, la variante concrète par le solver.
Chaque erreur (blueprint invalide, région insatisfiable, brique sans appui)
est un **feedback déterministe** renvoyé au LLM (2-3 tours).

```bash
pip install ortools
export DEEPSEEK_API_KEY=sk-...
python3 tools/generate_solver.py "un château médiéval avec deux tours et un donjon"
python3 tools/generate_solver.py "..." --blueprint bp.json --no-llm   # sans clé API
python3 tools/generate_solver.py "..." --max-pieces 150 --no-video
```

Outils MCP correspondants : `solve_blueprint(blueprint)` (blueprint JSON →
rapport + .ldr) et `generate_solved(prompt)` (pipeline complet).

- **Solver design** : les composants peuvent être placés par **attachement
  relatif** (`"attach": {"to": "tower_1", "side": "+x", "offset": 2}`) — le
  LLM décrit les relations, les coordonnées sont calculées (ancre inconnue,
  cycle et hors-terrain rejetés) ; des composants attachés se touchent, donc
  le modèle est connexe.
- **Cache de modules** (passage à l'échelle) : les régions de même forme
  (empreinte relative, hauteur, creux, pièces, couleurs) ne sont résolues
  qu'**une seule fois** — les tours jumelles, murailles répétées etc.
  sont translatées depuis la solution en cache.

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
les exports (BOM, XML), la notice (SVG sans LeoCAD) et les formes de démo.
Le test du solver CP-SAT est ignoré si `ortools` n'est pas installé.

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
