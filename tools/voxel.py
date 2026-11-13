#!/usr/bin/env python3
"""Grille de voxels : le chaînon manquant entre « une forme » et « des briques ».

Le problème du pipeline blueprint (composants `wall` / `box` / `tower`) est
qu'il ne peut représenter que des boîtes : le LLM décrit une maison, le
résultat est un empilement de pavés. Un vrai modèle LEGO est d'abord un
**volume** (une silhouette), que l'on pave ensuite avec des pièces.

`VoxelGrid` est cette représentation intermédiaire, volontairement simple :

  - un voxel = une cellule (x, z) sur une **plaque** de hauteur (y) ;
    l'unité verticale est la plaque (8 LDU), comme dans un vrai modèle où
    les détails font 1 plaque et les briques 3 plaques ;
  - chaque voxel porte un code couleur LDraw ;
  - des primitives pour sculpter (boîte, ellipsoïde, cylindre, cône,
    coque), des transformations (miroir, translation, échelle) ;
  - des importateurs : ASCII multi-couches, images (silhouettes), fichier
    LDraw existant ;
  - l'export est consommé par `tools/brickify.py` qui produit un modèle
    constructible (studs vérifiés) et une nomenclature réelle.

Un fichier `.vox.json` (ou des couches ASCII) est donc un « plan de volume »
stable, indépendant du solveur de briques.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

# Codes LDraw des couleurs courantes (voir pieces_catalog.json).
CHAR_COLORS = {
    "R": "4",    # rouge
    "B": "1",    # bleu
    "G": "2",    # vert
    "Y": "14",   # jaune
    "W": "15",   # blanc
    "K": "0",    # noir
    "O": "25",   # orange
    "N": "70",   # marron
    "A": "71",   # gris clair
    "D": "72",   # gris foncé
    "T": "19",   # tan
    "L": "28",   # dark tan
    "P": "5",    # rose
    "C": "3",    # cyan
    "M": "26",   # magenta / purple approx.
}

EMPTY_CHARS = ". _~"


def _catalog_colors() -> dict:
    path = Path(__file__).resolve().parent.parent / "pieces_catalog.json"
    try:
        return json.loads(path.read_text()).get("colors", {})
    except (OSError, ValueError):
        return {}


class VoxelGrid:
    """Ensemble de voxels colorés ; y est en plaques, (x, z) en studs."""

    def __init__(self, cells: dict | None = None):
        self.cells: dict[tuple[int, int, int], str] = dict(cells or {})

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def add(self, x: int, y: int, z: int, color: str = "4") -> None:
        self.cells[(int(x), int(y), int(z))] = str(color)

    def box(self, x: int, y: int, z: int, w: int, h: int, d: int,
            color: str = "4") -> "VoxelGrid":
        for xx in range(x, x + w):
            for yy in range(y, y + h):
                for zz in range(z, z + d):
                    self.add(xx, yy, zz, color)
        return self

    def ellipsoid(self, cx: float, cy: float, cz: float, rx: float,
                  ry: float, rz: float, color: str = "4",
                  hollow: int = 0) -> "VoxelGrid":
        """Ellipsoïde plein (ou coque d'épaisseur `hollow` voxels)."""
        for x in range(math.floor(cx - rx), math.ceil(cx + rx) + 1):
            for y in range(math.floor(cy - ry), math.ceil(cy + ry) + 1):
                for z in range(math.floor(cz - rz), math.ceil(cz + rz) + 1):
                    d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 + \
                        ((z - cz) / rz) ** 2
                    if d > 1.0:
                        continue
                    if hollow:
                        d2 = ((x - cx) / max(0.1, rx - hollow)) ** 2 + \
                             ((y - cy) / max(0.1, ry - hollow)) ** 2 + \
                             ((z - cz) / max(0.1, rz - hollow)) ** 2
                        if d2 <= 1.0:
                            continue
                    self.add(x, y, z, color)
        return self

    def cylinder(self, cx: float, cz: float, y0: int, y1: int, r: float,
                 color: str = "4", hollow: int = 0) -> "VoxelGrid":
        for x in range(math.floor(cx - r), math.ceil(cx + r) + 1):
            for z in range(math.floor(cz - r), math.ceil(cz + r) + 1):
                d = math.hypot(x - cx, z - cz)
                if d > r or (hollow and d < r - hollow):
                    continue
                for y in range(y0, y1):
                    self.add(x, y, z, color)
        return self

    def cone(self, cx: float, cz: float, y0: int, y1: int,
             r0: float, r1: float, color: str = "4") -> "VoxelGrid":
        """Cône/tronc de rayon r0 (base) à r1 (sommet)."""
        span = max(1, y1 - y0)
        for y in range(y0, y1):
            t = (y - y0) / span
            r = r0 + (r1 - r0) * t
            for x in range(math.floor(cx - r), math.ceil(cx + r) + 1):
                for z in range(math.floor(cz - r), math.ceil(cz + r) + 1):
                    if math.hypot(x - cx, z - cz) <= r:
                        self.add(x, y, z, color)
        return self

    # ------------------------------------------------------------------ #
    # Transformations
    # ------------------------------------------------------------------ #
    def mirror_x(self, at: int | None = None) -> "VoxelGrid":
        """Miroir selon x (par défaut : à droite du volume)."""
        if not self.cells:
            return self
        minx, maxx = min(c[0] for c in self.cells), max(c[0] for c in self.cells)
        at = minx + maxx if at is None else at
        return VoxelGrid({(at - x, y, z): c
                          for (x, y, z), c in self.cells.items()})

    def translate(self, dx: int = 0, dy: int = 0, dz: int = 0) -> "VoxelGrid":
        return VoxelGrid({(x + dx, y + dy, z + dz): c
                          for (x, y, z), c in self.cells.items()})

    def normalize(self) -> "VoxelGrid":
        """Ramène le coin minimal à (0, 0, 0)."""
        if not self.cells:
            return self
        dx = min(c[0] for c in self.cells)
        dy = min(c[1] for c in self.cells)
        dz = min(c[2] for c in self.cells)
        return self.translate(-dx, -dy, -dz)

    def shell(self, thickness: int = 1) -> "VoxelGrid":
        """Garde uniquement l'écorce du volume (murs creux, coque)."""
        keep = {}
        neigh = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                 (0, 0, 1), (0, 0, -1))
        for (x, y, z), c in self.cells.items():
            for r in range(1, thickness + 1):
                if any((x + dx * r, y + dy * r, z + dz * r) not in self.cells
                       for dx, dy, dz in neigh):
                    keep[(x, y, z)] = c
                    break
        return VoxelGrid(keep)

    def paint(self, cells, color: str) -> "VoxelGrid":
        for c in cells:
            if c in self.cells:
                self.cells[c] = str(color)
        return self

    def paint_box(self, x: int, y: int, z: int, w: int, h: int, d: int,
                  color: str) -> "VoxelGrid":
        """Peint les voxels existants d'un volume (sans en créer)."""
        for xx in range(x, x + w):
            for yy in range(y, y + h):
                for zz in range(z, z + d):
                    if (xx, yy, zz) in self.cells:
                        self.cells[(xx, yy, zz)] = str(color)
        return self

    def clean_colors(self, min_size: int = 3, passes: int = 3) -> "VoxelGrid":
        """Supprime les taches de couleur trop petites (bruit, détails de
        surface non constructibles) en les fondant dans la couleur voisine
        dominante. Une tache de 1-2 voxels sur une paroi ne peut pas être
        attachée : la garder produirait une pièce isolée."""
        cells = dict(self.cells)
        neigh = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0),
                 (0, 0, 1), (0, 0, -1))
        for _ in range(passes):
            changed = False
            # composantes connexes de même couleur
            seen = set()
            for start in cells:
                if start in seen:
                    continue
                color = cells[start]
                comp = {start}
                stack = [start]
                seen.add(start)
                while stack:
                    c = stack.pop()
                    for d in neigh:
                        n = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
                        if n in cells and n not in seen and cells[n] == color:
                            seen.add(n)
                            comp.add(n)
                            stack.append(n)
                if len(comp) >= min_size:
                    continue
                votes: dict[str, int] = {}
                for c in comp:
                    for d in neigh:
                        n = (c[0] + d[0], c[1] + d[1], c[2] + d[2])
                        if n in cells and cells[n] != color:
                            votes[cells[n]] = votes.get(cells[n], 0) + 1
                if votes:
                    new = max(votes.items(), key=lambda kv: kv[1])[0]
                    for c in comp:
                        cells[c] = new
                    changed = True
            if not changed:
                break
        return VoxelGrid(cells)

    def erase(self, x: int, y: int, z: int, w: int, h: int,
              d: int) -> "VoxelGrid":
        for xx in range(x, x + w):
            for yy in range(y, y + h):
                for zz in range(z, z + d):
                    self.cells.pop((xx, yy, zz), None)
        return self

    def fill_holes_2d(self) -> "VoxelGrid":
        """Bouche les trous fermés de chaque couche horizontale."""
        out = dict(self.cells)
        for y in {c[1] for c in self.cells}:
            cells = {(x, z) for (x, yy, z) in self.cells if yy == y}
            if not cells:
                continue
            minx, maxx = min(c[0] for c in cells), max(c[0] for c in cells)
            minz, maxz = min(c[1] for c in cells), max(c[1] for c in cells)
            # flood fill depuis l'extérieur de la boîte englobante
            outside = set()
            stack = [(minx - 1, minz - 1)]
            limit = {(x, z) for x in range(minx - 1, maxx + 2)
                     for z in range(minz - 1, maxz + 2)}
            while stack:
                c = stack.pop()
                if c in outside or c not in limit or c in cells:
                    continue
                outside.add(c)
                stack.extend(((c[0] + 1, c[1]), (c[0] - 1, c[1]),
                              (c[0], c[1] + 1), (c[0], c[1] - 1)))
            for c in limit - outside - cells:
                # couleur du voisin le plus proche
                col = next((self.cells[(x, y, z)]
                            for x, z in ((c[0] + 1, c[1]), (c[0] - 1, c[1]),
                                         (c[0], c[1] + 1), (c[0], c[1] - 1))
                            if (x, y, z) in self.cells), "4")
                out[(c[0], y, c[1])] = col
        return VoxelGrid(out)

    def crop(self, x0: int, x1: int, y0: int, y1: int,
             z0: int, z1: int) -> "VoxelGrid":
        return VoxelGrid({(x, y, z): c for (x, y, z), c in self.cells.items()
                          if x0 <= x < x1 and y0 <= y < y1 and z0 <= z < z1})

    # ------------------------------------------------------------------ #
    # Interrogation / export
    # ------------------------------------------------------------------ #
    def bounds(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        if not self.cells:
            return (0, 0, 0), (0, 0, 0)
        lo = tuple(min(c[i] for c in self.cells) for i in range(3))
        hi = tuple(max(c[i] for c in self.cells) + 1 for i in range(3))
        return lo, hi

    def size(self) -> tuple[int, int, int]:
        lo, hi = self.bounds()
        return tuple(hi[i] - lo[i] for i in range(3))

    def count(self) -> int:
        return len(self.cells)

    def color_counts(self) -> dict:
        out: dict[str, int] = {}
        for c in self.cells.values():
            out[c] = out.get(c, 0) + 1
        return out

    def levels(self) -> dict:
        out: dict[int, int] = {}
        for (_, y, _) in self.cells:
            out[y] = out.get(y, 0) + 1
        return out

    def to_ascii(self, empty: str = ".") -> str:
        """Une couche par niveau de plaque, de bas en haut."""
        lo, hi = self.bounds()
        by_char = {v: k for k, v in CHAR_COLORS.items()}
        lines = []
        for y in range(lo[1], hi[1]):
            lines.append(f"# y={y}")
            for z in range(lo[2], hi[2]):
                row = "".join(
                    empty if (x, y, z) not in self.cells
                    else by_char.get(self.cells[(x, y, z)], "#")
                    for x in range(lo[0], hi[0]))
                lines.append(row)
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {"format": "legocad-vox/1",
                "colors": {v: k for k, v in CHAR_COLORS.items()},
                "cells": [[x, y, z, c] for (x, y, z), c in
                          sorted(self.cells.items())]}

    @classmethod
    def from_dict(cls, raw: dict) -> "VoxelGrid":
        if raw.get("format") not in (None, "legocad-vox/1"):
            raise ValueError(f"format de voxels inconnu : {raw.get('format')}")
        cells = {}
        for item in raw.get("cells") or []:
            if len(item) != 4:
                raise ValueError("cellule voxel invalide (attendu [x,y,z,c])")
            x, y, z, c = item
            cells[(int(x), int(y), int(z))] = str(c)
        return cls(cells)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "VoxelGrid":
        path = Path(path)
        if path.suffix == ".json":
            return cls.from_dict(json.loads(path.read_text()))
        return cls.from_ascii(path.read_text())


# --------------------------------------------------------------------------- #
# Importateurs
# --------------------------------------------------------------------------- #

def from_ascii(text: str, palette: dict | None = None) -> VoxelGrid:
    """Couches ASCII : `# y=0`, puis une ligne par z (1 caractère = 1 stud).

    Un caractère vide arrête la ligne. `palette` permet de remplacer les
    couleurs par défaut (CHAR_COLORS) : {"#": "4", "b": "1"}.
    """
    pal = {**CHAR_COLORS, **(palette or {})}
    pal["#"] = pal.get("#", "4")
    grid = VoxelGrid()
    y = 0
    z = 0
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            # en-tête de couche : # y=12  (ou commentaire ignoré)
            head = line.lstrip("# ").strip()
            if head.lower().startswith("y="):
                y = int(head.split("=", 1)[1].strip())
                z = 0
            continue
        for x, ch in enumerate(line):
            if ch in EMPTY_CHARS:
                continue
            color = pal.get(ch.upper(), pal.get(ch))
            if color is None:
                raise ValueError(f"caractère de couleur inconnu : {ch!r}")
            grid.add(x, y, z, color)
        z += 1
    return grid.normalize()


def _mat_mul(a, b):
    return tuple(sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3))
                 for r in range(3) for c in range(3))


