# BrickBench « Set » — étude de la galerie et recommandations pour legoCAD

> Étude documentaire réalisée le **14 novembre 2026**. Aucun fichier de code n'a
> été modifié : ce document est le seul livrable.
>
> Pages principales consultées : <https://gallery.brickben.ch/?s=set>,
> <https://brickben.ch/>, <https://arxiv.org/abs/2610.12452> (v1, 8 octobre
> 2026), <https://arxiv.org/html/2610.12452v1>, <https://kulits.github.io/BrickNet/>,
> <https://github.com/kulits/BrickAgent>. La galerie est publique, sans login
> ni captcha ; seules les balises Cloudflare Analytics échouent en CORS, sans
> incidence sur le contenu.
>
> Méthode : parcours de la galerie (100 prompts « Set », 12 systèmes, 1 176
> rendus), téléchargement de **17 fichiers `.mpd`** et de **7 scripts `.py`**
> représentatifs, analyse locale des pièces/couleurs avec
> `parts_index_cache.json`, lecture du papier et du README de BrickAgent.
> Les comptages de types/couleurs ci-dessous viennent de ces `.mpd` ; les
> nombres de pièces affichés sont ceux de la galerie (ils diffèrent de quelques
> unités des fichiers, qui contiennent aussi les sous-modèles).

## En bref

1. BrickBench « Set » est un **corpus public de scènes de 400–4 000 pièces**,
   avec 8 vues, le `.mpd` et le `.py` de chaque build ; c'est un excellent
   étalon de **design**, pas un modèle de livrable (ni notice, ni BOM, ni steps).
2. La validité BrickBench est **plus permissive** que legoCAD sur la connexité
   (plusieurs composants stables admis) et **plus riche** sur les attaches
   (5 familles de connecteurs) ; elle reste un **proxy rigid-body**.
3. Les agents saturent la validité et le VQA ; le **design** est le plafond :
   323/360 comparaisons humaines choisissent le modèle humain, et l'écart de
   Design ELO entre le meilleur et le moins bon agent vaut ~545 points.
4. Le déficit de legoCAD n'est pas la géométrie mais le **vocabulaire** (51
   pièces, 3–41 types par forme) et la **composition de scène** (diorama,
   personnages, props, matières).
5. Les trois chantiers à plus fort effet de levier sont **A1 mode scène**,
   **A3 palette de détail** et **A2 composeur de diorama** ; la notice et le
   BOM restent l'avantage différenciant à préserver.

---

## 1. Ce qu'est la galerie « Set »

### 1.1 Trois réglages, une même galerie

La galerie expose trois réglages définis par le papier :

| Réglage | Contrainte | Ce que ça teste |
|---|---|---|
| **Model** | ≤ 400 pièces | un objet, généralement un seul composant |
| **Set** | **400 à 4 000 pièces** | une scène à l'échelle d'un set retail (BrickLink Designer Program) |
| **Alt-Build** | uniquement les 783 pièces / 104 types du set 10698 | la conception sous inventaire rare et fixe |

L'onglet `Set` de <https://gallery.brickben.ch/?s=set> affiche **100 prompts**
(10 catégories × 10 prompts) et, par défaut, 5 systèmes par ligne. Le bouton
`Agents` permet d'en afficher jusqu'à 12 (les deux baselines BrickNet/BrickGPT
ne s'appliquent qu'à `Model`). Catégories : Medieval/Castle,
Vehicle/Boat/Airplane, Train, Space/Sci-Fi/Fantasy, Art/Object, Building,
Floral/Nature, Animal, Pirate, History/Period — les catégories du BrickLink
Designer Program, avec `Floral/Nature` et `Animal` séparés.

Chaque vignette est une **paire (prompt, système)** : nom du système, nombre
de pièces, vignette. Cliquer ouvre une lightbox avec :

