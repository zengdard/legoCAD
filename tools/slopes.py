#!/usr/bin/env python3
"""Pentes LEGO : transformer les marches d'un volume en toits/carénages.

Un volume compilé en briques a une surface en escalier. Une pente (`3040b`,
`3039`, `3037`, `4286`, `3298`) posée sur la marche basse, haute face contre
la marche haute, remplit exactement la marche et donne une surface inclinée.
C'est le gain visuel le plus important pour les toits, capots et nez.

Principe : pour chaque marche verticale de **3 plaques** (une brique), on pose
une pente sur le palier bas, orientée vers l'extérieur. La pente occupe
3 plaques au-dessus du palier ; sa face haute coïncide avec le palier haut.
Aucune pièce n'est retirée (la pente se pose **au-dessus** de la surface).

Unités : le « depth » d'une pente est le nombre de studs dans le sens de la
descente (2 pour 3040b/3039/3037, 3 pour 4286/3298) ; la « width » est la
largeur perpendiculaire (1, 2 ou 4).
"""
from __future__ import annotations

# (depth, width) -> (part_id, description)
SLOPES = {
    (2, 1): "3040b",   # Slope 45 2 x 1
    (2, 2): "3039",    # Slope 45 2 x 2
    (2, 4): "3037",    # Slope 45 2 x 4
    (3, 1): "4286",    # Slope 33 3 x 1
    (3, 2): "3298",    # Slope 33 3 x 2
}

# tuile -> plaque de même empreinte (une pente a besoin de studs dessous)
TILE_TO_PLATE = {
    "3070b": "3024", "3069b": "3023", "63864": "3623", "2431": "3710",
    "6636": "3666", "3068b": "3022", "26603": "3021", "87079": "3020",
}

# direction (dx, dz) -> rotation LDraw (la pente descend vers la direction)
_ROT = {(0, -1): 0, (0, 1): 180, (-1, 0): 90, (1, 0): 270}


def _tops(model) -> dict:
    tops = {}
    for b in model.bricks:
        part = model.part(b["part_id"])
        sx, sz = model._footprint(part, b["rot"])
        h = _height(model, b, part)
        for x in range(b["x"], b["x"] + sx):
            for z in range(b["z"], b["z"] + sz):
                tops[(x, z)] = max(tops.get((x, z), 0), b["y"] + h)
    return tops


def _height(model, b, part) -> int:
    from ldraw_model import LDU_PER_LEVEL, _NOMINAL_H
    return max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)


def _color_above(model, x: int, z: int, top: int) -> str:
    """Couleur de la marche haute : c'est la couleur du toit/carénage."""
    i = model._occupied.get((x, top - 1, z))
    if i is None:
        return "4"
    return str(model.bricks[i]["color"])


def _footprint(n, d, depth, width, perp_sign):
    """Cellules couvertes par une pente de depth × width."""
    dx, dz = d
    px, pz = (-dz, dx)          # perpendiculaire
    cells = set()
    for k in range(depth):
        for w in range(width):
            ox = px * (w if perp_sign >= 0 else -w - 1)
            oz = pz * (w if perp_sign >= 0 else -w - 1)
            cells.add((n[0] + dx * k + ox, n[1] + dz * k + oz))
    return cells


def _origin(n, d, depth, width, perp_sign):
    """Coin (x, z) de la pièce (min des coordonnées couvertes)."""
    cells = _footprint(n, d, depth, width, perp_sign)
    return min(c[0] for c in cells), min(c[1] for c in cells)


def apply(model, max_slopes: int = 2000) -> tuple:
    """Pose des pentes sur les marches de 3 plaques. Retourne (modèle, stats)."""
    tops = _tops(model)
    if not tops:
        return model, {"slopes": 0}
    used = set()
    placed = 0
    for (cx, cz), high in sorted(tops.items()):
        if placed >= max_slopes:
            break
        for d in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            n = (cx + d[0], cz + d[1])
            level = tops.get(n)
            # marche de 3 plaques exactement, palier bas libre
            if level is None or high - level != 3:
                continue
            if any(c in used for c in _footprint(n, d, 2, 1, 1)):
                continue
            # choisit la plus grande pente qui tient sur le palier
            chosen = None
            for depth, width in ((3, 2), (3, 1), (2, 4), (2, 2), (2, 1)):
                if (depth, width) not in SLOPES:
                    continue
                for sign in (1, -1):
                    cells = _footprint(n, d, depth, width, sign)
                    if any(tops.get(c) != level for c in cells):
                        continue
                    if any(c in used for c in cells):
                        continue
                    # chaque cellule doit avoir sa surface en dessous
                    if any((c[0], level - 1, c[1]) not in model._occupied
                           for c in cells):
                        continue
                    chosen = (depth, width, sign, cells)
                    break
                if chosen:
                    break
            if not chosen:
                continue
            depth, width, sign, cells = chosen
            pid = SLOPES[(depth, width)]
            rot = _ROT[d]
            x, z = _origin(n, d, depth, width, sign)
            color = _color_above(model, cx, cz, high)
            # les tuiles n'ont pas de studs : on les remplace par des plaques
            # sous la pente (elles seront cachées)
            replaced = False
            for c in cells:
                i = model._occupied.get((c[0], level - 1, c[1]))
                if i is None:
                    continue
                b = model.bricks[i]
                plate = TILE_TO_PLATE.get(str(b["part_id"]))
                if not plate:
                    continue
                model.remove(i)
                model.place(plate, b["x"], b["z"], b["y"], b["color"],
                            b["rot"])
                replaced = True
            if model.try_place(pid, x, z, level, color, rot):
                used |= cells
                placed += 1
                break                    # une pente par marche
    return model, {"slopes": placed, "added": placed}
