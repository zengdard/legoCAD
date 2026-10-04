# text2legoCAD

Génère des sets LEGO à partir de texte et en produit des vidéos
(timelapse de construction + rotation 360°), via LeoCAD en headless.

```
prompt ──► DeepSeek ──► spec JSON (briques sur grille) ──► générateur .ldr
        ──► LeoCAD headless (rendu par step) ──► FFmpeg ──► vidéo mp4
```

## Installation

```bash
pip install ortools openai fastmcp
# bibliothèque LDraw (CC BY 4.0, ~615 Mo, non incluse) :
mkdir ldraw && cd ldraw
curl -LO https://library.ldraw.org/library/updates/complete.zip && unzip complete.zip
# rendu : LeoCAD via Flatpak + ffmpeg
flatpak install org.leocad.LeoCAD   # + ffmpeg dans le PATH
```

## Structure

| Fichier | Rôle |
|---|---|
| `tools/build_catalog.py` | Extrait les dimensions réelles des pièces curées depuis la bibliothèque LDraw officielle → `pieces_catalog.json` |
| `tools/parts_index.py` | Index des ~23 000 pièces de la bibliothèque complète (descriptions, familles, hauteurs) + cache `parts_index_cache.json` |
| `tools/stability.py` | Analyse de stabilité physique (appui, basculement, `min_stability`) |
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
