#!/usr/bin/env python3
"""Tests de la bibliothèque de construction patterns (tools/patterns.py)."""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import patterns as pt  # noqa: E402


def test_mix_1_largeur():
    mix = pt.part_mix("cheap", depth2=False)
    assert (1, 3) in mix and (1, 1) in mix
    assert mix[(1, 3)] == [pt.BRICKS_1[l] for l in pt.BRICKS_1]
    assert (2, 3) not in mix


def test_mix_2_largeurs():
    mix = pt.part_mix("cheap", depth2=True)
    assert mix[(2, 3)] == [pt.BRICKS_2[l] for l in pt.BRICKS_2]
    assert mix[(2, 1)] == list(pt.PLATES_2.values())


def test_strong_alternance():
    a = pt.part_mix("strong", False, level_plate=0)[(1, 3)]
    b = pt.part_mix("strong", False, level_plate=3)[(1, 3)]
    assert a != b
    # longueurs de l'appareillage A/B uniquement
    assert set(a) <= {pt.BRICKS_1[l] for l in pt.STRONG_A}
    assert set(b) <= {pt.BRICKS_1[l] for l in pt.STRONG_B}
    # les plates restent toujours disponibles
    assert pt.part_mix("strong", False, level_plate=3)[(1, 1)]
