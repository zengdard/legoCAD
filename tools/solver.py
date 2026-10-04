#!/usr/bin/env python3
"""Solver combinatoire (OR-Tools CP-SAT) : le LLM a produit un blueprint
(tools/lego_ir.py), le solver choisit les briques concrètes.

Modèle exact-cover par région :
  - une variable booléenne par placement candidat d'une pièce (part_id,
    orientation 0/90°, ancre (x, z), niveau de départ y en plaques) ;
  - contrainte de couverture : chaque cellule (x, z) libre à chaque niveau
    est couverte par EXACTEMENT une pièce (=> zéro collision par
    construction) ;
  - contrainte de support : une pièce posée au-dessus du sol doit toucher
    la pièce du dessous sur au moins une cellule, OU être accolée
    latéralement à une pièce de même tranche verticale (linteau au-dessus
    d'une porte) — c'est la sémantique de tools/stability.py ;
  - objectif : min λ1·N_pièces + λ2·N_types (§5 du cahier des charges).

solve_blueprint() enchaîne : validation IR -> solve par région -> pose dans
LDrawModel (collision voxel, warnings) -> toits (arch.py) -> stabilité ->
ordre de montage. Le rapport est le feedback déterministe renvoyé au LLM.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ortools.sat.python import cp_model

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lego_ir as ir                       # noqa: E402
import stability as st                     # noqa: E402
import build_order as bo                   # noqa: E402
from ldraw_model import CollisionError, LDrawModel, UnknownPartError  # noqa: E402


# ---------------------------------------------------------------------------
# Génération des placements candidats d'une région
# ---------------------------------------------------------------------------

def _orientations(part_sx: int, part_sz: int):
    yield (part_sx, part_sz), 0
    if part_sx != part_sz:
        yield (part_sz, part_sx), 90


def _candidates(region: ir.Region, part_dims: dict):
    """Liste de placements candidats : dicts {part_id, x, z, y, h, rot,
    cells, key}. part_dims : part_id -> (studs_x, studs_z)."""
    cands = []
    for (w, h), ids in region.allowed.items():
        for pid in ids:
            sx, sz = part_dims.get(pid, (w, 1))
            for (ox, oz), rot in _orientations(sx, sz):
                cells_x = [c[0] for c in region.cells]
                cells_z = [c[1] for c in region.cells]
                x0, x1 = min(cells_x), max(cells_x)
                z0, z1 = min(cells_z), max(cells_z)
                for ax in range(x0, x1 - ox + 2):
                    for az in range(z0, z1 - oz + 2):
                        cells = tuple((ax + i, az + j)
                                      for i in range(ox)
                                      for j in range(oz))
                        if not set(cells) <= region.cells:
                            continue
                        for y in range(region.y_base,
                                       region.y_top - h + 1):
                            if any(set(range(y, y + h)) & region.holes.get(c, set())
                                   for c in cells):
                                continue
                            cands.append({
                                "part_id": pid, "x": ax, "z": az, "y": y,
                                "h": h, "rot": rot, "cells": cells,
                                "levels": set(range(y, y + h)),
                            })
    return cands


def solve_region(region: ir.Region, part_dims: dict,
                 time_limit: float = 30.0) -> tuple[list, dict]:
    """Remplit une région -> (briques, info). info contient 'status' et,
    en cas d'échec, la raison (feedback pour le LLM)."""
    cands = _candidates(region, part_dims)
    # index : (cellule, niveau) -> placements qui la couvrent
    cover: dict = {}
    for i, c in enumerate(cands):
        for cell in c["cells"]:
            for lev in c["levels"]:
                cover.setdefault((cell, lev), []).append(i)

    # cellules exigées : toute cellule de la région à tout niveau non troué
    required = []
    for (x, z) in sorted(region.cells):
        for y in range(region.y_base, region.y_top):
            if y in region.holes.get((x, z), set()):
                continue
            if not cover.get(((x, z), y)):
                return [], {"status": "INFEASIBLE",
                            "reason": f"aucune pièce autorisée ne peut "
                                      f"couvrir ({x},{z}) au niveau {y}"}
            required.append(((x, z), y))

    m = cp_model.CpModel()
    p = [m.NewBoolVar(f"p{i}") for i in range(len(cands))]

    for key in required:
        m.AddExactlyOne(p[i] for i in cover[key])

    # accolement latéral : seulement vers une brique ancrée (au sol ou avec
    # un appui vertical statiquement possible) — sinon deux briques peuvent
    # se déclarer mutuellement « accolées » sans aucune fondation.
    def anchored(c):
        return (c["y"] <= region.y_base or
                any(cover.get((cell, c["y"] - 1))
                    for cell in c["cells"]))

    # support : contact vertical sur >= 1 cellule, OU accolade latérale
    for i, c in enumerate(cands):
        if c["y"] <= region.y_base:
            continue
        below = []
        for cell in c["cells"]:
            qs = cover.get((cell, c["y"] - 1), [])
            if not qs:
                continue
            b = m.NewBoolVar(f"below{i}_{cell}")
            m.AddMaxEquality(b, [p[q] for q in qs])
            below.append(b)
        if not below:
            # aucune cellule ne peut être posée sur du dessous : il faut
            # absolument un accolement latéral (linteau)
            glue = _glue_vars(m, c, cands, p, i, anchored)
            if glue:
                m.Add(sum(glue) >= 1).OnlyEnforceIf(p[i])
            else:
                m.Add(p[i] == 0)
            continue
        glue = _glue_vars(m, c, cands, p, i, anchored)
        terms = below + glue
        m.Add(sum(terms) >= 1).OnlyEnforceIf(p[i])

    # objectif : min pièces + petit malus par type de pièce utilisé
    types = sorted({c["part_id"] for c in cands})
    used = {t: m.NewBoolVar(f"used_{t}") for t in types}
    for i, c in enumerate(cands):
        m.AddImplication(p[i], used[c["part_id"]])
    m.Minimize(sum(p) + 0.2 * sum(used.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [], {"status": solver.StatusName(status),
                    "reason": f"région {region.rid} : pas de solution "
                              f"({solver.StatusName(status)}) — réduis la "
                              f"hauteur, élargis la région ou vérifie les "
                              f"ouvertures"}
    bricks = []
    for i, c in enumerate(cands):
        if solver.Value(p[i]):
            bricks.append({"part_id": c["part_id"], "x": c["x"],
                           "z": c["z"], "y": c["y"],
                           "color": region.colors.get(c["y"], "7"),
                           "rot": c["rot"]})
    return bricks, {"status": "OK", "pieces": len(bricks)}


def _glue_vars(m, c, cands, p, i, anchored=None):
    """Vars OR : placements accolés latéralement à c sur sa tranche verticale."""
    cellset = set(c["cells"])
    neighbors = set()
    for (x, z) in cellset:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, z + dz)
            if n not in cellset:
                neighbors.add(n)
    glue = []
    for j, q in enumerate(cands):
        if j == i:
            continue
        if anchored is not None and not anchored(q):
            continue
        if not (q["y"] < c["y"] + c["h"] and c["y"] < q["y"] + q["h"]):
            continue
        if set(q["cells"]) & neighbors:
            glue.append(p[j])
    return glue


# ---------------------------------------------------------------------------
# Blueprint -> modèle complet
# ---------------------------------------------------------------------------

def _region_key(region: ir.Region) -> tuple:
    """Clé de forme d'une région, indépendante de sa position : deux régions
    de même forme (cellules/creux relatifs, hauteur, pièces, couleurs)
    partagent la même solution du solver."""
    minx = min(x for x, _ in region.cells)
    minz = min(z for _, z in region.cells)
    rel_cells = frozenset((x - minx, z - minz) for x, z in region.cells)
    rel_holes = frozenset((x - minx, z - minz, tuple(sorted(levels)))
                          for (x, z), levels in region.holes.items())
    allowed = tuple(sorted((w, h, tuple(sorted(ids)))
                           for (w, h), ids in region.allowed.items()))
    colors = tuple(sorted(region.colors.items()))
    return (region.kind, region.y_base, region.y_top,
            rel_cells, rel_holes, allowed, colors)


def _relativize(bricks: list, region: ir.Region) -> list:
    minx = min(x for x, _ in region.cells)
    minz = min(z for _, z in region.cells)
    return [{**b, "x": b["x"] - minx, "z": b["z"] - minz} for b in bricks]


def _translate(rel_bricks: list, region: ir.Region) -> list:
    minx = min(x for x, _ in region.cells)
    minz = min(z for _, z in region.cells)
    return [{**b, "x": b["x"] + minx, "z": b["z"] + minz}
            for b in rel_bricks]


def _part_dims(model: LDrawModel, allowed: dict) -> dict:
    dims = {}
    for ids in allowed.values():
        for pid in ids:
            if pid not in dims:
                try:
                    part = model.part(pid)
                    dims[pid] = (max(1, round(part["studs_x"])),
                                 max(1, round(part["studs_z"])))
                except UnknownPartError:
                    dims[pid] = None
    return {k: v for k, v in dims.items() if v}


def solve_blueprint(bp: ir.Blueprint, time_limit: float = 30.0,
                    apply_build_order: bool = True) -> tuple[LDrawModel, dict]:
    """Blueprint validé -> (LDrawModel, rapport). Le rapport contient
    status=OK ou la liste des problèmes (feedback déterministe au LLM)."""
    errors = ir.validate(bp)
    if errors:
        return None, {"status": "INVALID_BLUEPRINT", "issues": errors}
    model = LDrawModel(bp.name)
    issues = []
    part_dims_cache: dict = {}
    solved_cache: dict = {}   # clé de forme de région -> briques relatives
    n_solved = 0
    for region in ir.regions(bp):
        key = _region_key(region)
        if key in solved_cache:
            # MVP 4.1 : modules identiques (tours jumelles, murailles...) —
            # la solution est résolue une fois puis translatée
            bricks = _translate(solved_cache[key], region)
        else:
            if region.rid not in part_dims_cache:
                part_dims_cache[region.rid] = _part_dims(model, region.allowed)
            bricks, info = solve_region(region, part_dims_cache[region.rid],
                                        time_limit)
            if info["status"] != "OK":
                issues.append(f"{region.rid}: {info['reason']}")
                continue
            solved_cache[key] = _relativize(bricks, region)
            n_solved += 1
        for b in bricks:
            try:
                model.place(**b)
            except (CollisionError, UnknownPartError) as e:
                issues.append(f"{region.rid}: pose {b['part_id']} "
                              f"@({b['x']},{b['y']},{b['z']}) : {e}")
    # toits décoratifs (hors zone solver : pièces de pente/cône)
    import arch
    for comp in bp.components:
        if comp.type == "slab" or comp.roof == "none":
            continue
        try:
            if comp.roof == "conical":
                arch.pyramid_roof(model, comp.x, comp.z, comp.width,
                                  comp.height_plates(), comp.color)
            elif comp.roof == "pitched":
                arch.pitched_roof(model, comp.x, comp.z, comp.width,
                                  comp.depth, comp.height_plates(),
                                  comp.color)
        except (CollisionError, UnknownPartError, ValueError) as e:
            issues.append(f"{comp.cid or comp.type}: toit {comp.roof}: {e}")

    conn = model.connectivity()
    stab = model.stability()
    steps = bo.plan(model)
    build_errors = bo.validate(model, steps)
    if build_errors:
        issues.extend(build_errors)
    if apply_build_order:
        bo.apply(model, steps)

    n_pieces = len(model.bricks)
    n_types = len(model.parts_summary())
    report = {
        "status": "OK" if not issues else "ISSUES",
        "issues": issues,
        "pieces": n_pieces,
        "types": n_types,
        "islands": conn.get("islands", 0),
        "min_stability": stab.get("min_stability", 0.0),
        "unsupported": stab.get("unsupported", []),
        "build_steps": len(model.steps),
        "objectives": bp.objectives,
        "score": _score(bp, model, stab, conn, n_pieces, n_types,
                        len(build_errors) == 0),
    }
    return model, report


def _score(bp, model, stab, conn, n_pieces, n_types, buildable) -> dict:
    """Score multi-critères (§11) : sémantique = couverture des régions du
    blueprint (chaque composant présent) ; le reste vient des validateurs."""
    obj = bp.objectives
    components = len(bp.components)
    return {
        "buildability": 1.0 if buildable else 0.0,
        "stability": stab.get("min_stability", 0.0),
        "connectivity": 1.0 if conn.get("islands", 0) <= 1 else 0.0,
        "piece_efficiency": min(1.0, obj.get("max_pieces", 400) /
                                max(1, n_pieces)),
        "variety": min(1.0, n_types / max(1, obj.get("max_types", 12)))
                   if n_types else 0.0,
        "components_built": components,
    }


def summary_line(report: dict) -> str:
    if report["status"] == "INVALID_BLUEPRINT":
        return ("Blueprint invalide :\n" +
                "\n".join(" - " + e for e in report["issues"]))
    line = (f"{report['status']} : {report['pieces']} pièces, "
            f"{report['types']} types, stabilité "
            f"{report['min_stability']:.2f}, "
            f"{report['islands']} amas, {report['build_steps']} steps")
    if report["issues"]:
        line += "\nProblèmes :\n" + "\n".join(" - " + i
                                              for i in report["issues"])
    return line


if __name__ == "__main__":
    demo = {
        "name": "mur_test",
        "terrain": {"width": 12, "depth": 8, "max_height": 6},
        "components": [
            {"type": "wall", "id": "w", "x": 1, "z": 1, "width": 8,
             "depth": 1, "height": 4, "color": "1",
             "openings": [{"kind": "gate", "offset": 2, "width": 3,
                           "top": 6}]},
        ],
    }
    bp, errs = ir.from_dict(demo)
    print("erreurs IR:", errs)
    if not errs:
        model, report = solve_blueprint(bp, time_limit=20)
        print(summary_line(report))
        if model:
            out = Path(__file__).resolve().parent.parent / "models" / "_solver_test.ldr"
            model.save(out)
            print("sauvé :", out)
