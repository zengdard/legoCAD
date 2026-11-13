#!/usr/bin/env python3
"""Connexions réelles entre pièces LEGO : les *studs*, pas le voisinage.

Une brique LEGO ne se fixe QUE par le dessus : les tenons (studs) de la pièce
du dessous entrent dans le dessous (tubes) de la pièce du dessus. Deux pièces
posées côte à côte au même niveau ne sont **pas** attachées — même si elles se
touchent dans le rendu 3D.

C'est la différence entre un modèle "joli à l'écran" et un modèle réellement
constructible : `stability.py` (version historique) considérait l'accolement
latéral comme un appui, ce qui valide des planchers et des ailes qui tombent
dès qu'on soulève le modèle. Ce module fournit le graphe de connexions exact :

  - `connections(model)` : arêtes étud → tube entre pièces empilées ;
  - `support(model)`     : pour chaque pièce, les pièces qui la portent, le
                           nombre de studs réellement engagés, la fraction de
                           son empreinte posée ;
  - `report(model)`      : amas, pièces non attachées au sol, pièces tenues
                           par un seul stud, statistiques de connexion.

Le sol (y=0) est traité comme un support (table ou plaque de base).
"""
from __future__ import annotations

from ldraw_model import LDU_PER_LEVEL, part_levels

# Pièces dont le dessus n'a pas de tenons : rien ne peut s'y fixer.
_NO_TOP_STUDS = ("tile", "smooth", "printed tile", "grille")


def has_top_studs(part: dict) -> bool:
    """Vrai si la pièce possède des tenons sur sa face supérieure."""
    desc = str(part.get("desc", "")).lower()
    kind = str(part.get("kind", "")).lower()
    if kind == "tile":
        return False
    if any(word in desc for word in _NO_TOP_STUDS):
        # « Tile 1 x 2 » n'a pas de tenons ; « Brick with studs on side »
        # en a sur le côté mais pas forcément dessus : on reste prudent.
        return False
    return True


def part_geometry(model, index: int) -> dict:
    """Géométrie d'une pièce en unités de construction (studs / plaques)."""
    b = model.bricks[index]
    part = model.part(b["part_id"])
    sx, sz = model._footprint(part, b["rot"])
    h = part_levels(part)
    cells = frozenset((b["x"] + dx, b["z"] + dz)
                      for dx in range(sx) for dz in range(sz))
    return {
        "index": index,
        "part": part,
        "base": b["y"],
        "top": b["y"] + h,
        "height": h,
        "footprint": cells,
        "top_studs": has_top_studs(part),
        "y": b["y"],
    }


def bottom_owner(model, geoms: list[dict] | None = None) -> dict:
    """Carte (x, niveau_plaque, z) -> indice de la pièce qui occupe la cellule.

    Un voxel n'appartient qu'à une pièce : les collisions sont interdites en
    amont (LDrawModel.place). Le dernier posé gagne, comme dans le reste du
    projet."""
    geoms = geoms if geoms is not None else [part_geometry(model, i)
                                             for i in range(len(model.bricks))]
    owner: dict[tuple, int] = {}
    for g in geoms:
        i = g["index"]
        for (cx, cz) in g["footprint"]:
            for cy in range(g["base"], g["top"]):
                owner[(cx, cy, cz)] = i
    return owner


def _support_edges(model, geoms: list[dict]) -> list[dict]:
    """Arêtes étud → tube : pièce i posée sur la pièce j, avec le nombre de
    studs en contact. Ne compte que les contacts strictement verticaux
    (top(j) == base(i)) et les pièces du dessous qui ont des tenons."""
    by_top: dict[int, list[int]] = {}
    for g in geoms:
        if g["top_studs"]:
            by_top.setdefault(g["top"], []).append(g["index"])
    edges = []
    for g in geoms:
        i = g["index"]
        if g["base"] <= 0:
            continue
        # la pièce du dessous a son dessus exactement au niveau du dessous :
        # son intervalle est [base, top) et elle couvre la plaque base-1
        for j in by_top.get(g["base"], []):
            gj = geoms[j]
            studs = len(g["footprint"] & gj["footprint"])
            if studs:
                edges.append({"below": j, "above": i, "studs": studs})
    return edges


