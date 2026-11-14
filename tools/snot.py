#!/usr/bin/env python3
"""SNOT / connexions 3D : prototype de pose par **frames de connecteurs**.

La grille voxel de `brickify` ne sait faire que des poses verticales
(rotations autour de Y). Pour les brackets, headlight bricks, charnières et
axes, il faut une pose 3D : une pièce est un volume LDU + des **connecteurs**
(stud, anti-stud, stud latéral) et une matrice de rotation.

Ce module est un prototype volontairement petit :
  - pièces : brique 1×1, brique 1×2, headlight brick 1×1 (stud latéral) ;
  - rotation par matrices 90° (Y, X, Z) ;
  - attachement par connecteur (le nouveau connecteur reçoit le stud) ;
  - collision AABB, connexité par le graphe de connecteurs ;
  - export `.ldr` avec matrices, donc ouvrable dans Studio/LeoCAD.

Il est maintenant **branché** au compilateur comme couche de décoration :
`decorate_wall_banners()` remplace une brique de mur par une 4070 et attache
une plaque 1x2 verticale par le tenon latéral. Les pièces SNOT sont exportées
avec leur matrice complète, comptées dans le BOM et vérifiées en collision.
La grille volumique reste la structure porteuse : le SNOT ne porte pas encore
de charge (pas de mur entièrement en studs latéraux).

    python3 tools/snot.py --out out/snot_demo.ldr
"""
from __future__ import annotations

import argparse
import itertools
import math
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

IDENT = (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0)
# matrices LDraw (lignes) pour les rotations de 90°
ROT = {
    "y90": (0, 0, 1, 0, 1, 0, -1, 0, 0),
    "y180": (-1, 0, 0, 0, 1, 0, 0, 0, -1),
    "y270": (0, 0, -1, 0, 1, 0, 1, 0, 0),
    "x90": (1, 0, 0, 0, 0, -1, 0, 1, 0),
    "x270": (1, 0, 0, 0, 0, 1, 0, -1, 0),
    "z90": (0, 1, 0, -1, 0, 0, 0, 0, 1),
    "z270": (0, -1, 0, 1, 0, 0, 0, 0, 1),
}


def mat_mul(a, b):
    return tuple(sum(a[r * 3 + k] * b[k * 3 + c] for k in range(3))
                 for r in range(3) for c in range(3))


def mat_apply(m, v):
    return tuple(m[r * 3] * v[0] + m[r * 3 + 1] * v[1] + m[r * 3 + 2] * v[2]
                 for r in range(3))


# pièce -> (taille LDU, couleur par défaut, connecteurs locaux)
# connecteur = (nom, position locale, normale sortante)
PARTS = {
    "3005": ((20, 24, 20), "15", [
        ("top", (0, 0, 0), (0, -1, 0)),
        ("bottom", (0, 24, 0), (0, 1, 0)),
    ]),
    "3004": ((40, 24, 20), "15", [
        ("top0", (-10, 0, 0), (0, -1, 0)),
        ("top1", (10, 0, 0), (0, -1, 0)),
        ("bottom", (0, 24, 0), (0, 1, 0)),
    ]),
    "4070": ((20, 24, 20), "4", [           # headlight brick 1x1, stud +X
        ("top", (0, 0, 0), (0, -1, 0)),
        ("bottom", (0, 24, 0), (0, 1, 0)),
        ("side", (10, 12, 0), (1, 0, 0)),
    ]),
}


@dataclass
class Item:
    part: str
    pos: tuple
    rot: tuple = IDENT
    color: str = ""
    connectors: list = field(default_factory=list)  # (nom, world, normal, item)

    def box(self):
        sx, sy, sz = PARTS[self.part][0]
        pts = []
        for (x, y, z) in itertools.product((-sx / 2, sx / 2),
                                           (0, sy), (-sz / 2, sz / 2)):
            pts.append(mat_apply(self.rot, (x, y, z)))
        lo = tuple(self.pos[i] + min(p[i] for p in pts) for i in range(3))
        hi = tuple(self.pos[i] + max(p[i] for p in pts) for i in range(3))
        return lo, hi


