#!/usr/bin/env python3
"""Import « natif » d'un modèle LDraw : on garde les pièces d'origine.

Le pipeline volume → briques (`brickify`) reconstruit un modèle à partir
d'une forme. Pour **étudier un modèle existant** (OMR, Classic Space,
BrickBench), on veut l'inverse : conserver les pièces, leurs couleurs et leur
ordre, puis produire une nomenclature, un aperçu et une notice — et mesurer
la validité avec les mêmes règles que nos modèles.

Limite assumée : seules les rotations d'axe Y (0/90/180/270°) sont
représentées sur notre grille. Les pièces à charnière/axe/rotule (BrickNet
distingue stud/hinge/axle/ball/fixed) sont importées si leur pose est
axis-aligned, sinon ignorées et comptées. C'est un visualiseur/validateur,
pas un solveur de connecteurs non-stud.
"""
from __future__ import annotations

import math
from pathlib import Path

import voxel
from ldraw_model import (CollisionError, LDrawModel, UnknownPartError,
                         LDU_PER_LEVEL, STUD, part_levels)


def _y_rotation(mat: tuple) -> int | None:
    """Rotation autour de Y (0/90/180/270) ou None si la pose est oblique."""
    a, b, c, d, e, f, g, h, i = mat
    if abs(b) > 1e-3 or abs(d) > 1e-3 or abs(f) > 1e-3 or abs(h) > 1e-3 \
            or abs(abs(e) - 1) > 1e-3:
        return None
    if abs(a - 1) < 1e-3 and abs(c) < 1e-3 and abs(g) < 1e-3 \
            and abs(i - 1) < 1e-3:
        return 0
    if abs(a) < 1e-3 and abs(c + 1) < 1e-3 and abs(g - 1) < 1e-3 \
            and abs(i) < 1e-3:
        return 90
    if abs(a + 1) < 1e-3 and abs(c) < 1e-3 and abs(g) < 1e-3 \
            and abs(i + 1) < 1e-3:
        return 180
    if abs(a) < 1e-3 and abs(c - 1) < 1e-3 and abs(g + 1) < 1e-3 \
            and abs(i) < 1e-3:
        return 270
    return None


def _nominal_height(part_id: str) -> int:
    """Hauteur nominale en plaques (brique 3, plaque/tile 1)."""
    from ldraw_model import _part_data
    data = _part_data(part_id)
    if not data:
        return 3
    return part_levels(data)


def read_parts(path: str | Path) -> tuple[list[dict], dict]:
    """Liste les poses de pièces d'un .ldr/.mpd (sous-modèles développés)."""
    models, root = voxel._ldr_lines(path)
    records, skipped = [], 0
    for color, pos, mat, pid in voxel._expand(root, models):
        rot = _y_rotation(mat)
        if rot is None:
            skipped += 1
            continue
        records.append({"part_id": pid, "color": color, "pos": pos,
                        "rot": rot})
    return records, {"skipped_rotated": skipped, "raw": len(records) + skipped}


def load(path: str | Path, name: str | None = None) -> tuple[LDrawModel, dict]:
    """Charge un modèle LDraw en conservant les pièces (poses axis-aligned)."""
    records, stats = read_parts(path)
    model = LDrawModel(name or Path(path).stem)
    if not records:
        return model, {**stats, "pieces": 0, "collisions": 0, "unknown": 0}
    # hauteur minimale (convertie en plaques) pour normaliser le sol à y=0
    bases = []
    for r in records:
        # le y LDraw est le centre : on retire la demi-hauteur de la pièce
        try:
            part = _nominal_height(r["part_id"])
        except Exception:
            part = 24
        bases.append(round(-r["pos"][1] / LDU_PER_LEVEL - part / 2.0))
    min_base = min(bases) if bases else 0
    collisions = unknown = 0
    placed = 0
    for r, base in zip(records, bases):
        try:
            data = model.part(r["part_id"])
        except UnknownPartError:
            unknown += 1
            continue
        sx = max(1, round(float(data.get("studs_x", 1))))
        sz = max(1, round(float(data.get("studs_z", 1))))
        dx, dz = (sz, sx) if r["rot"] in (90, 270) else (sx, sz)
        x = round((r["pos"][0] + STUD / 2.0) / STUD - dx / 2.0)
        z = round((r["pos"][2] + STUD / 2.0) / STUD - dz / 2.0)
        try:
            model.place(r["part_id"], x, z, base - min_base, r["color"],
                        r["rot"])
            placed += 1
        except (CollisionError, ValueError):
            collisions += 1
    # steps : les frontières du .ldr ne sont pas conservées par _expand ;
    # on laisse un seul step (l'ordre d'origine reste l'ordre de pose).
    stats.update({"pieces": placed, "collisions": collisions,
                  "unknown": unknown})
    return model, stats


def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if len(sys.argv) < 2:
        raise SystemExit("usage: ldr_io.py modele.ldr/.mpd")
    model, stats = load(sys.argv[1])
    print(stats)
    print(model.parts_summary())
    if len(sys.argv) > 2:
        model.save(sys.argv[2])
        print("sauvé :", sys.argv[2])


if __name__ == "__main__":
    main()
