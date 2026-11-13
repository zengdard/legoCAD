#!/usr/bin/env python3
"""Tests de l'analyse de stabilité (tools/stability.py).

Lancer : python3 -m pytest tests/ -v
"""
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from ldraw_model import CollisionError, LDrawModel  # noqa: E402
import stability as st  # noqa: E402


def _m(name="t"):
    return LDrawModel(name)


# --- appui : ce qui tient debout ------------------------------------- #

def test_console_empilee_est_stable():
    m = _m()
    for i in range(4):
        m.place("3001", 0, 0, i * 3, "4")
    r = st.analyze(m)
    assert r["min_stability"] == 1.0
    assert not r["unsupported"]


def test_brique_flottante_est_instable():
    m = _m()
    m.place("3001", 0, 0, 0, "4")
    m.place("3001", 0, 0, 12, "1")   # 4 niveaux au-dessus du vide
    r = st.analyze(m)
    assert r["min_stability"] == 0.0
    assert len(r["unsupported"]) == 1


def test_pyramide_est_stable():
    m = _m()
    m.slab(0, 0, 4, 4, 0, "4")
    m.slab(1, 1, 2, 2, 3, "14")
    r = st.analyze(m)
    assert r["min_stability"] == 1.0


def test_plancher_sur_quatre_piliers_n_est_pas_constructible():
    """Physique LEGO : des plaques côte à côte au même niveau ne sont PAS
    attachées. Seuls les quatre coins posés sur les piliers tiennent ; tout
    le reste du plancher tombe."""
    m = _m()
    for x in (0, 11):
        for z in (0, 11):
            m.column(x, z, 1, "71")
    m.slab(0, 0, 12, 12, 3, "4")
    r = st.analyze(m)
    assert r["unsupported"], "le centre du plancher n'est tenu par rien"
    assert r["min_stability"] == 0.0


# --- basculement ------------------------------------------------------ #

def test_dalle_sur_un_seul_pilier_bascule():
    m = _m()
    m.column(4, 4, 1, "71")
    m.slab(0, 0, 12, 12, 3, "4")
    r = st.analyze(m)
    assert r["tipping_joints"], "le centre de gravité sort de la zone d'appui"
    assert r["min_stability"] <= 0.5


def test_porte_a_faux_faible_est_signale():
    """Brique 2x4 posée sur les 2 studs de son extrémité : le centre de
    gravité sort de la zone d'appui, la brique bascule."""
    m = _m()
    m.place("3001", 0, 0, 0, "4")
    m.place("3001", 3, 0, 3, "1")
    r = st.analyze(m)
    assert r["tipping_joints"], "basculement attendu"
    assert r["min_stability"] <= 0.5
    assert r["overhang_cells"] == 1


def test_porte_a_faux_modere_reste_accepte():
    """2 studs sur 8 (25 %) et centre de gravité encore au-dessus de l'appui :
    c'est une construction LEGO normale, aucune pénalité."""
    m = _m()
    m.place("3001", 0, 0, 0, "4")
    m.place("3001", 2, 0, 3, "1")
    r = st.analyze(m)
    assert r["min_stability"] == 1.0
    assert not r["tipping_joints"]
    assert r["overhang_cells"] == 1  # signalé comme information


def test_accolement_lateral_ne_tient_pas():
    """Une brique collée latéralement à une tour, sans rien dessous, n'est
    attachée par aucun stud : elle tombe."""
    m = _m()
    m.column(0, 0, 3, "71")
    m.place("3001", 1, 0, 3, "4")   # accolée à la tour au niveau 3
    r = st.analyze(m)
    assert r["unsupported"] == [3]
    assert r["min_stability"] == 0.0


def test_volume_compile_est_stable():
    """Le compilateur volume → briques produit un modèle d'un seul bloc, dont
    chaque pièce est tenue par des studs."""
    from voxel import VoxelGrid
    from brickify import brickify
    m, rep = brickify(VoxelGrid().box(0, 0, 0, 12, 6, 8, "4"), "bloc")
    r = st.analyze(m)
    assert rep["coverage"] == 1.0
    assert not r["unsupported"]
    assert r["islands"] == 1


# --- intégration avec le générateur ----------------------------------- #

def test_mur_sur_dalle_est_stable():
    m = _m()
    m.slab(0, 0, 12, 8, 0, "71")
    m.slab(0, 0, 12, 1, 3, "19", layers=3)
    r = st.analyze(m)
    assert r["min_stability"] == 1.0


def test_modele_vide_ne_plante_pas():
    r = st.analyze(_m())
    assert r["min_stability"] == 0.0
    assert r["unsupported"] == []


def test_collision_toujours_bloquee():
    """La stabilité ne doit pas affaiblir la détection de collision."""
    m = _m()
    m.place("3001", 0, 0, 0, "4")
    with pytest.raises(CollisionError):
        m.place("3001", 1, 0, 0, "1")