class SnotScene:
    def __init__(self):
        self.items: list[Item] = []

    def _world_connectors(self, item: Item):
        out = []
        for name, local, normal in PARTS[item.part][2]:
            p = mat_apply(item.rot, local)
            n = mat_apply(item.rot, normal)
            out.append((name, tuple(item.pos[i] + p[i] for i in range(3)),
                        n, item))
        return out

    def _collides(self, item: Item) -> bool:
        lo, hi = item.box()
        for other in self.items:
            olo, ohi = other.box()
            if all(lo[i] < ohi[i] - 1e-6 and olo[i] < hi[i] - 1e-6
                   for i in range(3)):
                return True
        return False

    def add(self, part: str, pos, rot=IDENT, color: str = "") -> Item:
        if part not in PARTS:
            raise ValueError(f"pièce SNOT inconnue {part!r}")
        item = Item(part, tuple(pos), tuple(rot),
                    color or PARTS[part][1])
        if self._collides(item):
            raise ValueError(f"collision pour {part} en {pos}")
        item.connectors = self._world_connectors(item)
        self.items.append(item)
        return item

    def attach(self, part: str, to: Item, connector: str = "top",
               color: str = "") -> Item:
        """Attache `part` par son connecteur `bottom` au connecteur cible.

        Le connecteur du dessous de la nouvelle pièce doit être **opposé**
        à la normale du connecteur cible ; on essaie les rotations 90°.
        """
        target = next((c for c in self._world_connectors(to)
                       if c[0] == connector), None)
        if target is None:
            raise ValueError(f"connecteur {connector!r} absent")
        _, tpos, tnormal, _ = target
        bottom = next(c for c in PARTS[part][2] if c[0] == "bottom")
        local_n = bottom[2]
        local_p = bottom[1]
        for rname, r in ROT.items():
            if tuple(round(v, 6) for v in mat_apply(r, local_n)) != \
                    tuple(round(-v, 6) for v in tnormal):
                continue
            rp = mat_apply(r, local_p)
            pos = tuple(tpos[i] - rp[i] for i in range(3))
            try:
                return self.add(part, pos, r, color)
            except ValueError:
                continue
        raise ValueError("aucune orientation ne tient (collision)")

    def connected(self) -> bool:
        """Toutes les pièces sont-elles reliées par un connecteur ?"""
        if not self.items:
            return True
        # graphe : connecteurs confondus à moins d'1 LDU
        adj = {id(it): set() for it in self.items}
        allc = [c for it in self.items for c in self._world_connectors(it)]
        for i, a in enumerate(allc):
            for b in allc[i + 1:]:
                if a[3] is b[3]:
                    continue
                d = math.dist(a[1], b[1])
                if d < 1.0:
                    adj[id(a[3])].add(id(b[3]))
                    adj[id(b[3])].add(id(a[3]))
        seen = set()
        stack = [id(self.items[0])]
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            stack.extend(adj[k] - seen)
        return len(seen) == len(self.items)

    def to_ldraw(self, name: str = "snot_demo") -> str:
        lines = [f"0 {name}", f"0 Name: {name}.ldr",
                 "0 Author: legoCAD SNOT", "0 BFC CERTIFY CCW", ""]
        for it in self.items:
            r = it.rot
            mat = " ".join(f"{v:g}" for v in r)
            lines.append(f"1 {it.color} {it.pos[0]:g} {it.pos[1]:g} "
                         f"{it.pos[2]:g} {mat} {it.part}.dat")
        return "\n".join(lines) + "\n"

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_ldraw(path.stem))
        return path


def demo() -> SnotScene:
    """Petit vaisseau : brique de base, brique dessus, headlight + aile SNOT."""
    s = SnotScene()
    base = s.add("3004", (0, 0, 0), color="15")
    top = s.attach("3004", base, "top0", color="15")
    head = s.attach("4070", top, "top0", color="4")
    # aile attachée au stud latéral du headlight brick
    s.attach("3005", head, "side", color="1")
    # un plot sur le dessus de l'aile
    return s