def _mat_apply(m, v):
    return (m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
            m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
            m[6] * v[0] + m[7] * v[1] + m[8] * v[2])


def _ldr_lines(path: str | Path) -> tuple[dict, list]:
    """Lit un .ldr/.mpd : (sous-modèles {nom: lignes}, lignes racine)."""
    models: dict[str, list] = {}
    root: list = []
    current = None
    for line in Path(path).read_text(errors="replace").splitlines():
        tok = line.split()
        if len(tok) >= 3 and tok[0] == "0" and tok[1].upper() == "FILE":
            current = " ".join(tok[2:]).lower().replace(".ldr", "") \
                .replace(".mpd", "")
            models[current] = []
            continue
        (models[current] if current else root).append(line)
    if not root and models:
        # MPD sans racine explicite : le modèle principal est celui que
        # personne ne référence (les sous-modèles sont référencés par lui).
        referenced = set()
        for lines in models.values():
            for line in lines:
                tok = line.split()
                if len(tok) >= 15 and tok[0] == "1":
                    referenced.add(" ".join(tok[14:]).replace(".dat", "")
                                   .replace(".ldr", "").lower())
        candidates = [name for name in models if name not in referenced]
        pick = candidates[0] if candidates else next(iter(models))
        root = models.pop(pick)
    return models, root