- **8 vues** rendues du même modèle (rotation, vue « front ») ;
- le **prompt complet** (souvent 45 à 70 mots pour les Sets) ;
- les boutons **`.mpd`** et **`.py`** (téléchargement du modèle LDraw et du
  script BrickAgent qui l'a produit) ;
- les flèches précédent/suivant **agent** et **prompt** ;
- un statut de validité : `N parts` en vert, ou un badge ✕ avec la raison
  (`Collision`, `Unstable`, …), ou `no build` quand aucun assembly n'a été
  rendu.

Exemples directs :

- <https://gallery.brickben.ch/?s=set&b=set-077-astra> — « Pointing woman and
  a white cat at dinner », 1 809 pièces, valide.
- <https://gallery.brickben.ch/?s=set&b=set-077-opus55> — même prompt,
  417 pièces, valide, approche minifig très différente.
- <https://gallery.brickben.ch/?s=set&b=set-077-glm> — même prompt,
  463 pièces, **invalide (Collision)**.
- <https://gallery.brickben.ch/?s=set&b=set-060-muse> — 1 pièce, invalide.
- <https://gallery.brickben.ch/?s=set&b=set-010-muse> — `no build`.

### 1.2 Ce que montre une « fiche Set »

La galerie est pauvre en livrables mais riche en **vues**. Elle ne fournit
ni notice, ni nomenclature, ni ordre de montage : les `.mpd` analysés
ne contiennent **aucune ligne `0 STEP`**. C'est un point important pour legoCAD, qui est
justement fort sur ce terrain (voir § 3).

Les rendus sont normalisés : fond neutre, cadrage automatique, 1024×1024,
8 vues par modèle, une vue frontale marquée. C'est ce protocole qui rend les
comparaisons visuelles possibles, pas seulement le nombre de pièces.

### 1.3 Échantillon analysé

17 constructions téléchargées et mesurées (pièces = galerie ; types/couleurs =
analyse du `.mpd`). Les liens sont de la forme
`https://gallery.brickben.ch/?s=set&b=<id>`.

| id | Catégorie | Sujet | Système | Pièces | Types | Couleurs | Valide |
|---|---|---|---:|---:|---:|---:|---|
| set-003 | Medieval | Floating turtle-head fortress | BrickWright | 2 313 | 26 | 18 | oui |
| set-010 | Medieval | Two goblets on a hillside table | Opus 5.5 | 709 | 70 | 13 | oui |
| set-021 | Train | Giant toy engine through a house | Astra | 3 290 | 68 | 22 | oui |
| set-041 | Art/Object | Household-object ball | Astra | 1 105 | 55 | 18 | oui |
| set-045 | Art/Object | Staircase sculpture… | Astra | 1 121 | 40 | 9 | oui |
| set-051 | Building | Pink dream house with two slides | Astra | 1 093 | 46 | 18 | oui |
| set-052 | Building | Striped convenience store | BrickWright | 597 | 24 | 12 | oui |
| set-064 | Floral/Nature | Explorer in a giant fungus forest | Astra | 1 192 | 38 | 16 | oui |
| set-077 | Animal | Pointing woman and a white cat… | Astra | 1 809 | 59 | 20 | oui |
| set-077 | Animal | idem | Opus 5.5 | 417 | 61 | 18 | oui |
| set-077 | Animal | idem | Qwen 3.8 | 537 | 88 | 19 | oui |
| set-077 | Animal | idem | DeepSeek V4.1 | 420 | 30 | 15 | oui |
| set-077 | Animal | idem | GLM 5.3 | 463 | 28 | 11 | **non (collision)** |
| set-077 | Animal | idem | BrickWright | 914 | 88 | 20 | oui |
| set-083 | Pirate | Green ghost ship on the seabed | Astra | 1 818 | 56 | 22 | oui |
| set-096 | History | Two chariots at an arena bend | Astra | 1 144 | 84 | 17 | oui |
| set-097 | History | Travelers in a parted sea | BrickWright | 1 097 | 22 | 21 | oui |

Premiers constats quantitatifs :

- les Sets valides de la galerie font **417 à 3 290 pièces**, avec **22 à 88
  types** et **9 à 22 couleurs** — très loin des 2 à 8 types de beaucoup de
  générateurs voxel ;
- les formes du banc legoCAD (`tools/bench.py --shapes`, 14/11/2026) font
  **5 à 3 664 pièces** mais seulement **3 à 41 types** : le déficit est
  d'abord un déficit de **vocabulaire de pièces** ;
- sur 1 200 rendus possibles (100 prompts × 12 systèmes), la galerie en
  compte **1 176** : 24 `no build` ; 1 121 sont valides et 55 invalides
  (95,3 % de valides), les échecs affichés étant surtout collisions et
  instabilité.

---

## 2. Critères de validité et métriques du papier

### 2.1 Le contrat « Valid »

Une assembly est **valide** si elle satisfait **les trois** conditions :

1. **contrainte de pièces** du réglage (≤ 400 pour Model, **400–4 000** pour
   Set, inventaire exact de 10698 pour Alt-Build) ;
2. **sans collision** : deux pièces ne se chevauchent pas au-delà d'une
   tolérance (test géométrique préalable) ;
3. **stable sous gravité** : chaque composant connexe est simulé comme un
   corps rigide dans **PyBullet** (frottement élevé, restitution nulle) ;
   aucun point ne doit bouger de plus de **3 LDU** (¾ de hauteur de tenon).

Deux nuances capitales, souvent mal reprises :

- **plusieurs composants sont autorisés** : une scène peut contenir des objets
  séparés (personnage, table, animal). Le papier les compte et les simule
  séparément ; il ne demande pas un seul amas.
- la stabilité est un **proxy rigid-body** : la force des tenons, le jeu des
  axes et la flexion ne sont pas modélisés. Un assemblage qui tient en
  équilibre passe même s'il serait mou en vrai. Le papier l'assume
  explicitement (§ 3.2 et § 6).

### 2.2 Les quatre métriques

| Métrique | Définition | Limite |
|---|---|---|
| **Valid** | proportion d'assemblies valides (pièces + collisions + stabilité) | binaire, ne dit rien du design |
| **VQA** | fraction des questions oui/non d'un **graphe de questions** (style DSG) répondue oui par un VLM (Gemma 4 31B) sur 8 vues | dépend du judge et du rendu ; sature chez les bons agents |
| **ELO** | tournoi par paires (Bradley–Terry), deux questions : **Align** (avec le prompt) et **Design** (sans le prompt, « standard d'un set officiel ») ; paires dans les deux ordres, 4 vues par modèle | coûteux ; biais de judge ; validation humaine nécessaire |
| **Cost** | prix API des tokens par assembly (ou coût GPU équivalent pour BrickGPT) | ne mesure pas le temps humain |

Le graphe de questions Set contient **2 369 questions** pour 100 prompts, soit
**~24 questions par prompt** (entités, attributs, relations, états). Les
questions dépendent les unes des autres : si le chevalier n'existe pas, on ne
teste pas la couleur de son armure. C'est une bonne idée à reprendre pour la
QC de legoCAD, indépendamment du VLM.

### 2.3 Résultats « Set » et enseignements du papier

Extraits de la Table 1 (réglage Set) et de la Table A1 :

| Système | Valid | VQA | ELO | Design ELO | Coût $ | Pièces | Types | Couleurs | Composants |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra | 1,00 | 0,933 | 1305 | **1316** | 5,15 | 1 511 | 46,8 | 17,0 | 2,2 |
| GPT-6.1 Sol | 1,00 | 0,920 | 1295 | 1292 | 1,05 | 1 625 | 49,1 | 16,7 | 3,5 |
| Claude Opus 5.5 | 0,99 | 0,892 | 1240 | 1315 | 8,08 | 1 112 | 68,5 | 17,5 | 3,8 |
| Claude Opus 5 | 1,00 | 0,890 | 1100 | 1109 | 18,80 | 865 | 48,6 | 14,6 | 4,2 |
| Qwen 3.8 Flash | 0,79 | 0,801 | 1090 | 1131 | 2,26 | 1 118 | 38,8 | 17,4 | 32,8 |
| GPT-5.6 Sol | 1,00 | 0,832 | 993 | 963 | 1,16 | 698 | 29,9 | 14,8 | 3,3 |
| Gemini 3.8 Flash | 0,97 | 0,806 | 1012 | 1013 | 4,26 | 581 | 36,5 | 17,3 | 1,7 |
| DeepSeek V4.1 | 0,87 | 0,786 | 1005 | 1036 | 0,87 | 726 | 33,5 | 12,9 | 36,7 |
| GPT-5.6 Luna | 1,00 | 0,758 | 929 | 902 | 0,85 | 511 | 26,2 | 13,2 | 10,2 |
| Muse Spark 1.3 | 0,68 | 0,661 | 871 | 882 | 8,54 | 500 | 19,2 | 11,0 | 22,6 |
| GLM 5.3 Flash | 0,89 | 0,523 | 695 | 649 | 0,61 | 568 | 16,5 | 9,0 | 40,2 |

À retenir :

- **la validité est presque résolue** quand l'environnement vérifie
  (plusieurs agents à 1,00) ; **le design ne l'est pas** ;
- l'écart de **Design ELO** entre GLM et Astra vaut ~545 points, soit un judge
  qui préfère Astra dans ~96 % des paires ; l'écart à l'humain reste net :
  dans l'étude perceptive, **323 des 360** comparaisons ont choisi le modèle
  humain, et aucun agent n'a été pris pour un humain plus d'une fois sur cinq ;
- **le rang ne suit pas le prix** : Sol 6.1 égale Astra en ELO pour ~1/5 du
  coût ; Opus 5 coûte 18,80 $ par Set ;
- **les composants explosent** chez les agents faibles : 22 à 40 composants
  pour Muse/Qwen/DeepSeek/GLM, contre 2 à 4 pour Astra/Sol/Opus. La scène est
  éclatée en objets posés côte à côte, pas construite ;
- **la texture est le point faible du VQA** (49–83 % de réussite), alors que la
  couleur dépasse 91 % ; viennent ensuite le type d'objet et son état. C'est
  exactement le vocabulaire qui manque à legoCAD : surfaces, matières,
  éléments reconnaissables, pas seulement des volumes colorés ;
- sur 137 assemblies invalides du set de référence : 44 sans build, 41
  instables, 31 en collision, 21 hors contrainte de pièces.

### 2.4 Ce que le papier ne mesure pas

- **la notice et l'ordre de montage** : aucun score de constructibilité pas à
  pas, aucune nomenclature, aucun test « un humain peut-il suivre la notice » ;
- **la disponibilité commerciale** : une pièce LDraw existe, mais le couple
  pièce/couleur peut ne jamais avoir été produit ; BrickBench ne le vérifie
  pas ;
- **le coût humain** (temps de conception, lisibilité, plaisir de montage) ;
- **la robustesse réelle** : tenons, flexion, pièces lourdes, portées.

C'est précisément l'espace où legoCAD peut se différencier plutôt que de
copier la galerie.

---

## 3. Lecture comparée legoCAD ↔ BrickBench

| Axe | legoCAD aujourd'hui | BrickBench « Set » | Écart / conséquence |
|---|---|---|---|
| Échelle | 5–3 664 pièces ; 8 formes, médiane 0,19 s | 400–4 000 pièces ; scènes de 417 à 3 290 | la taille est atteignable, la **scène** ne l'est pas |
| Bibliothèque | **51 pièces, 43 couleurs** (`pieces_catalog.json`) | **14 441 types** LDraw, 322 couleurs dans la galerie ; 47–68 types utilisés par Set | déficit de vocabulaire, pas de géométrie |
| Connecteurs | tenon → trou/tube uniquement (`studs.py`) | stud, hinge, axle, ball, fixed (BrickNet) | pas de charnières/axes/rotules ; SNOT limité aux bannières |
| Validité | pièces réelles, 0 collision, 0 flottant, **1 seul amas**, `min_stability ≥ 0,8` | pièces + 0 collision + stable ; **plusieurs composants admis** | legoCAD est **plus strict** sur la connexité, moins riche sur les attaches |
| Physique | chemin de charge, support direct, basculement par joint | rigid-body PyBullet, 3 LDU, pas de force des tenons | deux proxys différents ; aucun n'est une FEM |
| Métriques | `coverage`, `islands`, `unsupported`, `min_stability`, `availability`, `mix_similarity`, score A–D | Valid, VQA, Align ELO, Design ELO, Cost | legoCAD mesure la fabricabilité, pas la **qualité de design** |
| Évaluation visuelle | aperçu SVG/LeoCAD, pas de protocole multi-vues | **8 vues** 1024², cadrage fixe, judge VLM + humains | pas de banc visuel comparable |
| Livrables | `.ldr`, BOM, wanted list, notice A4, sous-ensembles, `report.json` | `.mpd` + `.py` + 8 vues ; **pas de notice/BOM/steps** | legoCAD est **meilleur** ici ; ne pas régresser |
| Coût | déterministe, ~0,2 s/modèle, LLM optionnel | 0,61–18,80 $ par Set, jusqu'à 300 tours d'agent | legoCAD peut rester bon marché, mais doit investir dans le design |
| Structure du code | compilateur volume → briques, validation | agent qui écrit `build.py`, `check()` nomme les pièces fautives | les deux sont "structure-as-code" ; BrickAgent a un meilleur **feedback local** |

Conclusion de la comparaison : BrickBench n'est pas un concurrent frontal de
legoCAD. C'est un **étalon de scène et de design**. legoCAD a déjà la
fabricabilité, la notice et le coût ; il lui manque la **composition**, le
**vocabulaire de détail**, les **personnages/props** et une **évaluation
visuelle multi-vues**.

---

## 4. Vingt enseignements de design observés

Convention d'effort : **S** < 1 jour, **M** 2–5 jours, **L** 1–2 semaines
(avec tests et non-régression du banc 8/8).

### L1 — La scène est un diorama : sol, fond, une face ouverte

**Observé.** Les meilleurs Sets ne sont pas des objets flottants : ils ont une
plaque de sol, un mur de fond et une face avant ouverte. `set-077-astra`
(restaurant) a un sol carrelé, une cloison arrière avec banquette et comptoir,
et le quatrième mur absent. `set-051-astra` (maison rose) est une maison de
poupée coupée en façade. `set-021-astra` (locomotive dans la maison) combine
une façade coupée et un sol de jardin.

**À faire.** Ajouter un **composeur de diorama** : empreinte au sol, bord de
base, mur(x) de fond, orientation d'ouverture, zone de caméra. Le compilateur
doit accepter un volume « scène » composé de plusieurs volumes (bâtiment,
sol, props) au lieu d'un seul bloc.

**Module.** nouveau `tools/scene.py` (ou `tools/shapes.py` + `tools/voxel.py`)
· **Effort M**.

### L2 — Le socle est un objet de design, pas un reste de voxels

**Observé.** `set-077-astra` a un socle à deux niveaux, bord sombre et surface
tiled avec liseré ; `set-041-astra` pose la boule sur un socle tan en tuiles
2×4 ; `set-052-brickwright` a un trottoir gris et une base claire ;
`set-096-astra` a un bord sombre et un sol sable texturé. Le socle **cadre**
la scène et masque les irrégularités de bord.

**À faire.** Généraliser `_foundation`/baseplate : bordure de 2 plaques,
retrait ou débord contrôlé, socle 2×2/4×4/8×8 en plaques, et **choix de couleur
de socle** (noir, tan, gris) selon la scène. Aujourd'hui la baseplate 32×32
n'est posée que si l'empreinte est exactement standard.

**Module.** `tools/brickify.py` (`_foundation`, `baseplate`) · **Effort S/M**.

### L3 — Le sol raconte le lieu (carrelage, planches, eau, sable)

**Observé.** `set-077-astra` : damier de tuiles 1×1 beige/brun, très lisible.
`set-077-opus55` : damier beige/brun plus large, avec bordure. `set-097-brickwright` :
mer fendue en **murs d'eau** stratifiés (briques, plaques, pentes inversées).
`set-083-astra` : fond marin en plaques et petites plantes. `set-096-astra` :
sable en plaques avec motifs de studs.

**À faire.** Ajouter des **matériaux de sol procéduraux** : `checker`,
`planks`, `water`, `sand`, `cobble`, `grass`, avec épaisseur, motif, palette et
budget de pièces. Le sol doit être compilé comme une surface, pas comme un
remplissage.

**Module.** `tools/shapes.py` + `tools/brickify.py` · **Effort M**.

### L4 — Une silhouette forte avant les détails

**Observé.** `set-003-brickwright` (forteresse tête de tortue) est
reconnaissable à 20 mètres : une grande gueule, des dents, des sourcils, des
tours. `set-041-astra` est une boule hérissée d'objets. `set-083-astra` est
une épave avec des mâts et des voiles. Dans les trois cas, la silhouette
externe porte le sujet ; les détails viennent après.

**À faire.** Ajouter un **score de silhouette** : rendu binaire par vue
(avant/arrière/gauche/droite), comparaison à une silhouette cible ou à un
ensemble de primitives, et pénalité si le contour est un pavé. Utiliser ce
score dans `quality.py` et dans la boucle de correction.

**Module.** `tools/quality.py` + `tools/preview_svg.py` · **Effort M**.

### L5 — Contraste d'échelle : le géant et le témoin

**Observé.** `set-021-astra` oppose une locomotive géante à une maison, une
voiture et deux minifigs. `set-003-brickwright` place un unique minifig sur
l'herbe pour donner l'échelle de la forteresse flottante. `set-096-astra`
aligne 24 minifigs dans les gradins, face à deux quadriges.

**À faire.** Introduire une **figure d'échelle** (minifig ou personnage
brick-built) et une **contrainte de ratio** : objet héros 1,5–4× la taille du
contexte ; au moins un élément de référence humain. Vérifier que l'échelle est
cohérente entre personnages et architecture.

**Module.** nouveau `tools/figures.py` + `tools/quality.py` · **Effort L**.

### L6 — Deux grammaires de personnage, à choisir par entité

**Observé.** `set-077-opus55` utilise des **minifigs** (têtes, cheveux, torse,
jambes) pour les femmes et un **chat brick-built** surdimensionné : le chat
n'existe pas en minifig, donc il est construit. `set-077-astra` construit
**tous** les personnages en briques, avec des têtes cubiques, des cheveux en
pentes et des yeux en tuiles imprimées. `set-096-astra` utilise des minifigs
en masse. Les deux grammaires fonctionnent, mais **pas mélangées au hasard**
dans la même scène.

**À faire.** Créer un **kit personnage** avec deux modes : `minifig` (tête,
torse, jambes, mains, cheveux) et `brick-built` (tête 3–5 studs, yeux, bouche,
cheveux en pentes). Une règle de cohérence : une scène choisit une grammaire
dominante ; les exceptions (animal, statue) sont justifiées.

**Module.** nouveau `tools/figures.py`, `pieces_catalog.json` · **Effort L**.

### L7 — Les visages et les gestes portent le récit

**Observé.** `set-077-astra` : sourcils, yeux ronds, bouche ouverte, bras
tendu, doigts ; le chat a des yeux, un nez, une bouche et des oreilles.
`set-003-brickwright` : dents blanches, yeux, sourcils, narines. `set-021-astra` :
visage souriant de la locomotive. `set-096-astra` : les minifigs sont
simplement posées, mais la scène (chars, chevaux, gradins) raconte l'action.

**À faire.** Ajouter des **primitives d'expression** : yeux (tuile ronde
imprimée ou 1×1), bouche (tuile 1×2, slope), sourcils (slope 1×1), nez
(round plate), oreilles (slope/cone). Ajouter une **pose de bras** par
rotation de charnière ou SNOT ; à défaut, des bras fixes mais orientés.

