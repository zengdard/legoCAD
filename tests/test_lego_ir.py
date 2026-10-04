#!/usr/bin/env python3
"""Tests de la couche LEGO IR (tools/lego_ir.py).

Lancer : python3 -m pytest tests/ -v
"""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import lego_ir as ir  # noqa: E402


def _bp(**kw):
    base = {
        "name": "test",
        "terrain": {"width": 20, "depth": 20, "max_height": 12},
        "components": [],
    }
    base.update(kw)
    return base


def test_parse_ok():
    bp, errs = ir.from_dict(_bp(components=[
        {"type": "wall", "id": "w", "x": 2, "z": 2, "width": 8, "depth": 1,
         "height": 3, "color": "1"},
    ]))
    assert errs == []
    assert len(bp.components) == 1
    assert bp.components[0].height_plates() == 9


def test_type_inconnu_rejete():
    bp, errs = ir.from_dict(_bp(components=[
        {"type": "piscine", "x": 0, "z": 0, "width": 4, "depth": 4},
    ]))
    assert any("type inconnu" in e for e in errs)


def test_hors_terrain():
    bp, errs = ir.from_dict(_bp(components=[
        {"type": "slab", "id": "s", "x": 18, "z": 0, "width": 4, "depth": 4},
    ]))
    assert any("hors terrain" in e for e in errs)


def test_chevauchement_rejete():
    bp, errs = ir.from_dict(_bp(components=[
        {"type": "slab", "id": "a", "x": 0, "z": 0, "width": 6, "depth": 6},
        {"type": "slab", "id": "b", "x": 3, "z": 3, "width": 6, "depth": 6},
    ]))
    assert any("chevauchent" in e for e in errs)
    # touching is fine
    _, errs2 = ir.from_dict(_bp(components=[
        {"type": "slab", "id": "a", "x": 0, "z": 0, "width": 6, "depth": 6},
        {"type": "slab", "id": "b", "x": 6, "z": 0, "width": 6, "depth": 6},
    ]))
    assert errs2 == []


def test_hauteur_max():
    bp, errs = ir.from_dict(_bp(components=[
        {"type": "tower", "id": "t", "x": 0, "z": 0, "size": 6,
         "height": 99},
    ]))
    assert any("max_height" in e for e in errs)


def test_ouverture_deborde():
    bp, errs = ir.from_dict(_bp(components=[
        {"type": "wall", "id": "w", "x": 0, "z": 0, "width": 6, "depth": 1,
         "height": 4,
         "openings": [{"kind": "gate", "offset": 4, "width": 4, "top": 6}]},
    ]))
    assert any("déborde" in e for e in errs)


def test_regions_wall():
    bp, _ = ir.from_dict(_bp(components=[
        {"type": "wall", "id": "w", "x": 2, "z": 3, "width": 6, "depth": 1,
         "height": 3,
         "openings": [{"kind": "gate", "offset": 2, "width": 2,
                       "top": 6}]},
    ]))
    rs = ir.regions(bp)
    assert len(rs) == 1
    r = rs[0]
    assert r.cells == {(x, 3) for x in range(2, 8)}
    # porte : cellules (4,3) et (5,3) creusées jusqu'à 6 plaques
    assert set(r.holes[(4, 3)]) == set(range(6))
    assert (2, 3) not in r.holes
    assert r.y_top == 9


def test_regions_tower_ring():
    bp, _ = ir.from_dict(_bp(components=[
        {"type": "tower", "id": "t", "x": 0, "z": 0, "size": 6, "height": 4},
    ]))
    r = ir.regions(bp)[0]
    assert (0, 0) in r.cells and (5, 5) in r.cells
    assert (2, 2) not in r.cells and (3, 3) not in r.cells
    assert len(r.cells) == 20  # périmètre 6x6


def test_regions_box_floor_interieur():
    bp, _ = ir.from_dict(_bp(components=[
        {"type": "box", "id": "b", "x": 0, "z": 0, "width": 6, "depth": 6,
         "height": 3, "floor": True},
    ]))
    rs = ir.regions(bp)
    ring = rs[0]
    floor = rs[1]
    assert ring.cells.isdisjoint(floor.cells)
    assert (1, 1) in floor.cells and (4, 4) in floor.cells


def test_palette():
    bp, errs = ir.from_dict(_bp(palette=["1", "2"], components=[
        {"type": "slab", "id": "s", "x": 0, "z": 0, "width": 4,
         "depth": 4, "color": "85"},
    ]))
    assert any("hors palette" in e for e in errs)
