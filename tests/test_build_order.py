#!/usr/bin/env python3
"""Tests de l'ordre de montage (tools/build_order.py).

Lancer : python3 -m pytest tests/ -v
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from ldraw_model import LDrawModel  # noqa: E402
import arch  # noqa: E402
import build_order as bo  # noqa: E402


def _house():
    """Volume de test compilé par le pipeline réel (briques posées sur studs)."""
    from voxel import VoxelGrid
    from brickify import brickify, BrickifyOptions
    model, _ = brickify(VoxelGrid().box(0, 0, 0, 12, 9, 8, "19"), "h",
                        BrickifyOptions(add_steps=False))
    return model


def test_sequence_couvre_toutes_les_briques():
    m = _house()
    steps = bo.plan(m)
    assert sum(len(s) for s in steps) == len(m.bricks)


def test_sequence_est_posable():
    """Chaque brique doit avoir un appui déjà posé quand vient son tour."""
    m = _house()
    steps = bo.plan(m)
    assert bo.validate(m, steps) == []


def test_ordre_va_du_bas_vers_le_haut():
    """Le niveau d'un step ne doit jamais redescendre sous le précédent."""
    m = _house()
    steps = bo.plan(m)
    levels = [min(m.bricks[i]["y"] for i in s) for s in steps]
    for a, b in zip(levels, levels[1:]):
        assert b >= a, "l'ordre redescend : illisible pour une notice"


def test_les_briques_du_haut_viennent_en_dernier():
    m = _house()
    steps = bo.plan(m)
    levels = [max(m.bricks[i]["y"] for i in s) for s in steps]
    assert levels == sorted(levels)


def test_steps_de_taille_raisonnable():
    m = _house()
    steps = bo.plan(m, max_per_step=10)
    assert all(len(s) <= 10 for s in steps)


def test_apply_reordonne_et_ecrit_les_steps():
    m = _house()
    n = len(m.bricks)
    steps = bo.plan(m)
    bo.apply(m, steps)
    assert len(m.bricks) == n
    assert len(m.steps) == len(steps) - 1
    # le modèle reste valide après réordonnancement
    assert m.connectivity()["islands"] == 1


def test_modele_vide():
    m = LDrawModel("vide")
    assert bo.plan(m) == []


def test_brique_isolee_en_l_air_reste_dans_la_sequence():
    """Une brique sans appui doit tout de même être planifiée (elle sera
    signalée par l'analyse de stabilité, pas par l'ordre de montage)."""
    m = LDrawModel("flottant")
    m.place("3001", 0, 0, 0, "4")
    m.place("3001", 20, 20, 9, "1")   # isolée
    steps = bo.plan(m)
    assert sum(len(s) for s in steps) == 2
