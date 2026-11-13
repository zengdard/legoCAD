#!/usr/bin/env python3
"""Analyse de stabilité physique d'un modèle LDraw — version « vrais LEGO ».

Le modèle de connexion est celui du jeu réel : une pièce n'est tenue que par
les **studs** de la pièce située juste en dessous (voir tools/studs.py).
Deux briques côte à côte ne sont pas attachées, même si elles se touchent.

Trois contrôles, du plus grave au plus fin :
  1. Chemin de charge — chaque pièce doit être reliée au sol (y=0) par une
     chaîne de connexions étud → tube. C'est éliminatoire : une pièce sans
     chemin tombe dès qu'on soulève le modèle.
  2. Support direct — fraction de l'empreinte réellement posée sur une pièce
     du dessous. Un porte-à-faux est légal, mais il est signalé.
  3. Basculement — à chaque joint horizontal, le centre de gravité de la
     charge descendante doit tomber au-dessus de la zone de contact
     (critère d'équilibre des moments, version discrète).

`min_stability` reste le maillon faible (comme dans BrickGPT) : 1.0 = tout
est tenu, 0.0 = une pièce n'est attachée à rien.
"""
from __future__ import annotations

import studs


def analyze(model) -> dict:
    """Retourne le rapport de stabilité du modèle."""
    if not model.bricks:
        return {"min_stability": 0.0, "mean_stability": 0.0, "unsupported": [],
                "weak": [], "overhang_cells": 0, "tipping_joints": [],
                "single_stud": [], "islands": 0, "connections": 0,
                "resting": []}

    rep = studs.report(model)
    geoms = rep["geoms"]
    sup = rep["support"]
    unsupported = rep["unsupported"]

    # --- 3 : basculement par joint horizontal -------------------------- #
    # Pour chaque niveau où une pièce commence, on considère uniquement la
    # charge qui repose *via ce joint* : les pièces posées à ce niveau, puis
    # tout ce qui est empilé dessus. Comparer le CoM de TOUT le modèle au
    # contact d'un petit joint produirait des faux positifs (un escalier de
    # toit n'est pas en équilibre sur chaque marche).
    volume = [len(g["footprint"]) * g["height"] for g in geoms]
    up: dict[int, list[int]] = {}
    for e in sup["edges"]:
        up.setdefault(e["below"], []).append(e["above"])

    joints = sorted({g["base"] for g in geoms if g["base"] > 0})
    tipping_joints = []
    for y in joints:
        seeds = [i for i, g in enumerate(geoms)
                 if g["base"] == y and sup["contact"][i]]
        if not seeds:
            continue
        load = set(seeds)
        stack = list(seeds)
        while stack:
            i = stack.pop()
            for j in up.get(i, []):
                if j not in load and geoms[j]["base"] >= y:
                    load.add(j)
                    stack.append(j)
        wsum = sum(volume[i] for i in load)
        if not wsum:
            continue
        com_x = com_z = 0.0
        for i in load:
            sx, sz = model._footprint(geoms[i]["part"],
                                      model.bricks[i]["rot"])
            com_x += volume[i] * (model.bricks[i]["x"] + sx / 2.0)
            com_z += volume[i] * (model.bricks[i]["z"] + sz / 2.0)
        com_x /= wsum
        com_z /= wsum
        contact = set()
        for i in seeds:
            contact |= sup["contact"][i]
        if not contact:
            continue
        xs = [c[0] for c in contact]
        zs = [c[1] for c in contact]
        # tolérance d'un demi-stud : les studs LEGO encaissent un léger
        # porte-à-faux, un vrai basculement est bien plus franc
        inside = (min(xs) - 0.5 <= com_x <= max(xs) + 1.5
                  and min(zs) - 0.5 <= com_z <= max(zs) + 1.5)
        if not inside:
            tipping_joints.append({"y": y,
                                   "com": [round(com_x, 2), round(com_z, 2)],
                                   "contact_x": [min(xs), max(xs)],
                                   "contact_z": [min(zs), max(zs)],
                                   "load": len(load)})

    tipping_above: set[int] = set()
    for joint in tipping_joints:
        for i, g in enumerate(geoms):
            if g["base"] >= joint["y"]:
                tipping_above.add(i)

    # --- scores locaux ------------------------------------------------ #
    local: list[float] = []
    weak = []
    for i, g in enumerate(geoms):
        b = model.bricks[i]
        if i in unsupported:
            local.append(0.0)
            reason = ("sans_appui" if not sup["below"].get(i)
                      else "tenue_par_du_lisse")
            weak.append({"index": i, "part": b["part_id"],
                         "pos": [b["x"], b["y"], b["z"]], "reason": reason})
            continue
        score = 1.0
        if g["base"] > 0 and sup["studs"].get(i, 0) == 1:
            # attachée par un seul tenon : légal, mais fragile
            score *= 0.9
            weak.append({"index": i, "part": b["part_id"],
                         "pos": [b["x"], b["y"], b["z"]],
                         "reason": "1 seul stud"})
        elif g["base"] > 0 and sup["fraction"][i] < 0.25:
            score *= 0.85
            weak.append({"index": i, "part": b["part_id"],
                         "pos": [b["x"], b["y"], b["z"]],
                         "reason": f"support {sup['fraction'][i]:.0%}"})
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
        "overhang_cells": sum(1 for i, g in enumerate(geoms)
                              if g["base"] > 0 and sup["fraction"][i] < 1.0),
        "tipping_joints": tipping_joints[:6],
        "single_stud": rep["single_stud"],
        "islands": rep["islands"],
        "connections": rep["connections"],
        "resting": rep["resting"],
        "families": rep.get("families", {}),
    }


def summary_line(report: dict) -> str:
    """Résumé court pour les messages d'erreur et les logs."""
    bits = [f"min {report['min_stability']:.2f}",
            f"moy {report['mean_stability']:.2f}"]
    if report.get("islands", 0) > 1:
        bits.append(f"{report['islands']} amas")
    if report.get("unsupported"):
        bits.append(f"{len(report['unsupported'])} non attachées")
    if report.get("tipping_joints"):
        bits.append(f"{len(report['tipping_joints'])} joint(s) instable(s)")
    if report.get("overhang_cells"):
        bits.append(f"{report['overhang_cells']} porte-à-faux")
    if report.get("single_stud"):
        bits.append(f"{len(report['single_stud'])} tenues par 1 stud")
    return " | ".join(bits)
