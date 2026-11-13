#!/usr/bin/env python3
"""Banc d'essai reproductible : validité, couverture, stabilité, temps.

Inspiré de **BrickBench** (brickben.ch, 2026) : la question n'est pas
« est-ce joli ? » mais « est-ce valide ? » (pièces réelles, pas de collision,
stable, un seul composant) puis « est-ce que ça ressemble à un set ? ».
On mesure les deux, et on publie les chiffres plutôt que des impressions.

    python3 tools/bench.py --shapes
    python3 tools/bench.py --ldr /tmp/omr/sets --limit 20
    python3 tools/bench.py --ldr ~/Téléchargements/clspace --native --limit 10
    python3 tools/bench.py --shapes --json out/bench.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import brickify                     # noqa: E402
import ldr_io                       # noqa: E402
import quality                      # noqa: E402
import shapes                       # noqa: E402
import studs                        # noqa: E402
import voxel                        # noqa: E402


def _row(name: str, model, report: dict, seconds: float,
         extra: dict | None = None) -> dict:
    val = quality.validity(model, report)
    return {
        "name": name,
        "pieces": report.get("pieces", 0),
        "types": report.get("types", 0),
        "coverage": report.get("coverage", 0.0),
        "islands": report.get("islands", 0),
        "stability": report.get("min_stability", 0.0),
        "slopes": report.get("slopes", 0),
        "valid": val["valid"],
        "reasons": val["reasons"],
        "seconds": round(seconds, 2),
        **(extra or {}),
    }


def run_shapes() -> list[dict]:
    rows = []
    for name in sorted(shapes.SHAPES):
        if name == "mosaic":
            continue
        t = time.time()
        try:
            grid = shapes.make(name)
            model, rep = brickify.brickify(grid, name)
            rows.append(_row(name, model, rep, time.time() - t))
        except Exception as exc:
            rows.append({"name": name, "valid": False,
                         "reasons": [str(exc)], "seconds": 0})
    return rows


def run_ldr(directory: Path, limit: int, native: bool) -> list[dict]:
    files = sorted(directory.rglob("*.ldr")) + sorted(directory.rglob("*.mpd"))
    files = files[:limit] if limit else files
    rows = []
    for path in files:
        t = time.time()
        try:
            if native:
                model, stats = ldr_io.load(path)
                rep = studs.report(model)
                rep = {**rep, "pieces": len(model.bricks),
                       "coverage": 1.0,
                       "min_stability": __import__("stability").analyze(
                           model)["min_stability"]}
            else:
                grid = voxel.from_ldr(path)
                model, rep = brickify.brickify(grid, path.stem)
            rows.append(_row(path.name, model, rep, time.time() - t,
                             {"import": native}))
        except Exception as exc:
            rows.append({"name": path.name, "valid": False,
                         "reasons": [str(exc)], "seconds": round(
                             time.time() - t, 2)})
    return rows


def _print(rows: list[dict]) -> None:
    head = (f"{'modèle':28s} {'pièces':>7} {'couv.':>6} {'amas':>5} "
            f"{'stab.':>5} {'valid':>6} {'s':>6}")
    print(head)
    print("-" * len(head))
    for r in rows:
        print(f"{str(r['name'])[:28]:28s} {r.get('pieces',0):7d} "
              f"{r.get('coverage',0):6.1%} {r.get('islands',0):5d} "
              f"{r.get('stability',0):5.2f} "
              f"{('oui' if r.get('valid') else 'NON'):>6} "
              f"{r.get('seconds',0):6.2f}")
        if not r.get("valid") and r.get("reasons"):
            print(f"  ↳ {', '.join(str(x) for x in r['reasons'])[:100]}")
    if rows:
        valid = sum(1 for r in rows if r.get("valid"))
        print(f"\n{valid}/{len(rows)} valides · "
              f"temps médian {statistics.median(r.get('seconds',0) for r in rows):.2f}s")


def main():
    ap = argparse.ArgumentParser(description="benchmark legoCAD")
    ap.add_argument("--shapes", action="store_true")
    ap.add_argument("--ldr", metavar="DOSSIER")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--native", action="store_true",
                    help="importer les pièces d'origine au lieu de recompiler")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    rows = []
    if args.shapes or not args.ldr:
        rows += run_shapes()
    if args.ldr:
        rows += run_ldr(Path(args.ldr), args.limit, args.native)
    _print(rows)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2,
                                              ensure_ascii=False))
        print(f"JSON : {args.json}")


if __name__ == "__main__":
    main()
