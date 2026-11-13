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

Il n'est **pas encore branché** au compilateur volumique : c'est la brique de
base pour y ajouter le SNOT (BrickNet : stud / hinge / axle / ball / fixed).

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