def main():
    ap = argparse.ArgumentParser(description="démo SNOT 3D")
    ap.add_argument("--out", default=str(PROJECT / "out" / "snot_demo.ldr"))
    args = ap.parse_args()
    scene = demo()
    path = scene.save(args.out)
    print(path, f"{len(scene.items)} pièces",
          "connecté" if scene.connected() else "NON connecté")


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------- #
# Détails SNOT réels, attachés à un modèle compilé
# --------------------------------------------------------------------------- #
# Le compilateur volumique pose la masse principale. Cette couche ajoute des
# pièces **extérieures** réellement tenues par un tenon latéral :
#
#   brique 4070 (tenon sur le côté)  ->  plaque 1x2 verticale (bannière)
#
# La plaque est attachée par son dessous au tenon latéral ; elle n'a aucun
# appui vertical, ce qui est exactement le cas que la grille ne sait pas
# représenter. On valide donc : (1) remplacement d'une brique de mur par une
# 4070 de même empreinte, (2) collision de la bannière avec la grille,
# (3) export LDraw avec matrice complète.

# matrice de la plaque 1x2 verticale quand le tenon pointe vers -z
_BANNER_M = (0, 0, 1, -1, 0, 0, 0, 1, 0)
_SIDE_ROT = {"+x": 0, "-z": 90, "-x": 180, "+z": 270}
_SIDE_DIR = {"+x": (1, 0), "-z": (0, -1), "-x": (-1, 0), "+z": (0, 1)}
_OUT = {"+x": (1, 0), "-z": (0, -1), "-x": (-1, 0), "+z": (0, 1)}


def _rot_y(angle: int):
    c = int(round(math.cos(math.radians(angle))))
    s = int(round(math.sin(math.radians(angle))))
    return (c, 0, s, 0, 1, 0, -s, 0, c)


def _brick_ldu_center(model, b: dict) -> tuple[float, float, float]:
    """Centre LDraw d'une pièce posée sur la grille (même formule que l'export)."""
    from ldraw_model import STUD, LDU_PER_LEVEL, part_levels
    part = model.part(b["part_id"])
    sx, sz = model._footprint(part, b["rot"])
    cx = (b["x"] + sx / 2.0 - 0.5) * STUD
    cz = (b["z"] + sz / 2.0 - 0.5) * STUD
    cy = -(b["y"] * LDU_PER_LEVEL) - part_levels(part) * LDU_PER_LEVEL / 2.0
    return cx, cy, cz


_LONG_BRICKS = {"3004": 2, "3622": 3, "3010": 4, "3009": 6, "3008": 8}
_FILL_BRICKS = {1: "3005", 2: "3004", 3: "3622", 4: "3010",
                6: "3009", 8: "3008"}


def _refill(model, cells, y, color, rot) -> bool:
    """Re-pave une rangée de briques 1×N après retrait d'une cellule."""
    todo = list(cells)
    while todo:
        n = len(todo)
        for L in (6, 4, 3, 2, 1):
            if L <= n and L in _FILL_BRICKS:
                if model.try_place(_FILL_BRICKS[L], todo[0][0], todo[0][1],
                                   y, color, rot):
                    todo = todo[L:]
                    break
        else:
            return False
    return True


