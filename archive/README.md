# Archive du projet legoCAD

Ce dossier conserve le **pipeline v1** et les **anciennes productions**,
sortis du chemin principal lors du remaniement. Rien ici n'est maintenu :
la référence est le pipeline v2 (`tools/brickify.py` + `tools/shapes.py`).

```
archive/
├── v1/tools/     solver CP-SAT, blueprint IR, templates, clients LLM
├── v1/tests/     tests de ce pipeline
├── models/       anciens .ldr (solver, LLM, prototypes)
└── renders/      captures de ces anciens modèles
```

## Pipeline v1 (archivé)

Le v1 partait d'un **blueprint sémantique** (murs, tours, dalles) : un LLM
écrivait le blueprint, un solver OR-Tools CP-SAT choisissait les briques.
Trois autres entrées existaient : templates paramétriques, génération de
script Python exécuté en sandbox, et spec JSON one-shot.

### Relancer le code v1

Les imports croisés (`solver`, `lego_ir`, `templates`, `arch`, `render`) sont
résolus en ajoutant les deux dossiers au `PYTHONPATH` :

```bash
PYTHONPATH=tools:archive/v1/tools python3 archive/v1/tools/generate_solver.py \
  "un château médiéval avec deux tours" --no-llm --blueprint bp.json
PYTHONPATH=tools:archive/v1/tools python3 -m pytest archive/v1/tests -q
```

`generate_template.py`, `generate_script.py` et `generate.py` nécessitent
une clé `DEEPSEEK_API_KEY`.

### Documentation d'origine (extraite du README)

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



## Anciens modèles

| Fichier | Origine |
|---|---|
| `models/cabane_solver.ldr` | solver CP-SAT, cabane |
| `models/petit_chateau_solver.ldr` | solver CP-SAT, château |
| `models/chateau_attache.ldr` | prototype « château attaché » |
| `models/chateau_llm.ldr` | génération LLM (mode script) |
| `models/voiture_llm.ldr` | génération LLM (mode script) |
| `models/house.ldr` | première maison procédurale |
| `models/maison_beige_toit_rouge.ldr` | maison beige, toit rouge |
| `models/tower.ldr`, `models/spaceship.ldr` | prototypes de formes |
| `models/Voilier.ldr`, `models/Voilier LEGO.ldr` | import LDraw / voilier |

## Anciens rendus

`renders/chateau_llm.png`, `renders/voiture_llm.png`,
`renders/cabane_solver.png` : captures des productions ci-dessus.

## Pourquoi ce classement

- Le v1 reste utile comme **référence de recherche** (solver, IR, templates)
  et pour comparer les approches dans `docs/APPROACH.md`.
- Les sorties v1 ne sont plus régénérées par `tools/make_model.py` ; les
  garder à la racine brouillait la lecture du projet.
- Les modèles v2 de référence sont `models/chateau.ldr` et
  `models/maison.ldr`.
