#!/usr/bin/env python3
"""Analyse de stabilité physique d'un modèle LDraw.

Trois contrôles, du plus grave au plus fin :
  1. Chemin de charge — chaque brique doit reposer, directement ou par une
     chaîne de briques, sur le sol (y=0). Une brique sans chemin est instable.
  2. Support direct — fraction de l'empreinte d'une brique réellement posée
     sur une brique du dessous (les porte-à-faux ont un support partiel).
  3. Basculement — à chaque joint horizontal, le centre de gravité de tout ce
     qui est au-dessus doit tomber au-dessus de la zone de contact. C'est le
     critère d'équilibre des moments utilisé par Legolization / StableLego,
     en version discrète (pas de solveur LP nécessaire).

La métrique qui compte est `min_stability` : le maillon faible, comme dans
BrickGPT (une moyenne bonne peut cacher une brique qui fait tout tomber).
"""
from __future__ import annotations

from ldraw_model import LDU_PER_LEVEL, _NOMINAL_H


def _brick_cells(model, b: dict):
    """Cellules (x_plaque, y_plaque, z) couvertes par une brique, et son
    volume en voxels (utilisé comme poids)."""
    part = model.part(b["part_id"])
    sx, sz = model._footprint(part, b["rot"])
    h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
    cells = [(cx, cy, cz)
             for cx in range(b["x"], b["x"] + sx)
             for cz in range(b["z"], b["z"] + sz)
             for cy in range(b["y"], b["y"] + h)]
    return cells, len(cells), (sx, sz, h)