def _expand(lines, models, pos=(0.0, 0.0, 0.0),
            mat=(1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), depth=0):
    """Développe récursivement les sous-modèles en (color, pos, mat, part)."""
    if depth > 16:
        return
    for line in lines:
        tok = line.split()
        if len(tok) < 15 or tok[0] != "1":
            continue
        try:
            color = str(int(tok[1]))
            local_p = (float(tok[2]), float(tok[3]), float(tok[4]))
            local_m = tuple(float(v) for v in tok[5:14])
        except ValueError:
            continue
        name = " ".join(tok[14:]).replace(".dat", "") \
            .replace(".ldr", "").lower()
        # transformation composée parent ∘ enfant
        world_p = tuple(pos[k] + _mat_apply(mat, local_p)[k] for k in range(3))
        world_m = _mat_mul(mat, local_m)
        if name in models:
            yield from _expand(models[name], models, world_p, world_m,
                               depth + 1)
        else:
            yield color, world_p, world_m, name


def from_ldr(path: str | Path) -> VoxelGrid:
    """Voxelise un fichier .ldr/.mpd existant (import d'un vrai modèle).

    Une cellule = un stud × une plaque. La couleur d'une cellule est la plus
    fréquente parmi les pièces qui la couvrent (gère les pièces qui se
    chevauchent dans les modèles LDraw, ex. pentes). Les sous-modèles MPD
    sont développés récursivement."""
    from ldraw_model import LDU_PER_LEVEL, STUD, _part_data, part_levels

    counts: dict[tuple, dict] = {}
    models, root = _ldr_lines(path)
    for color, pos, mat, pid in _expand(root, models):
        data = _part_data(pid)
        if data is None:
            continue
        sx = max(1, round(data["studs_x"]))
        sz = max(1, round(data["studs_z"]))
        h = part_levels(data)
        # rotation 90° : la matrice échange les axes x et z
        rotated = abs(mat[0]) < 0.5
        dx, dz = (sz, sx) if rotated else (sx, sz)
        # le y d'une ligne LDraw est le CENTRE de la pièce (pas sa face
        # supérieure) : on retire la demi-hauteur pour retrouver le niveau
        cell_x = round((pos[0] + STUD / 2.0) / STUD - dx / 2.0)
        cell_z = round((pos[2] + STUD / 2.0) / STUD - dz / 2.0)
        base = round(-pos[1] / LDU_PER_LEVEL - h / 2.0)
        for cx in range(cell_x, cell_x + dx):
            for cz in range(cell_z, cell_z + dz):
                for cy in range(base, base + h):
                    slot = counts.setdefault((cx, cy, cz), {})
                    slot[color] = slot.get(color, 0) + 1
    cells = {cell: max(vals.items(), key=lambda kv: kv[1])[0]
             for cell, vals in counts.items()}
    return VoxelGrid(cells).normalize()


