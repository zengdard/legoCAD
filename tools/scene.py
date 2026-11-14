#!/usr/bin/env python3
"""Composeur de scènes / dioramas (mode « Set » de BrickBench).

Un diorama n'est pas un objet unique : c'est un **socle**, un sol qui raconte
le lieu, un ou deux volumes bâtis, des props et des figures. Ce module fournit
ces briques de composition, toutes en voxels (1 stud × 1 plaque), donc
directement compilables par `brickify` :

    s = Scene(32, ground=GREEN)
    s.path(14, 0, 4, 32, "19")
    s.cottage(2, 2, 10, 7, TAN, DARKRED)
    s.figure(15, 9, RED, BROWN)
    grid = s.build()          # miroir z + normalisation

Les helpers sont aussi appelables directement sur une `VoxelGrid` :

    g = VoxelGrid(); ...
    cottage(g, x, z, w, d, wall, roof)
"""
from __future__ import annotations

from voxel import VoxelGrid

# palette (codes LDraw)
RED, WHITE, BLACK, YELLOW = "4", "15", "0", "14"
BLUE, GREEN, ORANGE, BROWN = "1", "2", "25", "70"
TAN, LGRAY, DGRAY = "19", "71", "72"
DARKRED, DARKBLUE, DARKGREEN = "320", "272", "288"
LBLUE = "43"

GROUND = GREEN


