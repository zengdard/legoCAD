#!/usr/bin/env python3
"""Formes procédurales de démonstration : des volumes reconnaissables, sans LLM.

Ce module sert de « bibliothèque de départs » et de banc d'essai pour le
compilateur `brickify` : maisons, fusée, canard, voiture, arbre, mosaïque.
Chaque forme est un `VoxelGrid` (1 voxel = 1 stud × 1 plaque), donc
directement compilable en briques constructibles.

Pour un vrai pipeline texte → LEGO, le LLM écrit plutôt un petit programme
qui utilise les mêmes primitives (boîte, ellipsoïde, cylindre, cône,
peinture) : c'est le mode « structure-as-code » de BrickWright, plus fiable
que de demander au modèle de placer des briques une par une.

    python3 tools/shapes.py --list
    python3 tools/shapes.py house --out models/maison.vox.json
"""
from __future__ import annotations

import math
from pathlib import Path

from voxel import VoxelGrid, nearest_color

# palette de travail (codes LDraw courants dans les sets)
RED, WHITE, BLACK, YELLOW = "4", "15", "0", "14"
BLUE, GREEN, ORANGE, BROWN = "1", "2", "25", "70"
TAN, LGRAY, DGRAY = "19", "71", "72"
DARKRED, DARKBLUE, DARKGREEN = "320", "272", "288"
LBLUE = "43"      # trans light blue (vitrage)
LIME = "27"