def from_model(model) -> VoxelGrid:
    """Voxelise un LDrawModel déjà construit (utile pour les tests)."""
    cells = {}
    for b in model.bricks:
        part = model.part(b["part_id"])
        sx, sz = model._footprint(part, b["rot"])
        h = part_levels(part)
        for cx in range(b["x"], b["x"] + sx):
            for cz in range(b["z"], b["z"] + sz):
                for cy in range(b["y"], b["y"] + h):
                    cells[(cx, cy, cz)] = str(b["color"])
    return VoxelGrid(cells).normalize()


def nearest_color(rgb: tuple[int, int, int],
                  colors: dict | None = None) -> str:
    """Code LDraw le plus proche d'une couleur RGB (pour les images)."""
    colors = colors or _catalog_colors()
    best, best_d = "4", 1e18
    for code, info in colors.items():
        h = str(info.get("hex", "#000000")).lstrip("#")
        try:
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        except (ValueError, IndexError):
            continue
        d = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if d < best_d:
            best, best_d = code, d
    return best


def from_silhouettes(front, side, top, bg=None,
                     target_width: int | None = 32) -> VoxelGrid:
    """Reconstruit un volume à partir de 3 silhouettes (front/side/top).

    Chaque image peut être un chemin ou un image PIL. Les masques sont
    redimensionnés à la même largeur (`target_width`) puis intersectés
    (visual hull). La couleur vient de l'image de face. C'est la méthode
    la plus simple pour passer d'un dessin ou d'une photo détourée à un
    modèle : trois vues suffisent pour un objet massif.
    """
    from PIL import Image

    def load(img):
        im = img if isinstance(img, Image.Image) else Image.open(img)
        return im.convert("RGBA")

    def mask(im, w, h, flip=False):
        im = im.resize((w, h))
        px = im.load()
        out = set()
        for yy in range(h):
            for xx in range(w):
                r, g, b, a = px[xx, yy]
                if bg is not None:
                    dr = (r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2
                    filled = dr > 900
                else:
                    filled = a > 24 and (r + g + b) < 730
                if filled:
                    out.add((xx, h - 1 - yy) if flip else (xx, yy))
        return out

    f = load(front)
    s = load(side)
    t = load(top)
    w = target_width or max(f.width, s.width, t.width)
    # proportions : on conserve l'échelle de l'image de face
    scale = w / max(1, f.width)
    h = max(1, round(f.height * scale))
    d = max(1, round(s.width * scale))

    mf = mask(f.resize((w, h)), w, h, flip=True)
    ms = mask(s.resize((d, h)), d, h, flip=True)
    mt = mask(t.resize((w, d)), w, d, flip=True)

    grid = VoxelGrid()
    fp = f.resize((w, h)).convert("RGB").load()
    for (x, y) in mf:
        for (z, y2) in ms:
            if y2 != y:
                continue
            if (x, z) not in mt:
                continue
            rgb = fp[x, h - 1 - y]
            grid.add(x, y, z, nearest_color(rgb))
    return grid.normalize()
