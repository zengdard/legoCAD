#!/usr/bin/env python3
"""Rendu SVG isométrique sans dépendance : aperçu et images de notice.

LeoCAD produit de beaux rendus mais exige Flatpak, 615 Mo de bibliothèque et
un serveur graphique. Pour que le projet fonctionne **en ligne** (Docker, VPS,
CI), ce module dessine chaque brique comme un pavé isométrique coloré, avec
ses tenons. Ce n'est pas un rendu photoréaliste, mais c'est :
  - instantané (quelques millisecondes pour 500 pièces) ;
  - sans dépendance (SVG pur, lisible dans un navigateur) ;
  - fidèle à la géométrie compilée (pas d'artefact de pièce inconnue).

C'est aussi le rendu utilisé pour les images d'étapes quand LeoCAD est absent.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
UNIT = 10.0              # px par stud
PLATE_H = 4.0            # px par plaque
COS30 = math.cos(math.radians(30))
SIN30 = 0.5


def _colors() -> dict:
    try:
        return json.loads((PROJECT / "pieces_catalog.json").read_text())["colors"]
    except (OSError, ValueError, KeyError):
        return {}


def _shade(hex_color: str, factor: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    r, g, b = (max(0, min(255, int(v * factor))) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _project(x: float, y: float, z: float) -> tuple[float, float]:
    return ((x - z) * COS30 * UNIT,
            (x + z) * SIN30 * UNIT - y * PLATE_H)


def _part_height(model, b: dict, part: dict) -> int:
    from ldraw_model import LDU_PER_LEVEL, _NOMINAL_H
    return max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)


def _payload(model) -> list[dict]:
    """Briques avec leur empreinte, hauteur et couleur, prêtes à dessiner."""
    colors = _colors()
    out = []
    for b in model.bricks:
        part = model.part(b["part_id"])
        sx, sz = model._footprint(part, b["rot"])
        h = _part_height(model, b, part)
        hexcol = colors.get(str(b["color"]), {}).get("hex", "#C91A09")
        out.append({"x": b["x"], "z": b["z"], "y": b["y"],
                    "w": sx, "d": sz, "h": h, "hex": hexcol})
    return out


def render_svg(model, title: str | None = None,
               max_parts: int | None = None,
               background: str | None = None) -> str:
    """Rendu SVG d'un modèle (ou des `max_parts` premières pièces)."""
    bricks = _payload(model)
    if max_parts is not None:
        bricks = bricks[:max_parts]
    if not bricks:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="320" '
                'height="180"><text x="16" y="40">modèle vide</text></svg>')
    # bornes projetées
    xs, ys = [], []
    for b in bricks:
        for (dx, dz) in ((0, 0), (b["w"], 0), (0, b["d"]),
                         (b["w"], b["d"])):
            for dy in (0, b["h"]):
                px, py = _project(b["x"] + dx, b["y"] + dy, b["z"] + dz)
                xs.append(px)
                ys.append(py)
    pad, stud_h = 26.0, 6.0
    minx, maxx = min(xs) - pad, max(xs) + pad
    miny, maxy = min(ys) - pad - stud_h, max(ys) + pad
    w, h = maxx - minx, maxy - miny
    # tri peintre : du plus loin au plus proche
    bricks.sort(key=lambda b: (b["x"] + b["w"] / 2 + b["z"] + b["d"] / 2
                               + (b["y"] + b["h"] / 2) * 0.6))
    body = []
    for b in bricks:
        x, z, y = b["x"], b["z"], b["y"]
        ww, dd, hh = b["w"], b["d"], b["h"]
        top = [_project(x, y + hh, z), _project(x + ww, y + hh, z),
               _project(x + ww, y + hh, z + dd),
               _project(x, y + hh, z + dd)]
        left = [_project(x, y, z + dd), _project(x, y + hh, z + dd),
                _project(x + ww, y + hh, z + dd),
                _project(x + ww, y, z + dd)]
        right = [_project(x + ww, y, z), _project(x + ww, y + hh, z),
                 _project(x + ww, y + hh, z + dd),
                 _project(x + ww, y, z + dd)]
        poly = lambda pts, fill, op=1.0: (
            '<polygon points="' +
            " ".join(f"{px:.1f},{py:.1f}" for px, py in pts) +
            f'" fill="{fill}" fill-opacity="{op}" stroke="#0b0d10" '
            'stroke-opacity=".22" stroke-width=".7"/>')
        body.append(poly(left, _shade(b["hex"], 0.72)))
        body.append(poly(right, _shade(b["hex"], 0.86)))
        body.append(poly(top, b["hex"]))
        # tenons
        stud_rx = UNIT * 0.30
        stud_ry = stud_rx * 0.52
        for ix in range(ww):
            for iz in range(dd):
                cx, cy = _project(x + ix + 0.5, y + hh, z + iz + 0.5)
                body.append(
                    f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{stud_rx:.1f}" '
                    f'ry="{stud_ry:.1f}" fill="{_shade(b["hex"], 1.14)}" '
                    'stroke="#0b0d10" stroke-opacity=".25" stroke-width=".5"/>')
    bg = (f'<rect x="0" y="0" width="100%" height="100%" fill="{background}"/>'
          if background else "")
    label = (f'<title>{title}</title>' if title else "")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.1f} '
            f'{miny:.1f} {w:.1f} {h:.1f}" width="{int(w)}" height="{int(h)}" '
            f'role="img" aria-label="modèle LEGO">' + label + bg +
            "".join(body) + "</svg>")


def save_svg(model, path: str | Path, **kwargs) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_svg(model, **kwargs), encoding="utf-8")
    return path


def render_steps(model, out_dir: str | Path, steps: list[tuple[int, int]],
                 **kwargs) -> list[Path]:
    """Une image SVG par étape (les pièces sont ajoutées progressivement)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, (_a, end) in enumerate(steps, start=1):
        p = out / f"step{k:02d}.svg"
        p.write_text(render_svg(model, max_parts=end, **kwargs),
                     encoding="utf-8")
        paths.append(p)
    return paths


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(PROJECT / "tools"))
    from ldraw_model import LDrawModel
    import voxel
    from brickify import brickify
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if not src:
        raise SystemExit("usage: preview_svg.py modele.ldr [sortie.svg]")
    grid = voxel.from_ldr(src)
    model, _ = brickify(grid, Path(src).stem)
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        PROJECT / "renders" / (Path(src).stem + ".svg")
    save_svg(model, out)
    print(out)