def support(model) -> dict:
    """Rapport de support pièce par pièce.

    Retourne :
      geoms      : géométrie de chaque pièce
      edges      : connexions étud → tube
      below      : {index: [(piece_du_dessous, studs), ...]}
      studs      : {index: nombre total de studs engagés vers le bas}
      fraction   : {index: fraction de l'empreinte posée sur une pièce}
      contact    : {index: set(cellules (x,z) en contact avec le dessous)}
      ground     : {index: True si la pièce touche le sol}
    """
    geoms = [part_geometry(model, i) for i in range(len(model.bricks))]
    edges = _support_edges(model, geoms)
    below: dict[int, list[tuple[int, int]]] = {}
    for e in edges:
        below.setdefault(e["above"], []).append((e["below"], e["studs"]))
    studs = {i: sum(s for _, s in lst) for i, lst in below.items()}

    owner = bottom_owner(model, geoms)
    contact: dict[int, set] = {}
    fraction: dict[int, float] = {}
    for g in geoms:
        i = g["index"]
        if g["base"] == 0:
            contact[i] = set(g["footprint"])
            fraction[i] = 1.0
            continue
        cells = {(cx, cz) for (cx, cz) in g["footprint"]
                 if owner.get((cx, g["base"] - 1, cz)) is not None}
        contact[i] = cells
        fraction[i] = len(cells) / max(1, len(g["footprint"]))
    return {"geoms": geoms, "edges": edges, "below": below, "studs": studs,
            "fraction": fraction, "contact": contact,
            "ground": {i: g["base"] == 0 for i, g in
                       enumerate(geoms)}}


def components(model, sup: dict | None = None) -> list[set[int]]:
    """Amas de pièces réellement attachées entre elles (graphe étud)."""
    sup = sup or support(model)
    n = len(model.bricks)
    adj: list[set[int]] = [set() for _ in range(n)]
    for e in sup["edges"]:
        adj[e["below"]].add(e["above"])
        adj[e["above"]].add(e["below"])
    seen: set[int] = set()
    out = []
    for i in range(n):
        if i in seen:
            continue
        stack = [i]
        seen.add(i)
        comp = set()
        while stack:
            k = stack.pop()
            comp.add(k)
            for nb in adj[k]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        out.append(comp)
    return out


def report(model) -> dict:
    """Rapport complet de constructibilité structurelle."""
    if not model.bricks:
        return {"min_stability": 0.0, "mean_stability": 0.0, "islands": 0,
                "unsupported": [], "single_stud": [], "weak": [],
                "support": {}, "connections": 0, "resting": []}
    sup = support(model)
    geoms = sup["geoms"]

    # pieces reliées au sol par une chaîne d'étuds
    reachable = {i for i, g in enumerate(geoms) if g["base"] == 0}
    stack = list(reachable)
    while stack:
        i = stack.pop()
        for e in sup["edges"]:
            if e["below"] == i and e["above"] not in reachable:
                reachable.add(e["above"])
                stack.append(e["above"])
            elif e["above"] == i and e["below"] not in reachable:
                reachable.add(e["below"])
                stack.append(e["below"])
    unsupported = [i for i in range(len(geoms)) if i not in reachable]

    # pièces qui reposent sans être tenues (dessous lisse : tile)
    resting = []
    for i, g in enumerate(geoms):
        if g["base"] > 0 and not sup["below"].get(i) \
                and sup["fraction"][i] > 0:
            resting.append(i)

    single = [i for i, s in sup["studs"].items() if s == 1 and
              i not in unsupported]

    comps = components(model, sup)
    fam = families(model)
    return {
        "geoms": geoms,
        "families": fam,
        "support": sup,
        "connections": len(sup["edges"]),
        "islands": len(comps),
        "component_sizes": sorted((len(c) for c in comps), reverse=True),
        "unsupported": unsupported,
        "resting": resting,
        "single_stud": single,
        "reachable": reachable,
        "min_studs": min((sup["studs"].get(i, 0)
                          for i in range(len(geoms)) if geoms[i]["base"] > 0),
                         default=0),
    }