**Module.** `tools/figures.py` + `tools/snot.py` · **Effort L**.

### L8 — Les accessoires créent la densité visuelle

**Observé.** `set-077-opus55` : gobelets transparents, bouteille de vin,
assiettes, serviettes pliées, bol de salade, couverts — pour 417 pièces
seulement. `set-077-astra` : verres à pied, assiettes, salade, couverts,
comptoir, banquette. `set-041-astra` : chaise, télévision, parapluie, poêle,
banane, livres accrochés à la boule. `set-052-brickwright` : auvent rayé,
enseigne, portes vitrées.

**À faire.** Ajouter une passe **props** : grappes de 3–8 petits objets
autour d'un point focal (table, comptoir, sol), avec support vérifié et
budget. Commencer par une bibliothèque de 10–15 props réutilisables (verre,
assiette, bouteille, livre, caisse, pot de fleur, panneau, outil).

**Module.** nouveau `tools/props.py`, `pieces_catalog.json` · **Effort M**.

### L9 — La végétation structure et encadre

**Observé.** `set-077-opus55` encadre la scène avec deux grands palmiers et
des plantes en pot ; `set-064-astra` est une forêt de champignons géants
(271 tuiles rondes 1×1, 171 plaques rondes, 128 briques rondes, 90 cônes) ;
`set-010-opus55` sème des buissons et des rochers autour de la table ;
`set-083-astra` ajoute des coraux et des algues sur le fond marin.

