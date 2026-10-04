#!/usr/bin/env python3
"""Tests du solver CP-SAT (tools/solver.py) : invariants géométriques et
boucle de feedback blueprint invalide.

Lancer : python3 -m pytest tests/ -v
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import lego_ir as ir          # noqa: E402
import solver as sv           # noqa: E402
import build_order as bo      # noqa: E402
from ldraw_model import LDrawModel  # noqa: E402

TIME = 30.0


def _solve(components, terrain=(20, 20, 12)):
    bp, errs = ir.from_dict({
        "name": "test",
        "terrain": {"width": terrain[0], "depth": terrain[1],
                    "max_height": terrain[2]},
        "components": components,
    })
    assert errs == []
    return sv.solve_blueprint(bp, time_limit=TIME)


def test_mur_sans_ouverture():
    model, rep = _solve([
        {"type": "wall", "id": "w", "x": 2, "z": 2, "width": 6, "depth": 1,
         "height": 3, "color": "1"}])
    assert rep["status"] == "OK", rep["issues"]
    assert rep["pieces"] <= 12          # l'objectif minimise le nombre
    assert rep["min_stability"] >= 0.8
    assert rep["islands"] == 1
    assert rep["build_steps"] >= 1
    # zéro collision : la pose dans LDrawModel aurait levé
    assert all(b.get("y", 0) >= 0 for b in model.bricks)


def test_mur_avec_porte():
    model, rep = _solve([
        {"type": "wall", "id": "w", "x": 1, "z": 1, "width": 8, "depth": 1,
         "height": 4, "color": "1",
         "openings": [{"kind": "gate", "offset": 2, "width": 3,
                       "top": 6}]}])
    assert rep["status"] == "OK", rep["issues"]
    assert rep["min_stability"] >= 0.8
    # au-dessus de la porte (niveaux >= 6) : des pièces doivent exister
    above = [b for b in model.bricks if b["y"] >= 6]
    assert above


def test_tour_creuse():
    model, rep = _solve([
        {"type": "tower", "id": "t", "x": 0, "z": 0, "size": 6, "height": 4,
         "color": "72", "roof": "conical"}])
    assert rep["status"] == "OK", rep["issues"]
    assert rep["min_stability"] >= 0.8
    assert rep["islands"] == 1
    # le toit pyramidal a bien été posé (pièces de pente/cône)
    kinds = set(model.parts_summary())
    assert kinds & {"3045", "3039", "98100"}


def test_region_insatisfiable():
    # mur entièrement percé : rien ne peut reposer au-dessus de la porte
    bp, errs = ir.from_dict({
        "terrain": {"width": 12, "depth": 8, "max_height": 6},
        "components": [
            {"type": "wall", "id": "w", "x": 1, "z": 1, "width": 4,
             "depth": 1, "height": 4,
             "openings": [{"kind": "gate", "offset": 0, "width": 4,
                           "top": 6}]}]})
    assert errs == []
    model, rep = sv.solve_blueprint(bp, time_limit=TIME)
    assert model is None or rep["status"] == "ISSUES"
    assert rep["issues"]
    assert any("w" in i for i in rep["issues"])


def test_blueprint_invalide_feedback():
    bp, errs = ir.from_dict({
        "terrain": {"width": 10, "depth": 10, "max_height": 6},
        "components": [
            {"type": "slab", "id": "a", "x": 0, "z": 0, "width": 6,
             "depth": 6},
            {"type": "slab", "id": "b", "x": 3, "z": 3, "width": 6,
             "depth": 6}]})
    # from_dict collecte déjà les erreurs de validation
    assert errs
    model, rep = sv.solve_blueprint(bp)
    assert model is None
    assert rep["status"] == "INVALID_BLUEPRINT"


def test_end_to_end_steps_valides():
    """Blueprint en dur -> .ldr -> steps validés par build_order."""
    model, rep = _solve([
        {"type": "box", "id": "maison", "x": 1, "z": 1, "width": 8,
         "depth": 6, "height": 3, "color": "14", "floor": True,
         "roof": "pitched",
         "openings": [{"kind": "gate", "offset": 3, "width": 2,
                       "top": 6}]}])
    assert rep["status"] == "OK", rep["issues"]
    steps = bo.plan(model)
    assert bo.validate(model, steps) == []
    assert model.connectivity()["islands"] == 1
    assert rep["score"]["buildability"] == 1.0
    assert rep["score"]["stability"] >= 0.8