_FAMILY_PATTERNS = (
    ("snot", ("stud on side", "studs on side", "stud on the side",
              "bracket", "headlight", "stud on")),
    ("ball", ("ball", "socket", "soccer")),
    ("hinge", ("hinge", "clip", "bar ", "handle")),
    ("axle", ("axle", "pin ", "technic", "beam", "gear", "bush")),
)


def connector_family(part: dict) -> str:
    """Famille de connecteur dominante d'une pièce (façon BrickNet).

    stud  : brique/plaque/tuile/pente (le cas de 99 % de nos modèles) ;
    axle  : Technic (pin, axe, beam) ;
    hinge : charnière/clip/barre ;
    ball  : rotule ;
    fixed : pièce sans connexion étudiée (baseplate, décor).
    """
    desc = str(part.get("desc", "")).lower()
    for family, words in _FAMILY_PATTERNS:
        if any(w in desc for w in words):
            return family
    return "stud"


def families(model) -> dict:
    """Répartition des pièces par famille de connecteur."""
    counts: dict[str, int] = {}
    non_stud = []
    for i, b in enumerate(model.bricks):
        fam = connector_family(model.part(b["part_id"]))
        counts[fam] = counts.get(fam, 0) + 1
        if fam != "stud":
            non_stud.append({"index": i, "part": b["part_id"],
                             "family": fam,
                             "desc": model.part(b["part_id"]).get("desc", "")})
    return {"counts": counts, "non_stud": non_stud}


def subassemblies(model, weak_studs: int = 1, min_size: int = 3) -> list:
    """Sous-ensembles : composants séparés par des liaisons faibles.

    On retire les arêtes de **1 seul stud** du graphe de connexions : ce sont
    les charnières naturelles d'un modèle (cheminée, antenne, module
    décoratif). Les groupes restants de taille >= min_size sont des
    sous-assemblages candidats pour la notice (callouts).
    """
    sup = support(model)
    n = len(model.bricks)
    adj: list[set[int]] = [set() for _ in range(n)]
    for e in sup["edges"]:
        if e["studs"] > weak_studs:
            adj[e["below"]].add(e["above"])
            adj[e["above"]].add(e["below"])
    seen: set[int] = set()
    groups = []
    for i in range(n):
        if i in seen:
            continue
        stack = [i]
        seen.add(i)
        comp = set()
        while stack:
            k = stack.pop()
            comp.add(k)
            for nb in adj[k]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        groups.append(comp)
    groups.sort(key=len, reverse=True)
    if len(groups) <= 1:
        return []
    main = groups[0]
    if len(main) < 0.6 * n:
        return []                     # deux moitiés : pas un « module »
    return [sorted(g) for g in groups[1:] if len(g) >= min_size]


def summary_line(rep: dict) -> str:
    """Résumé court pour les logs et le feedback."""
    bits = [f"{len(rep.get('geoms', []))} pièces",
            f"{rep.get('connections', 0)} connexions étud",
            f"{rep.get('islands', 0)} amas"]
    if rep.get("unsupported"):
        bits.append(f"{len(rep['unsupported'])} non attachées au sol")
    if rep.get("single_stud"):
        bits.append(f"{len(rep['single_stud'])} tenues par 1 stud")
    if rep.get("resting"):
        bits.append(f"{len(rep['resting'])} posées sur du lisse")
    fam = rep.get("families", {}).get("counts", {})
    extra = {k: v for k, v in fam.items() if k != "stud"}
    if extra:
        bits.append("connecteurs " + ", ".join(f"{k}:{v}"
                                               for k, v in extra.items()))
    return " | ".join(bits)