**À faire.** Ajouter une famille **végétation** : tige (round brick), feuille
(leaf/plant), champignon (round plate + cone), buisson (round plates), arbre
(tronc + feuillage). Une passe de **scatter** avec règles : pas dans les
circulations, pas devant un visage, densité plus forte sur les bords.

**Module.** `tools/shapes.py` + `tools/props.py` · **Effort M**.

### L10 — Rochers, strates et eau : la matière avant le détail

**Observé.** `set-010-opus55` : amas de rochers gris (slopes, round bricks)
en plusieurs tailles. `set-097-brickwright` : murs d'eau en strates
horizontales, pentes inversées et plaques. `set-083-astra` : épave et fond
marin en plaques, pentes et petits coraux. `set-021-astra` : jardin en plaques
vertes, gravier, bordure.

**À faire.** Créer des **primitives de terrain** : `rock_cluster`,
`strata_wall`, `water_wall`, `sand_dune`, `grass_patch`, avec variantes de
taille et de couleur. Elles doivent être compilables (pas des décorations
flottantes) et réutilisables dans plusieurs scènes.

**Module.** `tools/shapes.py`, `tools/slopes.py` · **Effort M**.

### L11 — Studs exposés et tiles : une texture, pas un défaut

**Observé.** `set-077-astra` : sol et murs entièrement tiled, mais le dessus de
la banquette et certains murs gardent des **studs exposés**. `set-077-opus55` :
mur de cloison avec studs visibles, sol tiled. `set-083-astra` : coque en
plaques lisses, mât en briques à studs. `set-041-astra` : boule couverte de
studs, objets lisses. Les sets alternent **lisse** (tile) et **texturé**
(stud), souvent pour distinguer matériaux et zones.