def add_banner(model, brick_index: int, side: str, color: str = "4",
               banner_color: str = "4") -> bool:
    """Remplace une brique 1×N de mur par 4070 + 1×N et attache une bannière.

    `side` est la direction **sortante** du mur ("+x", "-x", "+z", "-z").
    Retourne True si la bannière a été posée et validée. Les briques 1×2 à
    1×8 sont acceptées : on garde la longueur du pan en re-pavant le reste,
    donc un mur appareillé fournit toujours des ancrages.
    """
    from ldraw_model import part_levels
    b = model.bricks[brick_index]
    part = model.part(b["part_id"])
    n = _LONG_BRICKS.get(str(b["part_id"]))
    if not n or part_levels(part) != 3:
        return False
    sx, sz = model._footprint(part, b["rot"])
    if max(sx, sz) != n or min(sx, sz) != 1:
        return False
    cells = [(b["x"] + i, b["z"] + j)
             for i in range(sx) for j in range(sz)]
    dx, dz = _OUT[side]
    anchor = None
    for (ax, az) in cells:
        ox, oz = ax + dx, az + dz
        levels = range(b["y"] - 1, b["y"] + 4)
        if any((ox, yy, oz) in model._occupied for yy in levels):
            continue
        anchor = (ax, az)
        break
    if anchor is None:
        return False
    ax, az = anchor
    rest = [c for c in cells if c != anchor]
    color = str(b["color"])
    rot = b["rot"]
    model.remove(brick_index)
    if not model.try_place("4070", ax, az, b["y"], color,
                           _SIDE_ROT[side]):
        model.try_place(b["part_id"], b["x"], b["z"], b["y"], color, rot)
        return False
    placed_before = len(model.bricks)
    # le reste du pan est re-pavé dans le même sens
    rest.sort(key=lambda c: (c[0], c[1]))
    if rest and not _refill(model, rest, b["y"], color, rot):
        del model.bricks[placed_before - 1:]
        model._rebuild_occupied()
        model.try_place(b["part_id"], b["x"], b["z"], b["y"], color, rot)
        return False
    # bannière : origine de la plaque à 8 LDU devant la face du tenon
    idx4070 = None
    for i in range(len(model.bricks) - 1, -1, -1):
        bb = model.bricks[i]
        if bb["part_id"] == "4070" and bb["x"] == ax and bb["z"] == az:
            idx4070 = i
            break
    cx, cy, cz = _brick_ldu_center(model, model.bricks[idx4070])
    fx, fz = _SIDE_DIR[side]
    ox_ldu = cx + fx * 18.0
    oz_ldu = cz + fz * 18.0
    angle = {"-z": 0, "+x": -90, "+z": 180, "-x": 90}[side]
    mat = mat_mul(_rot_y(angle), _BANNER_M)
    model.add_extra("3023", (ox_ldu, cy, oz_ldu), mat, banner_color)
    return True


def decorate_wall_banners(model, max_banners: int = 6,
                          color: str = "4",
                          banner_color: str = "4") -> int:
    """Pose des bannières SNOT sur les **murs extérieurs**, espacées.

    Choisit des briques 1x2 de l'enceinte extérieure (pas les murs de cour),
    orientées vers l'extérieur, remplace une cellule par une 4070 et attache
    la plaque. Les briques sont relues après chaque pose : `remove()` décale
    les indices, donc on ne garde pas d'indices obsolètes.
    """
    from ldraw_model import part_levels
    if not model.bricks:
        return 0
    xs = [b["x"] for b in model.bricks]
    zs = [b["z"] for b in model.bricks]
    xmin, xmax = min(xs), max(xs)
    zmin, zmax = min(zs), max(zs)
    placed: list[tuple[int, int]] = []
    tried: set[tuple[int, int, int]] = set()
    count = 0
    while count < max_banners:
        candidates = []
        for i, b in enumerate(model.bricks):
            if str(b["part_id"]) not in _LONG_BRICKS:
                continue
            if part_levels(model.part(b["part_id"])) != 3 or b["y"] < 6:
                continue
            key = (b["x"], b["z"], b["y"])
            if key in tried:
                continue
            sx, sz = model._footprint(model.part(b["part_id"]), b["rot"])
            if any(abs(b["x"] - px) < 3 and abs(b["z"] - pz) < 3
                   for (px, pz) in placed):
                continue
            # côté extérieur = côté du mur de périmètre
            if sx >= sz:
                side = "-z" if b["z"] <= zmin + 3 else (
                    "+z" if b["z"] >= zmax - 3 else None)
            else:
                side = "-x" if b["x"] <= xmin + 3 else (
                    "+x" if b["x"] >= xmax - 3 else None)
            if side is None:
                continue
            candidates.append((i, side))
        if not candidates:
            break
        i, side = candidates[0]
        b = model.bricks[i]
        key = (b["x"], b["z"], b["y"])
        if add_banner(model, i, side, color, banner_color):
            placed.append((b["x"], b["z"]))
            count += 1
        tried.add(key)
    return count