def analyze(model) -> dict:
    """Retourne le rapport de stabilité du modèle."""
    if not model.bricks:
        return {"min_stability": 0.0, "mean_stability": 0.0, "unsupported": [],
                "weak": [], "overhang_cells": 0, "tipping_joints": []}

    parts = [_brick_cells(model, b) for b in model.bricks]

    # index voxel -> brique (le dernier posé gagne ; les collisions sont déjà
    # interdites, donc un voxel n'appartient qu'à une brique)
    owner: dict[tuple, int] = {}
    for i, (cells, _, _) in enumerate(parts):
        for c in cells:
            owner[c] = i

    # --- 1 & 2 : support direct et appui ---
    supports: list[set[int]] = [set() for _ in model.bricks]
    support_frac: list[float] = []
    for i, b in enumerate(model.bricks):
        cells, vol, (sx, sz, h) = parts[i]
        footprint = {(cx, cz) for (cx, cy, cz) in cells if cy == b["y"]}
        if b["y"] == 0:
            support_frac.append(1.0)
            continue
        supported = set()
        for (cx, cz) in footprint:
            j = owner.get((cx, b["y"] - 1, cz))
            if j is not None and j != i:
                supported.add(j)
        support_frac.append(len(
            {(cx, cz) for (cx, cz) in footprint
             if owner.get((cx, b["y"] - 1, cz)) is not None}) / max(1, len(footprint)))
        supports[i] = supported

    # Appui : une brique tient si elle atteint le sol par une chaîne de
    # connexions — support vertical OU accolement latéral (les studs tiennent :
    # un plancher de 18 briques fixé aux quatre coins est solide).
    reachable: set[int] = {i for i, b in enumerate(model.bricks) if b["y"] == 0}
    stack = list(reachable)
    while stack:
        i = stack.pop()
        b = model.bricks[i]
        cells = parts[i][0]
        for (cx, cy, cz) in cells:
            for nb in ((cx + 1, cy, cz), (cx - 1, cy, cz), (cx, cy, cz + 1),
                       (cx, cy, cz - 1), (cx, cy + 1, cz), (cx, cy - 1, cz)):
                j = owner.get(nb)
                if j is not None and j not in reachable:
                    reachable.add(j)
                    stack.append(j)
    unsupported = [i for i in range(len(model.bricks)) if i not in reachable]

    # --- 3 : basculement par joint horizontal ---
    # poids = volume en voxels ; on compare le CoM de la partie supérieure à
    # la zone de contact du joint.
    total_vol = sum(v for _, v, _ in parts)
    joints = sorted({b["y"] for b in model.bricks if b["y"] > 0})
    tipping_joints = []
    for y in joints:
        # Seules les briques dont le poids descend verticalement participent au
        # basculement : une brique simplement accolée (support vertical nul) est
        # retenue par ses studs latéraux, pas par ce joint.
        above = [i for i, b in enumerate(model.bricks)
                 if b["y"] >= y and (b["y"] == 0 or support_frac[i] > 0)]
        if not above:
            continue
        wsum = sum(parts[i][1] for i in above)
        if wsum == 0:
            continue
        com_x = sum(parts[i][1] * (model.bricks[i]["x"] + parts[i][2][0] / 2.0)
                    for i in above) / wsum
        com_z = sum(parts[i][1] * (model.bricks[i]["z"] + parts[i][2][1] / 2.0)
                    for i in above) / wsum
        contact = set()
        for i in above:
            b = model.bricks[i]
            for (cx, cz) in {(cx, cz) for (cx, cy, cz) in parts[i][0]
                             if cy == b["y"]}:
                if owner.get((cx, y - 1, cz)) is not None:
                    contact.add((cx, cz))
        if not contact:
            continue
        xs = [c[0] for c in contact]
        zs = [c[1] for c in contact]
        # marge : le CoM doit tomber dans l'emprise du contact (tolérance 0.5 stud)
        inside = (min(xs) - 0.5 <= com_x <= max(xs) + 1.5
                  and min(zs) - 0.5 <= com_z <= max(zs) + 1.5)
        if not inside:
            tipping_joints.append({"y": y, "com": [round(com_x, 2), round(com_z, 2)],
                                   "contact_x": [min(xs), max(xs)],
                                   "contact_z": [min(zs), max(zs)]})

    # --- scores locaux ---
    # Le score reflète ce qui fait tomber un modèle : pas de chemin de charge
    # (éliminatoire) ou basculement d'un joint. Le support partiel n'est qu'une
    # fragilité : une dalle sur quatre piliers est stable, une brique tenue par
    # un seul stud est légitime en LEGO.
    tipping_above: set[int] = set()
    for joint in tipping_joints:
        for i, b in enumerate(model.bricks):
            if b["y"] >= joint["y"]:
                tipping_above.add(i)
    local: list[float] = []
    weak = []
    for i, b in enumerate(model.bricks):
        if i in unsupported:
            local.append(0.0)
            weak.append({"index": i, "part": b["part_id"],
                         "pos": [b["x"], b["y"], b["z"]], "reason": "sans_appui"})
            continue
        score = 1.0
        if support_frac[i] == 0.0 and b["y"] > 0:
            # tenue uniquement par les studs latéraux : fragile
            score *= 0.8
            weak.append({"index": i, "part": b["part_id"],
                         "pos": [b["x"], b["y"], b["z"]],
                         "reason": "aucun support vertical"})
        elif support_frac[i] < 0.25:
            score *= 0.85
            weak.append({"index": i, "part": b["part_id"],
                         "pos": [b["x"], b["y"], b["z"]],
                         "reason": f"support {support_frac[i]:.0%}"})
        if i in tipping_above:
            score *= 0.5
        local.append(score)

    min_stability = min(local) if local else 0.0
    mean_stability = sum(local) / len(local) if local else 0.0

    return {
        "min_stability": round(min_stability, 3),
        "mean_stability": round(mean_stability, 3),
        "unsupported": unsupported,
        "weak": weak[:12],
        "overhang_cells": sum(1 for f in support_frac if f < 1.0),
        "tipping_joints": tipping_joints[:6],
    }


def summary_line(report: dict) -> str:
    """Résumé court pour les messages d'erreur et les logs."""
    bits = [f"min {report['min_stability']:.2f}", f"moy {report['mean_stability']:.2f}"]
    if report["unsupported"]:
        bits.append(f"{len(report['unsupported'])} sans appui")
    if report["tipping_joints"]:
        bits.append(f"{len(report['tipping_joints'])} joint(s) instable(s)")
    if report["overhang_cells"]:
        bits.append(f"{report['overhang_cells']} porte-à-faux")
    return " | ".join(bits)