**À faire.** Remplacer le `tile_cap` systématique par une **carte de
matières** : chaque région a un matériau (`smooth`, `studded`, `trans`,
`metallic`) et une couleur. Le taux de tiles doit être un paramètre (10–30 %
typique), pas 100 % des sommets. Les studs exposés sont autorisés et comptés
comme texture.

**Module.** `tools/brickify.py` (`_tile_layer`, `tile_cap`), `tools/voxel.py`
· **Effort M**.

### L12 — Discipline de palette : peu de couleurs, un accent

**Observé.** `set-045-astra` : 9 couleurs, tout en gris/blanc, avec des
minifigs colorés comme seuls accents. `set-051-astra` : structure blanche,
accent rose, eau bleu clair. `set-097-brickwright` : bleu/blanc/beige, 21
couleurs mais une dominante très claire. `set-052-brickwright` : tan, gris,
orange/vert de l'enseigne. Les meilleurs Sets tournent autour de **9–20
couleurs**, avec 2–3 familles neutres et 1–2 accents.

**À faire.** Ajouter une **direction artistique** : palette de 8–12 couleurs
+ 2 accents, rôles (structure, sol, accent, trans), et un contrôle de
cohérence (pas de couleur isolée, pas de patch de 1 pièce). `clean_colors`
actuel fusionne les taches ; il faut choisir la palette **avant** de colorier.

**Module.** `tools/quality.py`, `tools/bom.py`, `tools/voxel.py` · **Effort S/M**.

### L13 — Les pièces rondes font l'organique

**Observé.** `set-064-astra` : 76 % de pièces de la famille ronde/cône (tuiles rondes
1×1, plaques rondes, briques rondes, cônes, plaques 4×4 à coin rond) pour les
champignons et les tiges. `set-077-opus55` : 19 % de round (gobelets, plantes,
pieds de table). `set-097-brickwright` : 11 %, surtout des plaques rondes 2×2
et des cônes. `set-051-astra` : 9 %, bassin et fleurs.

**À faire.** Enrichir la famille **round** : plaques rondes 1×1/2×2, briques
rondes 1×1/2×2, cônes 1×1/2×2, dômes, quarter-round, plates with corner
round. Ajouter une préférence de remplacement des angles et des extrémités
(arbres, poteaux, champignons, gobelets) par des pièces rondes.

**Module.** `pieces_catalog.json`, `tools/brickify.py` (`_roundify`) ·
**Effort M**.

### L14 — Accents métalliques, imprimés et lettrage

**Observé.** `set-077-astra` : couverts et gobelets en **pearl gold**,
assiettes et verres transparents. `set-096-astra` : casques et armures
métalliques, lettrage **ROMA** construit dans le sol. `set-052-brickwright` :
enseigne et auvent. `set-003-brickwright` : dents blanches et accents lime.

