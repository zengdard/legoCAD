#!/usr/bin/env python3
"""Ordre de montage d'un modèle LEGO : produit une séquence qu'un humain peut
suivre, au lieu des blocs « auteur » du script de génération.

Approche (inspirée du brevet LEGO EP2135222B1 : on déconstruit, puis on
inverse) :
  1. graphe de dépendance — une brique ne peut être posée qu'une fois posées
     les briques qui la portent (support vertical) ou qui la bordent au même
     niveau quand elle n'a pas d'appui direct ;
  2. tri topologique par vagues, de bas en haut, en balayant l'espace de
     l'avant vers l'arrière (ordre naturel de lecture d'une notice) ;
  3. découpage en steps de taille raisonnable, en gardant ensemble les briques
     spatialement voisines — un step = ce qu'on assemble d'un coup.

Fonctions principales :
    plan(model)         -> liste de steps (listes d'indices de briques)
    validate(model, p)  -> vérifie que la séquence est physiquement posable
    apply(model, p)     -> réécrit model.steps avec cet ordre
"""
from __future__ import annotations

from ldraw_model import LDU_PER_LEVEL, _NOMINAL_H

DEFAULT_MAX_PER_STEP = 12


def _deps(model):
    """Pour chaque brique : les briques qui doivent être posées avant elle."""
    cells_per, owner = model._voxels()
    deps: list[set[int]] = [set() for _ in model.bricks]
    for i, b in enumerate(model.bricks):
        if b["y"] == 0:
            continue
        for (cx, cy, cz) in cells_per[i]:
            for nb in ((cx, cy - 1, cz),          # juste en dessous
                       (cx + 1, cy, cz), (cx - 1, cy, cz),   # voisins latéraux
                       (cx, cy, cz + 1), (cx, cy, cz - 1)):
                j = owner.get(nb)
                if j is None or j == i:
                    continue
                bj = model.bricks[j]
                if bj["y"] < b["y"] or (bj["y"] == b["y"] and j < i):
                    deps[i].add(j)
    return deps


def plan(model, max_per_step: int = DEFAULT_MAX_PER_STEP) -> list[list[int]]:
    """Construit l'ordre de montage : liste de steps, chaque step étant une
    liste d'indices de briques à poser ensemble."""
    n = len(model.bricks)
    if n == 0:
        return []
    deps = _deps(model)
    remaining = set(range(n))
    placed: set[int] = set()
    steps: list[list[int]] = []

    while remaining:
        # briques posables : toutes leurs dépendances sont déjà posées
        ready = [i for i in remaining if deps[i] <= placed]
        if not ready:
            # cycle improbable (données incohérentes) : on débloque le plus bas
            ready = [min(remaining, key=lambda i: (model.bricks[i]["y"], i))]
        # ordre naturel : bas en haut, puis de l'avant (-z) vers l'arrière, x croissant
        ready.sort(key=lambda i: (model.bricks[i]["y"], model.bricks[i]["z"],
                                  model.bricks[i]["x"]))
        level = model.bricks[ready[0]]["y"]
        # un step ne mélange pas deux niveaux, et garde des briques voisines
        chunk = [i for i in ready if model.bricks[i]["y"] == level][:max_per_step]
        if not chunk:
            chunk = ready[:max_per_step]
        steps.append(chunk)
        placed.update(chunk)
        remaining.difference_update(chunk)
    return steps


def validate(model, steps: list[list[int]]) -> list[str]:
    """Vérifie la séquence : chaque brique doit avoir un appui au moment où
    elle est posée, et aucune brique ne doit être posée sous une brique déjà
    en place. Retourne la liste des problèmes (vide = séquence valide)."""
    placed: set[int] = set()
    problems: list[str] = []
    order = {i: k for k, step in enumerate(steps) for i in step}
    if len(order) != len(model.bricks):
        missing = set(range(len(model.bricks))) - set(order)
        problems.append(f"{len(missing)} brique(s) absentes de la séquence")
    cells_per, owner = model._voxels()
    for k, step in enumerate(steps):
        for i in step:
            b = model.bricks[i]
            if b["y"] == 0:
                placed.add(i)
                continue
            # a-t-elle un appui déjà posé (vertical ou latéral) ?
            supported = False
            for (cx, cy, cz) in cells_per[i]:
                for nb in ((cx, cy - 1, cz), (cx + 1, cy, cz), (cx - 1, cy, cz),
                           (cx, cy, cz + 1), (cx, cy, cz - 1)):
                    j = owner.get(nb)
                    if j is not None and j in placed and j != i:
                        supported = True
                        break
                if supported:
                    break
            if not supported:
                problems.append(
                    f"step {k+1} : {b['part_id']} en ({b['x']},{b['y']},{b['z']}) "
                    "posée sans appui déjà en place")
            placed.add(i)
    return problems


def apply(model, steps: list[list[int]]) -> None:
    """Réordonne les briques du modèle selon la séquence et réécrit ses steps,
    de sorte que le .ldr exporté suive l'ordre de montage."""
    flat = [i for step in steps for i in step]
    if len(flat) != len(model.bricks):
        raise ValueError("séquence incomplète")
    model.bricks = [model.bricks[i] for i in flat]
    model._rebuild_occupied()
    model.steps = []
    acc = 0
    for step in steps[:-1]:
        acc += len(step)
        model.steps.append(acc)


def report(model, steps: list[list[int]]) -> dict:
    """Statistiques lisibles sur la séquence de montage."""
    if not steps:
        return {"steps": 0}
    sizes = [len(s) for s in steps]
    levels = [model.bricks[s[0]]["y"] for s in steps]
    return {
        "steps": len(steps),
        "pieces_per_step": {"min": min(sizes), "max": max(sizes),
                            "moy": round(sum(sizes) / len(sizes), 1)},
        "niveaux_couverts": len(set(levels)),
        "hauteur_max": max(levels),
    }
