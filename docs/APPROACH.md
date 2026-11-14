# legoCAD v2 — de « joli rendu » à « set réellement constructible »

Ce document explique le diagnostic, la nouvelle architecture et la feuille de
route. Il complète le README (mode d'emploi) : ici, on parle **approche**.

---

## 1. Ce qui bloquait dans la v1

| Symptôme | Cause | Conséquence |
|---|---|---|
| Modèles méconnaissables (pavés, tours) | le LLM produisait un *blueprint* de composants (`wall`, `box`, `tower`) | l'espace des formes exprimables est celui des boîtes |
| « Le plancher tient par les studs latéraux » | `stability.py` considérait l'accolement latéral comme un appui | des modèles qui s'effondrent dès qu'on les soulève |
| Aucune nomenclature exploitable | pas de BOM, pas de contrôle de disponibilité | impossible de commander les pièces |
| Pas de notice | les steps existaient, pas les images/pièces par étape | le `.ldr` n'est pas un set |
| Aspect « voxel » grossier | uniquement briques/plates 1×N et 2×N, objectif = moins de pièces | pas de pentes, de tiles, de détails |
| Pas d'évaluation | aucune métrique commune | impossible de comparer deux approches |

Le point le plus grave est le **modèle physique** : en LEGO, deux briques
côte à côte ne sont pas attachées. Seuls les tenons (studs) d'une pièce
s'insèrent dans le dessous de la pièce au-dessus. Toute la validation doit
partir de là.

---

## 2. La nouvelle chaîne

```
forme / texte / image / .ldr
        │
        ▼
   VOLUME (voxels)          tools/voxel.py      1 voxel = 1 stud × 1 plaque
        │
        ▼
   COMPILATEUR              tools/brickify.py   cours de briques, appareillage,
        │                                       support réel, tiles, réparation
        ▼
   VALIDATION               tools/studs.py      graphe étud → tube, amas,
        │                   tools/stability.py  basculement, pièces faibles
        ▼
   LIVRABLES                tools/bom.py        nomenclature, BrickLink XML
        │                   tools/instructions.py notice A4 imprimable
        │                   tools/preview_svg.py aperçu/étapes sans LeoCAD
        ▼
   WEB                      web/server.py       génération + téléchargements
```

### Pourquoi un volume intermédiaire ?

Un modèle LEGO est d'abord **une forme**, puis un pavage. En séparant les
deux, on peut :

- brancher n'importe quelle source de forme (texte, image, `.ldr` existant,
  primitive procédurale) sans toucher au compilateur ;
- garantir que le pavage est constructible (c'est le compilateur qui place
  les pièces, pas le LLM) ;
- changer de stratégie de pavage (pentes, SNOT, modules) sans casser les
  sources.