**À faire.** Ajouter une petite famille **accent** : pearl gold/silver, trans
clear/light blue, tuiles imprimées (yeux, bouche, panneau), et un générateur
de **lettrage** simple (5×7) pour les enseignes. Vérifier la disponibilité de
ces couples avec `data/part_colors.json`.

**Module.** `pieces_catalog.json`, `tools/patterns.py`, `tools/instructions.py`
· **Effort S/M**.

### L15 — Une scène peut avoir plusieurs composants — et doit le dire

**Observé.** La galerie accepte des scènes en plusieurs morceaux : le chat, la
table et les personnages peuvent être des composants séparés, chacun stable.
Les meilleurs agents restent à **2–4 composants** ; les faibles explosent à
**22–40** (Muse, Qwen, DeepSeek, GLM). `set-077-opus55` a des personnages
posés sur des chaises, une table et un chat : plusieurs objets, une scène
lisible.

**À faire.** Remplacer le verdict binaire `islands == 1` par un **rapport de
composants** : nombre, taille, stabilité de chacun, rôle (décor, personnage,
prop). Un modèle objet reste `islands == 1` ; un modèle scène accepte 2–6
composants **stables** et pénalise au-delà. `unsupported` reste interdit.

**Module.** `tools/studs.py`, `tools/stability.py`, `tools/quality.py` ·
**Effort M**.

### L16 — Les sous-ensembles sont des modules réutilisables

**Observé.** `set-077-brickwright` contient **46 sous-modèles** nommés
(`cat_upholstered_chair`, `blonde___leaning...`, `left_restraining_forearm`,
etc.) et 88 types de pièces. `set-096-astra` a 36 sous-modèles (chars,
chevaux, gradins). `set-021-astra` en a 10. Le script `.py` définit
des fonctions `dining_chair()`, `human_head()`, puis les assemble : c'est du
**structure-as-code** lisible et réutilisable.

**À faire.** Exposer une API de **sous-assemblage** dans le pipeline volume :
`Assembly(name)`, `add`, `attach`, `mirror`, `place`, puis composition. Les
sous-ensembles doivent être conservés dans le `.ldr`/`.mpd` et dans la notice.
Aujourd'hui `studs.subassemblies()` les **recalcule après coup** pour la
notice ; il faut les déclarer à la construction.

**Module.** `tools/voxel.py`, `tools/ldr_io.py`, `tools/instructions.py` ·
**Effort M/L**.

### L17 — La variété de pièces est un objectif mesurable

**Observé.** En Set, les bons modèles utilisent **47 à 69 types en moyenne**
(jusqu'à 88 sur un modèle) et **13 à 22 couleurs** ; les modèles pauvres
tombent à **16–39 types** (GLM 16,5 ; Muse 19,2 ; DeepSeek 33,5) et se
rabattent sur des plaques 1×1. legoCAD
produit aujourd'hui **3 à 41 types** par forme, avec un catalogue de 51
pièces. `set-097-brickwright` montre qu'on peut faire très bien avec **22
types**, mais ces 22 types sont **choisis** (pentes, round, tuiles) et non
subis.

**À faire.** Ajouter un **objectif de variété** dans le score : nombre de
types, entropie de la distribution, part du type dominant, ratio
brique/plaque/tuile/pente/round. Cibler 25–50 types pour une scène de 600–
1 500 pièces, sans tomber dans le saupoudrage.

**Module.** `tools/quality.py`, `tools/bom.py`, `tools/bench.py` ·
**Effort S**.

### L18 — Huit vues valent mieux qu'un hero shot

**Observé.** Chaque fiche de la galerie fournit 8 vues (rotation + front),
et le papier juge le design sur **4 vues** par paire. C'est ce qui révèle les
scènes plates ou les dos non finis : `set-077-glm` est une plaque avec quatre
figurines, vue de face ; les modèles d'Astra tiennent de dos (cloison,
comptoir, socle).

**À faire.** Standardiser un **banc 8 vues** : 8 PNG 1024², planche contact,
vue frontale marquée, cadrage automatique. Ajouter un contrôle « dos non
vide » : une scène ne doit pas être un décor de théâtre à une seule face.
Aujourd'hui `preview_svg`/LeoCAD rendent quelques vues, pas un protocole.

**Module.** `tools/bench.py`, `tools/preview_svg.py`, `tools/render.py` ·
**Effort M**.

### L19 — La notice est un livrable de design, pas une annexe

