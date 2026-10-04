#!/usr/bin/env python3
"""Tests du solver design : résolution des attachements (tools/lego_ir.py)
et cache de solutions de modules (tools/solver.py)."""
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import lego_ir as ir  # noqa: E402


def _bp(components):
    return {"terrain": {"width": 32, "depth": 32, "max_height": 12},
            "components": components}


def test_attach_positions():
    bp, errs = ir.from_dict(_bp([
        {"type": "tower", "id": "t1", "x": 4, "z": 4, "size": 6,
         "height": 4},
        {"type": "wall", "id": "w", "width": 8, "depth": 2, "height": 3,
         "attach": {"to": "t1", "side": "+x", "offset": 2}},
        {"type": "tower", "id": "t2", "size": 6, "height": 4,
         "attach": {"to": "w", "side": "+x"}},
    ]))
    assert errs == []
    by_id = {c.cid: c for c in bp.components}
    assert (by_id["w"].x, by_id["w"].z) == (10, 6)   # t1.x+6, t1.z+2
    assert (by_id["t2"].x, by_id["t2"].z) == (18, 6)  # w.x+8, w.z
    # collé : les empreintes se touchent sans se chevaucher
    assert by_id["t1"].x + by_id["t1"].width == by_id["w"].x
    assert by_id["w"].x + by_id["w"].width == by_id["t2"].x


def test_attach_negative_sides():
    bp, errs = ir.from_dict(_bp([
        {"type": "tower", "id": "t1", "x": 10, "z": 10, "size": 6,
         "height": 4},
        {"type": "wall", "id": "w", "width": 4, "depth": 1, "height": 3,
         "attach": {"to": "t1", "side": "-z", "offset": 1, "gap": 1}},
    ]))
    assert errs == []
    w = {c.cid: c for c in bp.components}["w"]
    assert w.z == 10 - 1 - 1          # t1.z - gap - depth
    assert w.x == 10 + 1              # t1.x + offset


def test_attach_ancre_inconnue():
    _, errs = ir.from_dict(_bp([
        {"type": "wall", "id": "w", "width": 4, "depth": 1, "height": 3,
         "attach": {"to": "fantome", "side": "+x"}},
    ]))
    assert any("inconnu" in e for e in errs)


def test_attach_cyclique():
    _, errs = ir.from_dict(_bp([
        {"type": "wall", "id": "a", "width": 4, "depth": 1, "height": 3,
         "attach": {"to": "b", "side": "+x"}},
        {"type": "wall", "id": "b", "width": 4, "depth": 1, "height": 3,
         "attach": {"to": "a", "side": "+x"}},
    ]))
    assert any("cyclique" in e for e in errs)


def test_attach_hors_terrain():
    _, errs = ir.from_dict(_bp([
        {"type": "tower", "id": "t1", "x": 28, "z": 4, "size": 6,
         "height": 4},
        {"type": "wall", "id": "w", "width": 8, "depth": 1, "height": 3,
         "attach": {"to": "t1", "side": "+x"}},
    ]))
    assert any("hors terrain" in e for e in errs)


def test_cache_modules_identiques():
    """Quatre tours identiques attachées en carré : une seule résolution
    de solver (3 hits de cache), 1 seul amas, stabilité >= 0.8."""
    import solver as sv
    calls = {"n": 0}
    orig = sv.solve_region

    def counting(region, dims, *a, **kw):
        calls["n"] += 1
        return orig(region, dims, *a, **kw)
    sv.solve_region = counting
    try:
        bp, errs = ir.from_dict(_bp([
            {"type": "tower", "id": "t1", "x": 2, "z": 2, "size": 6,
             "height": 4, "color": "72", "roof": "conical"},
            {"type": "tower", "id": "t2", "size": 6, "height": 4,
             "color": "72", "roof": "conical",
             "attach": {"to": "t1", "side": "+x"}},
            {"type": "tower", "id": "t3", "size": 6, "height": 4,
             "color": "72", "roof": "conical",
             "attach": {"to": "t1", "side": "+z"}},
            {"type": "tower", "id": "t4", "size": 6, "height": 4,
             "color": "72", "roof": "conical",
             "attach": {"to": "t3", "side": "+x"}},
        ]))
        assert errs == []
        model, rep = sv.solve_blueprint(bp, time_limit=45)
    finally:
        sv.solve_region = orig
    assert rep["status"] == "OK", rep["issues"]
    assert calls["n"] == 1            # 4 régions identiques, 1 solve
    assert rep["islands"] == 1        # tours jointives -> connectées
    assert rep["min_stability"] >= 0.8
    # les 4 tours sont bien présentes aux 4 positions
    xs = {(b["x"], b["z"]) for b in model.bricks}
    assert len({x for x, _ in xs}) >= 2 and len({z for _, z in xs}) >= 2