def cottage(g: VoxelGrid, x: int, z: int, w: int, d: int, wall: str,
            roof: str, y0: int = 3) -> None:
    """Petite maison de scène : murs pleins, porte, fenêtres, toit à pans."""
    h = 9
    g.box(x, y0, z, w, h, d, wall)
    g.paint_box(x, y0, z, w, 2, d, DGRAY)
    dx = x + w // 2 - 1
    g.paint_box(dx - 1, y0, z, 4, 7, 1, "0")
    g.paint_box(dx, y0, z, 2, 6, 1, BROWN)
    g.paint_box(dx, y0 + 2, z, 1, 1, 1, YELLOW)
    for wx in (x + 2, x + w - 4):
        for face in (z, z + d - 1):
            g.paint_box(wx - 1, y0 + 2, face, 4, 4, 1, "0")
            g.paint_box(wx, y0 + 3, face, 2, 3, 1, LBLUE)
    y = y0 + h
    step = 0
    while d - 4 * step >= 2:
        g.box(x, y, z + 2 * step, w, 3, d - 4 * step, roof)
        g.paint_box(x, y, z + 2 * step, 1, 3, d - 4 * step, wall)
        g.paint_box(x + w - 1, y, z + 2 * step, 1, 3, d - 4 * step, wall)
        y += 3
        step += 1
    g.box(x, y, z + d // 2 - 1, w, 1, 2, "0")
    cx = x + w - 3
    g.box(cx, y0 + h - 2, z + 2, 2, 10, 2, DGRAY)
    g.box(cx - 1, y0 + h + 8, z + 1, 3, 1, 3, "0")


def figure(g: VoxelGrid, x: int, z: int, torso: str = RED,
           hair: str = BROWN, y0: int = 3) -> None:
    """Personnage brick-built 4 studs : jambes, épaules, tête, visage, mains."""
    g.box(x + 1, y0, z, 2, 3, 2, "0")              # jambes
    g.box(x, y0 + 3, z, 4, 3, 2, torso)            # torse + épaules
    g.paint_box(x, y0 + 4, z, 1, 1, 2, YELLOW)     # mains
    g.paint_box(x + 3, y0 + 4, z, 1, 1, 2, YELLOW)
    g.box(x + 1, y0 + 6, z, 2, 3, 2, YELLOW)       # tête
    g.box(x + 1, y0 + 9, z, 2, 1, 2, hair)         # cheveux
    g.paint_box(x + 1, y0 + 7, z, 1, 1, 1, "0")    # yeux
    g.paint_box(x + 2, y0 + 7, z, 1, 1, 1, "0")
    g.paint_box(x + 1, y0 + 6, z, 2, 1, 1, DARKRED)  # bouche


def tree(g: VoxelGrid, x: int, z: int, trunk: int = 6,
         r: float = 2.4, y0: int = 3) -> None:
    g.box(x, y0, z, 2, trunk, 2, BROWN)
    g.ellipsoid(x + 0.5, y0 + trunk + 2, z + 0.5, r, r, r, DARKGREEN)
    g.ellipsoid(x + 0.5, y0 + trunk + 3, z + 0.5, r * 0.66, r * 0.66,
                r * 0.66, GREEN)


def pond(g: VoxelGrid, x: int, z: int, w: int = 7, d: int = 7,
         y: int = 2) -> None:
    g.paint_box(x, y, z, w, 1, d, DGRAY)
    g.paint_box(x + 1, y, z + 1, w - 2, 1, d - 2, LBLUE)
    g.box(x + w // 2 - 1, y + 1, z + d // 2 - 1, 2, 3, 2, DGRAY)
    g.box(x + w // 2, y + 4, z + d // 2, 1, 3, 1, LBLUE)


def stall(g: VoxelGrid, x: int, z: int, awning: str = RED,
          y0: int = 3) -> None:
    g.box(x, y0, z, 3, 1, 2, BROWN)
    for (mx, mz) in ((x, z), (x + 2, z), (x, z + 1), (x + 2, z + 1)):
        g.box(mx, y0 + 1, mz, 1, 4, 1, BROWN)
    g.box(x, y0 + 5, z, 3, 1, 2, awning)


def barrel(g: VoxelGrid, x: int, z: int, y0: int = 3) -> None:
    g.box(x, y0, z, 2, 3, 2, BROWN)
    g.paint_box(x, y0 + 1, z, 2, 1, 2, DGRAY)


def lamp(g: VoxelGrid, x: int, z: int, y0: int = 3) -> None:
    g.box(x, y0, z, 1, 6, 1, "0")
    g.box(x, y0 + 6, z, 1, 1, 1, YELLOW)


def back_wall(g: VoxelGrid, size: int, y0: int = 3, z: int | None = None,
              gate_color: str = BROWN) -> None:
    z = size - 1 if z is None else z
    g.box(0, y0, z, size, 6, 1, LGRAY)
    g.paint_box(0, y0, z, size, 2, 1, DGRAY)
    g.paint_box(size // 2 - 2, y0, z, 4, 5, 1, gate_color)
    for x in range(0, size, 2):
        g.box(x, y0 + 6, z, 1, 3, 1, LGRAY)


class Scene:
    """Composeur : sol + modules, puis `build()` renvoie la grille."""

    def __init__(self, size: int = 32, ground: str = GROUND):
        self.size = size
        self.g = VoxelGrid()
        self.g.box(0, 0, 0, size, 3, size, ground)

    def rect(self, x: int, z: int, w: int, d: int, color: str,
             y: int = 2) -> "Scene":
        self.g.paint_box(x, y, z, w, 1, d, color)
        return self

    def path(self, x: int, z: int, w: int, d: int, color: str = TAN) -> "Scene":
        return self.rect(x, z, w, d, color)

    def cottage(self, *a, **kw) -> "Scene":
        cottage(self.g, *a, **kw)
        return self

    def figure(self, *a, **kw) -> "Scene":
        figure(self.g, *a, **kw)
        return self

    def tree(self, *a, **kw) -> "Scene":
        tree(self.g, *a, **kw)
        return self

    def pond(self, *a, **kw) -> "Scene":
        pond(self.g, *a, **kw)
        return self

    def stall(self, *a, **kw) -> "Scene":
        stall(self.g, *a, **kw)
        return self

    def barrel(self, *a, **kw) -> "Scene":
        barrel(self.g, *a, **kw)
        return self

    def lamp(self, *a, **kw) -> "Scene":
        lamp(self.g, *a, **kw)
        return self

    def wall(self, *a, **kw) -> "Scene":
        back_wall(self.g, *a, **kw)
        return self

    def merge(self, grid: VoxelGrid, x: int = 0, z: int = 0,
              y: int = 0) -> "Scene":
        for (vx, vy, vz), c in grid.cells.items():
            self.g.add(vx + x, vy + y, vz + z, c)
        return self

    def build(self, mirror: bool = True) -> VoxelGrid:
        g = self.g
        if mirror:
            g = VoxelGrid({(x, y, self.size - 1 - z): c
                           for (x, y, z), c in g.cells.items()})
        return g.normalize()


def village(size: int = 32) -> VoxelGrid:
    """Le village de démonstration, composé avec l'API `Scene`."""
    s = Scene(size)
    s.rect(0, 0, size, 1, DGRAY).rect(0, size - 1, size, 1, DGRAY)
    s.path(14, 0, 4, size, "19")
    s.path(2, 10, 28, 8, "19")
    s.path(4, 2, 3, 8, "19")
    s.path(23, 2, 3, 8, "19")
    s.cottage(2, 2, 10, 7, TAN, DARKRED)
    s.cottage(20, 2, 9, 7, WHITE, DARKBLUE)
    s.pond(20, 21, 7, 7)
    s.tree(2, 23).tree(9, 27)
    s.stall(24, 13, RED)
    for (bx, bz) in ((30, 16), (30, 18)):
        s.barrel(bx, bz)
    s.figure(15, 9, RED, BROWN)
    s.figure(17, 14, BLUE, YELLOW)
    s.figure(19, 27, GREEN, "0")
    s.wall(size)
    for x in range(2, size - 2, 3):
        s.g.box(x, 3, size - 2, 2, 2, 1, DARKGREEN)
        s.g.paint_box(x, 4, size - 2, 1, 1, 1, RED)
    for (lx, lz) in ((12, 6), (18, 7), (12, 20), (18, 21)):
        s.lamp(lx, lz)
    for (fx, fz) in ((4, 1), (8, 1), (22, 1), (26, 1)):
        s.g.box(fx, 3, fz, 3, 1, 1, BROWN)
        s.g.paint_box(fx, 4, fz, 3, 1, 1, RED)
        s.g.paint_box(fx + 1, 4, fz, 1, 1, 1, YELLOW)
    # charrette
    s.g.box(28, 3, 12, 3, 1, 2, BROWN)
    for (wx, wz) in ((28, 12), (30, 12), (28, 13), (30, 13)):
        s.g.box(wx, 2, wz, 1, 1, 1, "0")
    return s.build()