**Observé.** La galerie ne fournit **aucune notice, aucun BOM, aucun step**
(0 `0 STEP` dans les 17 `.mpd` analysés). Or un set se juge aussi à sa
constructibilité : sous-ensembles, sacs, callouts, ordre. legoCAD a déjà
`instructions.py` (inventaire, étapes, pièces ajoutées, sous-ensembles,
avertissements) et `build_order.py` (validation de l'ordre). C'est un
**avantage à conserver et à mettre en avant**, pas à aligner sur BrickBench.

**À faire.** Ajouter au `.mpd` les `0 STEP` calculés, exporter le **script
source** (`.py` ou `.json`) à côté du `.ldr`, et lier chaque étape de la
notice à un sous-ensemble. Un modèle BrickBench est reproductible par son
`.py` ; legoCAD doit offrir la même provenance **et** la notice.

**Module.** `tools/instructions.py`, `tools/ldr_io.py`, `tools/make_model.py`
· **Effort S/M**.

### L20 — Les échecs de la galerie sont des garde-fous gratuits

**Observé.** Les cas invalides sont instructifs : `set-077-glm` = 425 plaques
1×1 sur 466 pièces (92 %), 40 composants, collision ; `set-077-deepseek` =
74 % de tuiles, 420 pièces, 2 sous-modèles, personnages très grossiers ;
`set-060-muse` = 1 pièce ; `set-010-muse` = `no build` ; `set-072-muse` =
20 pièces. À l'inverse, `set-077-astra` = 60 % de tuiles 1×1, 1 809 pièces :
beau mais irréaliste en set retail (coût, répétition).

**À faire.** Ajouter des **détecteurs d'anti-patterns** : part du type
dominant, part de plaques 1×1, part de tuiles, nombre de composants, pièces
près du plancher (400 ± 5), base vide (surface de socle non utilisée),
ratio pièces visibles/pièces totales. Les afficher dans `report.json` avec une
raison, sans bloquer la génération.

**Module.** `tools/quality.py`, `tools/bench.py` · **Effort S**.

---

## 5. Dix actions priorisées pour legoCAD

Chaque action est indépendante et se mesure avec l'outillage existant
(`tools/bench.py`, `report.json`, `bom.csv`). Les efforts sont ceux définis
plus haut.

### A1 — Mode « scène » multi-composants (P0, M)

**Quoi.** Séparer la notion d'**objet** (un seul amas) de la notion de
**scène** (2–6 composants, chacun stable). `report.json` expose
`components[]` avec taille, stabilité, rôle ; `quality.validity()` accepte une
scène si tous les composants sont stables et sans collision.

**Critère de succès.** 10 scènes de 400–1 500 pièces, 2–6 composants,
**100 % des composants** avec stabilité ≥ 0,9, 0 collision, 0 pièce
`unsupported` ; les 8 formes du banc restent 8/8 valides avec `islands == 1`.

### A2 — Composeur de diorama (P0, M)

**Quoi.** Un `scene.py` qui pose : socle (bord 2 plaques), sol matériel
(damier/planches/eau/sable), mur de fond, une face ouverte, zone caméra. Il
compose des volumes produits par `shapes.py`/`brickify.py`.

**Critère de succès.** 5 archétypes (restaurant, marché, port, arène,
intérieur) générés en < 5 s ; base couvrant 100 % de l'empreinte ; bord
≥ 2 plaques ; 1 sol patterné ; 1 mur de fond ; 0 `unsupported` ; 8 vues
exportées par scène.

### A3 — Palette de détail v1 + mode inventaire (P0, L)

**Quoi.** Passer de **51 à ≥ 110 pièces** curées, avec ≥ 12 familles :
arches, fenêtres/vitrages, panneaux, plaques/briques rondes, cônes/dômes,
végétation, brackets SNOT (87087, 11211), minifig (tête/torse/jambes/mains),
barres/clips, tuiles imprimées, trans, metallic. Chaque pièce a ses
connecteurs, sa hauteur et ses couples couleur observés. Ajouter un mode
`--inventory` (budget 400–1 500 pièces, types max).

**Critère de succès.** 10 scènes sans **aucune** pièce inconnue à l'export
LDraw ; `availability ≥ 0,90` ; BOM ≤ 120 lignes ; `bench --shapes` 8/8 ;
temps médian < 2 s (château ≤ 6 s).

### A4 — Kit personnage (P0/P1, L)

**Quoi.** Deux constructeurs : `minifig` (tête, torse, jambes, mains,
cheveux) et `brick-built` (tête 3–5 studs, yeux, bouche, cheveux, oreilles),
avec poses de bras (SNOT/charnière) et cohérence d'échelle dans la scène.

**Critère de succès.** 3 scènes avec ≥ 3 personnages ; 100 % des pièces
attachées ; chaque visage a ≥ 2 yeux + 1 bouche ; tête entre 3 et 5 studs ;
3/3 personnages reconnus par un VLM ou un humain sur les 8 vues ; aucune
régression de validité.

### A5 — Props et végétation (P1, M)

**Quoi.** Bibliothèque de 12–20 props (verre, assiette, bouteille, livre,
caisse, pot, panneau, outil, fleur, champignon, buisson, palmier) et passe de
scatter par grappes autour des points focaux, avec support vérifié.

**Critère de succès.** 15–30 props par scène ; 100 % supportés ; ≤ 12 nouveaux
types par scène ; ≥ 3 grappes distinctes ; surcoût ≤ 20 % de pièces ; pas de
collision ; rendu où les props sont identifiables sur ≥ 4 vues.

### A6 — Matières et textures (P1, M)

**Quoi.** Une carte de matériaux par région (`smooth`, `studded`, `trans`,
`metallic`) et un budget de tiles (10–30 %), avec trans clear/light blue pour
l'eau/verre, et studs exposés volontaires. Remplacer `tile_cap` global par une
règle locale.

**Critère de succès.** Sur 5 scènes : taux de tiles 10–30 % (hors surface
eau) ; ≥ 3 matériaux distincts (dont ≥ 1 trans) ; ≥ 1 surface à studs
exposés ; checklist visuelle 5/5 ; 0 régression de stabilité ;
`mix_similarity` ≥ 0,5.

### A7 — Direction artistique couleur (P1, S/M)

**Quoi.** Palette choisie avant coloriage : 8–12 couleurs + 2 accents, rôles
(structure/sol/accent/trans), contrôle des patches isolés et des couleurs non
disponibles. Remplacer `clean_colors` seul par un plan de palette.

**Critère de succès.** ≤ 12 couleurs (+ 2 accents) sur 10 scènes ; ≥ 50 % de
pièces neutres ; distribution à ≤ 20 % de la distribution OMR ; `availability
≥ 0,90` ; aucune couleur isolée de 1 pièce.

### A8 — Banc 8 vues + score de silhouette (P1, M)

**Quoi.** `bench.py --views 8` : 8 PNG 1024², planche contact, vue frontale,
score de silhouette par vue (occupation, symétrie, complexité du contour),
contrôle « dos non vide ».

**Critère de succès.** 100 % des lignes du banc produisent 8 vues + planche ;
score de silhouette calculé et baseline enregistrée ; géométrie < 2× le temps
actuel et rendu 8 vues < 60 s/modèle ; 8/8 formes toujours valides ; au moins
3 scènes avec un dos non vide.

### A9 — Garde-fous anti-patterns (P0, S)

**Quoi.** Détecteurs dans `quality.py` : type dominant > 60 %, plaques 1×1
> 40 %, tuiles > 50 %, composants > 10, pièces 395–405 (jeu du plancher),
socle vide > 50 %, ratio pièces visibles/total < 0,5. Sortie : `flags[]` avec
raison et sévérité, sans bloquer.

**Critère de succès.** 6 cas synthétiques détectés 6/6 (dont les profils
GLM/DeepSeek/Muse) ; 0 faux positif sur les 8 formes de référence ; chaque
flag apparaît dans `report.json` et dans le bench.

### A10 — Notice, provenance et sous-ensembles (P2, S/M)

**Quoi.** Écrire les `0 STEP` calculés dans le `.mpd`, exporter le script
source (`.py`/`.json`) à côté du `.ldr`, conserver les sous-ensembles déclarés
dans la notice, et lier chaque étape à ses pièces ajoutées. C'est le
différenciateur face à la galerie BrickBench.

**Critère de succès.** 100 % des sets : `.ldr`/`.mpd` avec steps + `.py`/`.json`
source + `notice.html` + BOM + wanted list ; `build_errors = 0` sur 10/10
scènes ; ≥ 1 sous-ensemble réutilisé par scène ; une notice rejouée à la main
sur 1 scène sans pièce manquante.

---

## 6. Ce qu'il ne faut pas copier

1. **Le catalogue complet (14 441 types, 322 couleurs).** Ce n'est pas un
   objectif : disponibilité commerciale non vérifiée, collisions et
   connecteurs à modéliser, temps de recherche. Viser 110–150 pièces
   **choisies** couvre l'essentiel du langage de set.
2. **Le tapis de plaques/tuiles pour atteindre 400 pièces.** GLM 5.3 :
   425 plaques 1×1 sur 466 pièces (92 %), 40 composants, invalide. DeepSeek :
   74 % de tuiles, 420 pièces. La contrainte de nombre de pièces doit être un
   **plancher de scène**, pas un objectif à remplir.
3. **Le tapis de tuiles 1×1 « partout ».** `set-077-astra` : 1 093 tuiles 1×1
   sur 1 809 pièces (60 %). C'est superbe en rendu, mais coûteux, répétitif et
   masque la construction. Plafonner le taux de tuiles et privilégier des
   tuiles plus grandes.
4. **Les scènes éclatées en 20–40 composants.** Ce n'est pas une scène, c'est
   un dépôt d'objets. Les bons modèles restent à 2–4 composants. Pénaliser
   au-delà de 6–8.
5. **Le coût et les 300 tours d'agent.** 0,61–18,80 $ par Set, jusqu'à 300
   tours. legoCAD doit garder son compilateur déterministe et réserver le LLM
   à la **direction artistique** (palette, layout, choix de props), pas au
   placement pièce à pièce.
6. **Le VQA/ELO comme unique KPI.** Le VQA sature (0,95 pour Astra) et le
   judge VLM coûte cher ; l'ELO dépend d'un panel. Utiliser ces métriques comme
   **audit trimestriel**, pas comme boucle d'optimisation quotidienne.
7. **L'absence de livrables.** La galerie ne fournit ni notice, ni BOM, ni
   steps. Un `.mpd` sans `0 STEP` n'est pas un set. Ne pas aligner legoCAD sur
   ce minimum.
8. **La stabilité « rigid-body » présentée comme vérité physique.** Le papier
   l'assume : pas de force de tenon, pas de FEM. legoCAD doit garder son
   critère de basculement, mais éviter de promettre « constructible » au-delà
   de ce qui est réellement vérifié.
9. **Les sculptures pleines de 2 300 pièces en 26 types.** `set-003` est
   impressionnant mais répétitif et lourd ; un set retail préfère une coque,
   des sous-ensembles et des détails. Ne pas confondre **masse** et **design**.
10. **Le rendu unique comme juge.** Une seule vue hero favorise les décors de
    théâtre ; la galerie elle-même utilise 8 vues. Toujours juger sur plusieurs
    angles, y compris le dos.

---

## 7. Sources consultées (14 novembre 2026)

- Galerie BrickBench, onglet Set : <https://gallery.brickben.ch/?s=set>
  (et pages `?b=set-001-astra`, `?b=set-003-brickwright`,
  `?b=set-010-opus55`, `?b=set-021-astra`, `?b=set-041-astra`,
  `?b=set-045-astra`, `?b=set-051-astra`, `?b=set-052-brickwright`,
  `?b=set-064-astra`, `?b=set-077-astra`, `?b=set-077-opus55`,
  `?b=set-077-brickwright`, `?b=set-077-deepseek`, `?b=set-077-qwen`,
  `?b=set-077-glm`, `?b=set-083-astra`, `?b=set-096-astra`,
  `?b=set-097-brickwright`, `?b=set-060-muse`, `?b=set-010-muse`).
- Fichiers `.mpd` et `.py` téléchargés depuis
  `https://brickbench-gallery-set.culfre.workers.dev/files/<id>.mpd` et
  `.py` (17 `.mpd`, 7 `.py`), analysés localement.
- Page projet BrickBench : <https://brickben.ch/>.
- Papier : Kulits, Xu, Jones, Schmid, Wu, *BrickBench: Evaluating Agentic
  Brick Design*, arXiv:2610.12452v1, 8 octobre 2026 —
  <https://arxiv.org/abs/2610.12452> et
  <https://arxiv.org/html/2610.12452v1> (sections 3.2, 4.1–4.4, 5, 6,
  Table 1, Table A1).
- BrickAgent (environnement, API `Assembly`, `attach`, `check`, `view`,
  validation, 2 369 questions Set, 8 vues) :
  <https://github.com/kulits/BrickAgent>.
- BrickNet (connecteurs stud/hinge/axle/ball/fixed, dataset LDraw) :
  <https://kulits.github.io/BrickNet/>.
- État interne de legoCAD : `README.md`, `docs/APPROACH.md`,
  `tools/brickify.py`, `tools/slopes.py`, `tools/snot.py`, `tools/studs.py`,
  `tools/stability.py`, `tools/bench.py`, `tools/instructions.py`,
  `tools/quality.py`, `pieces_catalog.json`, `data/part_colors.json` ;
  banc exécuté le 14/11/2026 (`python3 tools/bench.py --shapes`).