def house(width: int = 16, depth: int = 12, levels: int = 3,
          wall: str = TAN, roof: str = DARKRED) -> VoxelGrid:
    """Maison à toit à deux pans, posée sur une plaque de présentation.

    La géométrie est volontairement **pleine** (pas de pièce vide) : un
    volume creux avec un plafond large ne peut pas être construit sans
    poutres, et le compilateur refuserait les pièces non attachées.
    """
    h = levels * 3
    g = VoxelGrid().box(0, 0, 0, width, h, depth, wall)
    # toit à deux pans : 1 brique de hauteur tous les 2 studs (≈ 40°)
    for x in range(width):
        for z in range(depth):
            rise = ((min(z, depth - 1 - z) // 2) * 3)
            for y in range(h, h + rise):
                g.add(x, y, z, roof)
    # porte et fenêtres sur les deux faces avant/arrière
    dx = width // 2 - 1
    for z in (0, depth - 1):
        g.paint_box(dx, 0, z, 3, 6, 1, BROWN)
    for wx in (2, width - 5):
        for z in (0, depth - 1):
            g.paint_box(wx, 6, z, 3, 3, 1, LBLUE)
    # cheminée
    cx, cz = width - 4, 2
    rise = (min(cz, depth - 1 - cz) * 3) // 2
    for y in range(h, h + rise + 6):
        g.box(cx, y, cz, 2, 1, 2, DGRAY)
    # plaque de présentation (1 plaque, 1 stud de marge) : le modèle se
    # soulève d'un bloc et le rendu ressemble à un set
    g = g.translate(1, 1, 1)
    g.box(0, 0, 0, width + 2, 1, depth + 2, GREEN)
    return g.normalize()


def rocket(height: int = 26, color: str = WHITE, accent: str = RED) -> VoxelGrid:
    """Fusée : corps cylindrique, nez conique, ailerons, hublot, pas de tir."""
    g = VoxelGrid()
    r = 3.5
    cx = cz = int(r) + 1
    body_h = int(height * 0.72)
    g.cylinder(cx, cz, 0, body_h, r, color)
    g.cone(cx, cz, body_h, height, r, 0.4, accent)
    for sx in (-1, 1):
        g.box(cx + sx * 3, 0, cz - 1, 3, 7, 2, accent)
        g.box(cx - 1, 0, cz + sx * 3, 2, 7, 3, accent)
    g.paint_box(cx - 4, 4, cz - 4, 9, 2, 9, accent)
    # hublot sur les deux faces visibles
    for z in (cz - 4, cz + 2):
        g.paint_box(cx - 1, body_h - 8, z, 3, 3, 3, LBLUE)
    # pas de tir (1 plaque) : relie les ailerons et stabilise le modèle
    g = g.translate(1, 1, 1)
    g.box(0, 0, 0, cx * 2 + 3, 1, cz * 2 + 3, DGRAY)
    return g.normalize()


DUCK_ART = [
    "................",
    ".....YYYYY......",
    "....YYYYYYY.....",
    "...YYYYYYYYY....",
    "...YYKYYYYYY....",
    "..YYYYYYYYYYOO..",
    "..YYYYYYYYYYOO..",
    "...YYYYYYYYY....",
    "....YYYYYY......",
    ".....YYYY.......",
]


def duck(body: str = YELLOW, beak: str = ORANGE) -> VoxelGrid:
    """Canard en mosaïque : un « tableau » LEGO posé sur un fond de briques.

    Une mosaïque est le projet réel le plus simple : peu de pièces
    différentes, une notice courte, un résultat immédiatement
    reconnaissable. Le fond de 3 plaques est indispensable : des plaques
    côte à côte ne sont pas attachées, alors qu'un appareillage de briques
    forme un seul bloc.
    """
    pal = {"Y": body, "O": beak, "K": BLACK, "B": BLUE}
    w = max(len(row) for row in DUCK_ART)
    h = len(DUCK_ART)
    g = VoxelGrid()
    g.box(0, 0, 0, w, 3, h, DGRAY)               # fond de 3 plaques
    for z, row in enumerate(DUCK_ART):
        for x, ch in enumerate(row):
            if ch in pal:
                g.add(x, 3, z, pal[ch])
    return g.normalize()


def car(body: str = RED, glass: str = LBLUE) -> VoxelGrid:
    """Voiture : masse pleine (châssis + habitacle), vitres et passages de roue
    peints. Une voiture creuse avec des roues séparées ne serait pas stable :
    la carrosserie doit reposer sur un châssis continu."""
    g = VoxelGrid()
    g.box(0, 0, 0, 18, 8, 8, body)            # châssis + carrosserie
    g.box(4, 8, 1, 9, 3, 6, body)             # habitacle (3 plaques : pentes)
    g.paint_box(4, 9, 0, 3, 2, 1, glass)      # pare-brise avant
    g.paint_box(10, 9, 7, 3, 2, 1, glass)
    g.paint_box(4, 9, 1, 1, 2, 5, glass)      # vitres latérales
    g.paint_box(12, 9, 1, 1, 2, 5, glass)
    for x in (2, 13):
        for z in (0, 7):
            g.paint_box(x, 0, z, 3, 3, 1, BLACK)   # passages de roue
    g.paint_box(0, 3, 0, 1, 2, 8, DGRAY)      # pare-chocs
    g.paint_box(17, 3, 0, 1, 2, 8, DGRAY)
    g.paint_box(0, 0, 2, 1, 1, 4, BLACK)
    g.paint_box(17, 0, 2, 1, 1, 4, BLACK)
    return g.normalize()


def tree(trunk_h: int = 10, foliage_r: float = 6.0) -> VoxelGrid:
    """Sapin : cône plein posé au sol, avec bands de couleur et un tronc peint.

    Un feuillage qui s'élargit vers le haut ne peut pas être construit sans
    branches (porte-à-faux) : le cône qui s'élargit vers le bas est la forme
    réelle la plus simple, et elle est constructible à 100 %."""
    g = VoxelGrid()
    cx = cz = int(foliage_r) + 1
    top = trunk_h + int(foliage_r) * 2
    g.cone(cx, cz, 0, top, foliage_r, 0.8, DARKGREEN)
    # bands décoratives (peinture, pas de géométrie)
    for y in range(2, top, 4):
        g.paint_box(cx - int(foliage_r), y, cz - int(foliage_r),
                    2 * int(foliage_r) + 1, 1, 2 * int(foliage_r) + 1, GREEN)
    # tronc visible sur la face avant, à la base
    g.paint_box(cx - 1, 0, cz - int(foliage_r), 2, trunk_h, 1, BROWN)
    g.paint_box(cx - 1, 0, cz + int(foliage_r), 2, trunk_h, 1, BROWN)
    return g.normalize()


def spaceship(body: str = LGRAY, wing: str = BLUE,
              canopy: str = "46", accent: str = BLACK) -> VoxelGrid:
    """Vaisseau Classic Space (inspiré des sets 6801/6929) : fuselage gris,
    ailes bleues, verrière trans-jaune, réacteurs, antenne, logo.

    Les ailes sont tenues par des pylônes verticaux (une aile en porte-à-faux
    de 4 studs ne serait pas constructible) et les réacteurs chevauchent la
    queue : tout le volume est relié.
    """
    g = VoxelGrid()
    # fuselage central
    g.box(6, 3, 3, 8, 6, 12, body)
    # nez (chevauche le fuselage pour être attaché)
    g.box(7, 4, 0, 6, 4, 5, body)
    g.box(8, 4, 0, 4, 3, 2, body)
    # pylônes d'aile (du sol jusqu'au niveau de l'aile)
    for x in (4, 14):
        g.box(x, 1, 8, 2, 5, 5, wing)
    # ailes
    g.box(2, 5, 8, 4, 2, 5, wing)
    g.box(14, 5, 8, 4, 2, 5, wing)
    g.box(0, 5, 10, 2, 2, 3, wing)
    g.box(18, 5, 10, 2, 2, 3, wing)
    # verrière
    g.box(7, 8, 4, 6, 2, 5, canopy)
    g.box(8, 10, 5, 4, 1, 3, canopy)
    # dérive
    g.box(7, 8, 13, 2, 5, 2, wing)
    # réacteurs (chevauchent la queue)
    for x in (6, 13):
        g.cylinder(x, 15, 3, 6, 1.6, accent)
        g.paint_box(x - 1, 4, 17, 2, 2, 1, "25")
    # antenne
    g.cylinder(8, 13, 9, 15, 0.6, LGRAY)
    # logo Classic Space (planète jaune sur fond bleu)
    for x in (6, 13):
        g.paint_box(x, 5, 6, 1, 4, 4, wing)
        g.paint_box(x, 6, 7, 1, 2, 2, YELLOW)
    # plaque de présentation (3 plaques : c'est un vrai support de briques)
    g.box(0, 0, 0, 22, 3, 22, DGRAY)
    return g.normalize()


def castle(size: int = 26, wall_h: int = 9, color: str = LGRAY,
           stone: str = DGRAY, roof: str = DARKBLUE) -> VoxelGrid:
    """Château fort : enceinte crénelée, tours d'angle, donjon, porte et douve.

    Le château est **plein** (pas de plafond suspendu) : les murs, tours et
    donjon reposent sur une plateforme de 3 plaques. Les merlons sont des
    colonnes de 3 plaques sur le chemin de ronde ; les toits des tours sont
    des pyramides étagées (chaque niveau repose sur le précédent), donc
    constructibles et compatibles avec la passe de pentes.
    """
    g = VoxelGrid()
    g.box(0, 0, 0, size, 3, size, stone)          # plateforme
    # douve peinte sur le pourtour de la plateforme
    g.paint_box(0, 2, 0, 2, 1, size, BLUE)
    g.paint_box(size - 2, 2, 0, 2, 1, size, BLUE)
    g.paint_box(2, 2, 0, size - 4, 1, 2, BLUE)
    g.paint_box(2, 2, size - 2, size - 4, 1, 2, BLUE)

    x0, z0 = 2, 2
    x1, z1 = size - 3, size - 3
    # enceinte (1 stud d'épaisseur)
    g.box(x0, 3, z0, size - 4, wall_h, 1, color)
    g.box(x0, 3, z1, size - 4, wall_h, 1, color)
    g.box(x0, 3, z0 + 1, 1, wall_h, size - 6, color)
    g.box(x1, 3, z0 + 1, 1, wall_h, size - 6, color)
    # porte fermée : le mur reste plein (un trou de 3 studs exigerait un
    # linteau porteur que le tiler ne garantit pas toujours) ; la porte est
    # peinte sur la façade, avec un encadrement sombre.
    gate_x = size // 2 - 1
    g.paint_box(gate_x - 1, 2, z0, 5, 8, 1, DGRAY)   # encadrement
    g.paint_box(gate_x, 3, z0, 3, 6, 1, BROWN)      # porte
    g.box(gate_x, 3, 0, 3, 1, 3, BROWN)             # pont-levis
    # tours d'angle (5x5), toits pyramidaux
    towers = ((0, 0), (size - 5, 0), (0, size - 5), (size - 5, size - 5))
    for (tx, tz) in towers:
        g.box(tx, 3, tz, 5, 18, 5, color)
        _castle_pyramid(g, tx + 2, tz + 2, 5, 21, roof)
        # meurtrières
        for (wx, wz) in ((tx + 1, tz), (tx + 4, tz), (tx + 1, tz + 4),
                         (tx + 4, tz + 4)):
            g.paint_box(wx, 9, wz, 1, 3, 1, "0")
    # tours de porte (4x4)
    for tx in (size // 2 - 5, size // 2 + 2):
        g.box(tx, 3, 0, 4, 15, 4, color)
        _castle_crenellate(g, tx, 0, 4, 4, 18, color)
    # donjon central 8x8
    kx = kz = size // 2 - 4
    g.box(kx, 3, kz, 8, 21, 8, color)
    _castle_crenellate(g, kx, kz, 8, 8, 24, color)
    # mâts + drapeau sur le donjon
    pole_x, pole_z = kx + 3, kz + 3
    g.box(pole_x, 24, pole_z, 2, 8, 1, DGRAY)      # mât 1x2 (2 appuis)
    g.box(pole_x, 31, pole_z, 3, 1, 2, RED)        # drapeau 3x2
    g.paint_box(pole_x + 1, 31, pole_z + 1, 1, 1, 1, YELLOW)
    # crénelations de l'enceinte (merlons d'un stud)
    _castle_crenellate(g, x0, z0, size - 4, size - 4, 3 + wall_h, color)
    return g.normalize()


def _castle_crenellate(g: VoxelGrid, x: int, z: int, w: int, d: int,
                       y: int, color: str) -> None:
    """Merlons d'un stud sur le périmètre (un sur deux), 3 plaques de haut."""
    for i in range(0, w, 2):
        g.box(x + i, y, z, 1, 3, 1, color)
        g.box(x + i, y, z + d - 1, 1, 3, 1, color)
    for j in range(1, d - 1, 2):
        g.box(x, y, z + j, 1, 3, 1, color)
        g.box(x + w - 1, y, z + j, 1, 3, 1, color)


def _castle_pyramid(g: VoxelGrid, cx: int, cz: int, size: int, y: int,
                    color: str) -> None:
    """Toit pyramidal étagé : chaque niveau est un sous-ensemble du précédent."""
    s = size
    while s > 0:
        g.box(cx - s // 2, y, cz - s // 2, s, 3, s, color)
        y += 3
        s -= 2


def brick(width: int = 4, depth: int = 2) -> VoxelGrid:
    """Une brique géante (démo minimale)."""
    return VoxelGrid().box(0, 0, 0, width, 3, depth, RED)


def mosaic(image: str | Path, max_width: int = 48,
           depth: int = 1) -> VoxelGrid:
    """Photo → mosaïque LEGO : un fond de briques + une couche de plaques.

    Le fond (3 plaques) est un appareillage de briques qui rend la mosaïque
    soulevable ; les pixels colorés sont posés dessus. `depth` ajoute des
    pixels en épaisseur (1 par défaut, comme un tableau).
    """
    from PIL import Image
    im = Image.open(image).convert("RGBA")
    scale = max_width / max(1, im.width)
    w = max(1, round(im.width * scale))
    h = max(1, round(im.height * scale))
    im = im.resize((w, h))
    px = im.load()
    g = VoxelGrid()
    g.box(0, 0, 0, w, 3, h, DGRAY)               # fond constructible
    for yy in range(h):
        for x in range(w):
            r, gg, b, a = px[x, yy]
            if a < 24 or (r + gg + b) > 720:
                continue
            color = nearest_color((r, gg, b))
            for dz in range(depth):
                g.add(x, 3, h - 1 - yy + dz, color)
    return g.normalize()


SHAPES = {
    "house": house,
    "rocket": rocket,
    "duck": duck,
    "car": car,
    "tree": tree,
    "brick": brick,
    "castle": castle,
    "spaceship": spaceship,
    "mosaic": mosaic,
}


def make(name: str, **kwargs) -> VoxelGrid:
    if name not in SHAPES:
        raise ValueError(f"forme inconnue {name!r} (disponibles : "
                         f"{', '.join(sorted(SHAPES))})")
    return SHAPES[name](**kwargs)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="formes de démonstration → voxels")
    ap.add_argument("shape", nargs="?", help="house|rocket|duck|car|tree|brick|mosaic")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--image", help="image source pour la mosaïque")
    ap.add_argument("--out", default=None)
    ap.add_argument("--width", type=int, default=None)
    args = ap.parse_args()
    if args.list or not args.shape:
        print("\n".join(sorted(SHAPES)))
        return
    kwargs = {}
    if args.shape == "mosaic":
        if not args.image:
            raise SystemExit("mosaic nécessite --image")
        kwargs["image"] = args.image
        if args.width:
            kwargs["max_width"] = args.width
    elif args.width:
        key = "width" if args.shape in ("house", "brick") else "height"
        kwargs[key] = args.width
    grid = make(args.shape, **kwargs)
    out = Path(args.out) if args.out else Path("models") / f"{args.shape}.vox.json"
    grid.save(out)
    print(f"{out} : {grid.count()} voxels, taille {grid.size()}")


if __name__ == "__main__":
    main()
