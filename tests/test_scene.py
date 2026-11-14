#!/usr/bin/env python3
"""Composeur de scènes (`tools/scene.py`)."""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import brickify  # noqa: E402
import scene  # noqa: E402
import voxel  # noqa: E402


def test_scene_compose_et_compile():
    s = scene.Scene(20)
    s.path(8, 0, 4, 20, "19")
    s.cottage(1, 1, 8, 6, scene.TAN, scene.DARKRED)
    s.figure(12, 10, scene.RED, scene.BROWN)
    s.tree(14, 14)
    s.pond(2, 12, 6, 6)
    s.stall(10, 4)
    s.barrel(16, 8)
    s.lamp(6, 8)
    s.wall(20)
    grid = s.build()
    model, rep = brickify.brickify(grid, "scene")
    assert rep["coverage"] == 1.0
    assert rep["islands"] == 1
    assert rep["min_stability"] >= 0.8
    assert rep["unsupported"] == []


def test_figure_a_des_yeux_et_une_bouche():
    g = voxel.VoxelGrid()
    scene.figure(g, 0, 0, scene.BLUE, scene.YELLOW)
    assert g.cells[(1, 10, 0)] == "0"      # œil gauche
    assert g.cells[(2, 10, 0)] == "0"      # œil droit
    assert g.cells[(1, 9, 0)] == scene.DARKRED   # bouche
    assert g.cells[(1, 12, 0)] == scene.YELLOW   # cheveux


def test_scene_village_est_un_set():
    grid = scene.village()
    assert 500 <= grid.count() <= 8000
    model, rep = brickify.brickify(grid, "village")
    assert rep["coverage"] == 1.0
    assert rep["islands"] == 1
    assert rep["pieces"] >= 800