C'est l'architecture utilisée par BrickGPT (voxel 20³ → briques) et par
BrickWright (l'agent écrit un programme, le validateur vérifie).

### Le voxel est en **plaques**, pas en briques

Les sets réels sont majoritairement composés de plaques (dans notre
échantillon OMR : `3023` Plate 1×2 = 5,3 % des pièces, `6141` Plate 1×1 ronde
= 3,3 %, `3024` = 2,7 %…). Un voxel = 1 stud × **1 plaque** permet :

- les détails d'un demi-niveau (pare-chocs, bordures, visages) ;
- les formes qui s'affinent sans escalier de 3 plaques ;
- un mélange brique/plaque réaliste (une colonne pleine de 3 plaques devient
  une brique, le reste des plaques).

### Règles de compilation (les trois qui changent tout)

1. **Un cours de briques n'est posé que si l'empreinte ne s'élargit pas.**
   Une brique occupe 3 plaques ; si la forme s'élargit au niveau suivant,
   la brique bloque le débord et la couche au-dessus ne peut plus être
   posée. Les zones qui s'élargissent sont donc pavées en plaques. C'est ce
   qui fait passer la fusée de 0 % à 100 % de couverture.
2. **Appareillage** : les joints sont décalés d'un cours à l'autre ; une
   pièce qui **enjambe** deux pièces du dessous est récompensée. C'est ce
   qui relie les rangées et évite les modèles en colonnes indépendantes.
3. **Support réel** : une pièce n'est acceptée que si au moins un de ses
   studs repose sur une pièce déjà posée (ou le sol) ; une pièce non
   attachée est retirée, jamais laissée « flottante ».

### Validation physique

`tools/studs.py` construit le graphe **étud → tube** :

- `islands` : nombre d'amas réellement attachés (1 = modèle soulevable) ;
- `unsupported` : pièces sans chemin de charge vers le sol ;
- `single_stud` : pièces tenues par un seul tenon (légales, mais fragiles) ;
- `resting` : pièces posées sur une surface lisse (tile) — non attachées.

`tools/stability.py` ajoute le **basculement** : pour chaque joint, on prend
uniquement la charge qui passe par ce joint (les pièces posées à ce niveau,
puis tout ce qui est empilé dessus), et on vérifie que son centre de gravité
tombe au-dessus de la zone de contact. C'est la version discrète du critère
d'équilibre des moments (Legolization / StableLego).

### Disponibilité et réalisme

Sans API en ligne, on ne peut pas prouver qu'une combinaison pièce/couleur
existe. On apprend une **distribution empirique** sur 493 sets officiels
(OMR, 15 671 pièces, 1 297 pièces distinctes) :

- `data/part_colors.json` : couples pièce/couleur observés + fréquences ;
- un couple jamais vu est signalé (« à vérifier sur BrickLink »), pas rejeté ;
- `mix_similarity` compare la répartition des pièces du modèle à celle des
  sets réels (cosinus). Ce n'est pas un objectif esthétique, mais un signal :
  un modèle composé uniquement de 2×8 a une allure de « mur », pas de set.

Les exports sont : `.ldr` (Studio/LeoCAD), `bom.csv`, `bom.json`,
`wanted_list.xml` (BrickLink), `notice.html` imprimable.

---

## 3. État de l'art et ce qu'on emprunte

| Travail | Idée clé | Ce qu'on en fait |
|---|---|---|
| **BrickGPT** (ICCV 2025, CMU) | voxel 20³, dataset StableText2Brick (47 k structures), génération autorégressive + **rollback physique** | le volume intermédiaire, la métrique `min_stability`, la réparation par retrait des pièces instables |
| **BrickWright** (2026, CMU/Stanford) | *structure-as-code* : l'agent écrit du Python avec `BrickLayer`, un validateur vérifie collisions/flottants/amas ; 100 % de builds valides même avec de petits modèles | le mode texte → programme → volume, et la séparation création/validation |
| **BrickNet / Image2Lego** | image → voxels → briques ; les briques réelles guident la forme | la route image → mosaïque (déjà) et, ensuite, silhouette/depth → volume |
| **StableLego / Legolization** | stabilité par programmation linéaire, basculement | le critère de basculement par joint, en version discrète |
| **BrickNet** (CVPR 2026, Kulits & Schmid) | 100 k objets LDraw, 9 743 pièces, représentation **graphe de connecteurs** (stud / hinge / axle / ball / fixed), séquences de construction par arbre couvrant | le contrat de validité, la roadmap connecteurs (charnières/axes), l'idée de séquence = graphe |
| **BrickBench / BrickAgent** (2026, Kulits et al.) | 300 prompts, 3 réglages (Model ≤400, Set 400-4000, Alt-Build 10698), métriques Valid / VQA / ELO / coût ; la validité physique est résolue par l'environnement, le **design** reste le plafond | la définition `valid`, le benchmark local, la priorité aux détails de surface |
| **OMR** (Official Model Repository) | ~1 800 sets officiels en LDraw | calibration de la disponibilité, tests de non-régression, few-shot |
| **Studio / Rebrickable / BrickLink** | écosystème de pièces et d'instructions | exports `.ldr`, CSV, wanted list XML |

---

## 4. Feuille de route priorisée

### P0 — la qualité de surface (fait en v2.1)

- **Pentes** : `3040b`, `3039`, `3037`, `4286`, `3298` posées sur les marches
  de 3 plaques (`tools/slopes.py`). Les tuiles sous la pente sont remplacées
  par des plaques pour que la pente soit réellement attachée. Les cheese
  slopes 2 plaques (54200/85984/15068) sont identifiés et leur hauteur est
  supportée, mais leur pose n'est pas encore validée au rendu : désactivées.
- **Tiles** : une plaque de finition (`tile_cap`) couvre chaque sommet ;
  la surface est lisse, comme sur un set réel.
- **Pièces 2D** : fondation 4×4/4×8 (`3031`/`3035`) et **plaque de base
  32×32** (`3811`) quand l'empreinte est exactement un format standard : le
  socle est une pièce, ce qui relie les rangées du soubassement.
- **Débords / corbeaux** : une cellule sans appui vertical est couverte
  **avant** le pavage par une pièce posée en travers de l'appui
  (`_cover_overhangs`), puis un re-pavage local (`_repair_gaps`) retire et
  repose les pièces du niveau autour des trous restants. C'est ce qui rend
  constructibles les mâchicoulis, parapets de tours rondes, toits coniques
  et ailes en porte-à-faux.
- **Sous-assemblages** : les liaisons à 1 seul stud sont coupées du graphe ;
  les modules restants ont une page dédiée dans la notice
  (`tools/instructions.py`).
- **SNOT / charnières** : les familles sont identifiées (`stud`, `snot`,
  `axle`, `hinge`, `ball`) et signalées ; `tools/snot.py` est un **prototype
  3D** (frames de connecteurs, headlight brick, export LDraw) qui valide la
  connexion latérale. L'intégration au compilateur volumique reste à faire.
- **Vision** : `tools/depth_onnx.py` (Depth Anything V2 small, ONNX) produit
  une depth map réelle sans PyTorch ; `tools/depth_to_voxel.py` la transforme
  en relief 2.5D constructible. Un autre modèle se branche via `--depth-cmd`.
- **Approvisionnement / PDF** : `tools/rebrickable.py` et
  `tools/pdf_notice.py` (LPub3D si installé, sinon notice HTML).

### P1 — les sources de forme

- **Image → volume** : vue de face/dessus/côté (visual hull, déjà dans
  `voxel.from_silhouettes`), puis depth map (DepthAnything/MiDaS) et SAM
  pour détourer. Un modèle de vision ne produit jamais de briques : il
  produit un volume.
- **Boucle visuelle** : rendre 2-3 vues SVG/LeoCAD, demander à un VLM
  (« est-ce une fusée ? qu'est-ce qui manque ? »), corriger le volume.
  C'est la boucle déjà présente dans `generate_script.py`, déplacée au
  niveau du volume.
- **Few-shot OMR** : injecter 2-3 extraits de sets réels dans le prompt
  (idiomes de pièces, proportions).

### P2 — l'approvisionnement

- L'**API Rebrickable** est branchée (`tools/rebrickable.py`) : il ne manque
  que la clé `REBRICKABLE_API_KEY` pour vérifier les couples pièce/couleur
  et récupérer des prix.
- Export **BrickLink XML** validé (mapping LDraw → BrickLink), alternative
  CSV Rebrickable.
- Filtre « budget » / « pièces déjà possédées » (inventaire utilisateur).

### P3 — la notice et la diffusion

- **PDF** : LPub3D headless installé et testé ; `make_model --pdf` produit
  le document (24 pages pour la maison).
- **Web** : `web/server.py` (fait) + Docker ; déploiement VPS derrière
  Cloudflare Tunnel, ou Fly.io/Render. Mettre en cache les aperçus et
  limiter la taille des imports.
- **Galerie** : les modèles générés sont déjà dans `out/web/<nom>/` ;
  ajouter une page publique et des permaliens.

### P4 — l'apprentissage

- Le dataset **StableText2Brick** (BrickGPT, MIT) et l'OMR permettent
  d'entraîner un petit modèle « texte → volume » ou « image → volume ».
- Alternative moins coûteuse : un LLM généraliste + le DSL de volume +
  le validateur (déjà en place). C'est l'approche qui donne le meilleur
  rapport qualité/prix en 2026.

---

### BrickNet / BrickBench : ce qu'on adopte

- **Contrat de validité** identique : pièces réelles, zéro collision, zéro
  pièce flottante, **un seul composant**, stable sous gravité. C'est
  `quality.validity()` et le premier contrôle du score.
- **Structure-as-code** : BrickAgent fait écrire du Python à un agent, avec
  une API de connexion (`attach(stem, to=..., by=('stud', i), ...)`) et un
  validateur. Notre `tools/voxel.py` + `brickify.py` + `studs.py` est la
  version « volume » de la même idée ; `tools/text_to_voxel.py` est le mode
  agent.
- **Connecteurs** : BrickNet modélise cinq familles (stud, hinge, axle,
  ball, fixed). Notre validateur ne connaît que les studs, ce qui suffit
  aux briques/plaques ; les charnières, essieux et rotules sont la prochaine
  extension (et une limite assumée de `ldr_io.load()`).
- **Design** : BrickBench montre que les agents savent déjà produire du
  valide ; ce qui manque, ce sont les pentes, les tiles, les greebles et les
  proportions. C'est exactement la priorité P0 ci-dessus.

### Benchmark local

```bash
python3 tools/bench.py --shapes
# modèle                        pièces  couv.  amas stab.  valid
# brick                              1 100.0%     1  1.00    oui
# car                              124 100.0%     1  1.00    oui
# duck                              30 100.0%     1  1.00    oui
# house                            165 100.0%     1  0.90    oui
# rocket                           179 100.0%     1  0.90    oui
# spaceship                        190 100.0%     1  0.90    oui
# tree                             221 100.0%     1  0.90    oui
# 7/7 valides · temps médian 0.09 s
```

Les modèles de la v1 (blueprint/solver) et les sets OMR recompilés depuis
des voxels ne passent pas ce contrat (amas multiples, pièces non attachées) :
c'est précisément le problème que la v2 corrige. Pour étudier un modèle
existant, utiliser l'import **natif** (`--ldr-native`) qui conserve les
pièces, plutôt que de le voxeliser.

## 5. Comment évaluer (et ne pas se mentir)

Un modèle doit être jugé sur des critères reproductibles :

| Métrique | Définition | Cible |
|---|---|---|
| `coverage` | voxels du volume couverts par une pièce | ≥ 0,99 |
| `islands` | amas de pièces attachées | 1 |
| `unsupported` | pièces sans chemin de charge | 0 |
| `min_stability` | maillon faible (0-1) | ≥ 0,9 |
| `build_errors` | ordre de montage impossible | 0 |
| `availability` | couples pièce/couleur observés ou plausibles | ≥ 0,9 |
| `mix_similarity` | proximité de la distribution de pièces aux sets réels | ≥ 0,5 |
| `score` | moyenne pondérée (voir `tools/quality.py`) | ≥ 0,85 |

Le score n'est pas une décoration : il est affiché dans l'interface et
enregistré dans `report.json`. Un modèle qui a l'air beau mais qui a
`islands > 1` ou `unsupported > 0` n'est pas publiable.

---

## 6. Déploiement

```bash
# local
python3 web/server.py --port 8000

# docker (sans LeoCAD, rendu SVG)
docker compose up --build

# VPS derrière Cloudflare Tunnel
cloudflared tunnel --url http://127.0.0.1:8000
```

En ligne, `LEGOCAD_NO_RENDER=1` désactive LeoCAD : le serveur utilise le
rendu SVG isométrique (`tools/preview_svg.py`), qui ne demande ni Flatpak ni
bibliothèque LDraw et reste lisible dans la notice. Pour des rendus
photoréalistes, installer LeoCAD dans l'image (ou garder le rendu côté
machine locale) et monter `ldraw/`.

---

## 7. Ce qu'il ne faut pas faire

- Demander au LLM de placer des briques une par une : il produit des
  collisions, des flottants et des modèles non connexes (BrickWright le
  mesure : 9 % de builds valides avec un petit modèle, 100 % avec un
  validateur).
- Considérer l'accolement latéral comme un support : c'est faux
  physiquement et ça valide des planchers qui tombent.
- Utiliser une seule plaque comme plafond d'une pièce large : elle n'est
  attachée qu'au périmètre. Il faut des poutres en appareillage ou des
  appuis intermédiaires.
- Optimiser uniquement le nombre de pièces : on obtient des murs de 2×8,
  pas un set. La variété et la lisibilité comptent autant.
- Publier un modèle sans nomenclature : il n'est pas commandable, donc pas
  constructible.
