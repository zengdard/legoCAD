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


def house(width: int = 16, depth: int = 12, levels: int = 4,
          wall: str = TAN, roof: str = DARKRED) -> VoxelGrid:
    """Maison détaillée : colombages, fenêtres à volets, porche, cheminée.

    La maison est **pleine** (murs et intérieur), donc chaque détail posé
    au-dessus a un appui. Les éléments qui font la différence à l'œil sont
    les encadrements de fenêtres, les volets, le porche, la cheminée qui
    traverse le toit, la haie fleurie et les arbres du jardin.
    """
    m = 2                                   # marge de jardin
    W, D = width + 2 * m, depth + 2 * m
    h = levels * 3
    g = VoxelGrid()
    g.box(0, 0, 0, W, 3, D, GREEN)          # jardin (3 plaques)
    g.paint_box(0, 2, 0, W, 1, D, GREEN)
    x0, z0 = m, m
    x1, z1 = m + width - 1, m + depth - 1
    g.box(x0, 3, z0, width, h, depth, wall)
    # soubassement de pierre
    g.paint_box(x0, 3, z0, width, 2, depth, DGRAY)
    # colombages : poteaux sombres aux angles et à mi-pan
    for (px, pz) in ((x0, z0), (x1, z0), (x0, z1), (x1, z1),
                     (x0 + width // 2, z0), (x0 + width // 2, z1)):
        g.box(px, 3, pz, 1, h, 1, BROWN)
    for py in (h - 4, h - 3):
        g.paint_box(x0, py, z0, width, 1, 1, BROWN)
        g.paint_box(x0, py, z1, width, 1, 1, BROWN)
        g.paint_box(x0, py, z0, 1, 1, depth, BROWN)
        g.paint_box(x1, py, z0, 1, 1, depth, BROWN)

    def _window(wx, wz, ww, wd, wall_dir):
        """Fenêtre : encadrement, vitre, appui et volets."""
        w, d = (ww, 1) if wall_dir == "z" else (1, ww)
        # encadrement noir 1 stud autour
        g.paint_box(wx - 1, 5, wz - 1, w + 2, 7, d + 2, "0")
        g.paint_box(wx, 6, wz, w, 5, d, LBLUE)
        g.paint_box(wx, 5, wz, w, 1, d, WHITE)          # appui
        if w >= 3:
            g.paint_box(wx + w // 2, 6, wz, 1, 5, d, WHITE)   # meneau
        # volets verts
        if wall_dir == "z":
            g.paint_box(wx - 2, 6, wz, 1, 5, 1, DARKGREEN)
            g.paint_box(wx + w + 1, 6, wz, 1, 5, 1, DARKGREEN)
        else:
            g.paint_box(wx, 6, wz - 2, 1, 5, 1, DARKGREEN)
            g.paint_box(wx, 6, wz + w + 1, 1, 5, 1, DARKGREEN)

    _window(x0 + 3, z0, 3, 1, "z")
    _window(x1 - 5, z0, 3, 1, "z")
    for wx in (x0 + 3, x1 - 5):
        g.box(wx - 1, 3, z0 - 1, 5, 1, 1, BROWN)          # jardinière
        g.paint_box(wx, 4, z0 - 1, 3, 1, 1, RED)
        g.paint_box(wx + 1, 4, z0 - 1, 1, 1, 1, YELLOW)
    _window(x0 + 3, z1, 3, 1, "z")
    _window(x1 - 5, z1, 3, 1, "z")
    _window(x0, z0 + 4, 3, 1, "x")
    _window(x1, z0 + 4, 3, 1, "x")

    # porte + marche + porche (deux poteaux et un auvent)
    dx = x0 + width // 2 - 1
    g.paint_box(dx - 1, 3, z0, 5, 8, 1, "0")
    g.paint_box(dx, 3, z0, 3, 7, 1, BROWN)
    g.paint_box(dx + 1, 6, z0, 1, 1, 1, YELLOW)        # poignée
    g.box(dx - 1, 3, z0 - 1, 5, 1, 1, DGRAY)           # seuil
    for cx in (dx - 1, dx + 3):
        g.box(cx, 3, z0 - 2, 1, 9, 1, WHITE)           # poteaux
    g.box(dx - 2, 12, z0 - 2, 7, 1, 3, roof)           # auvent
    g.paint_box(dx - 2, 10, z0 - 2, 7, 1, 3, roof)

    # toit à deux pans : marches de 2 plaques (pente douce), pignons en
    # couleur murale aux deux extrémités pour que la maison ne soit pas un
    # gros bloc rouge.
    y = h + 3
    step = 0
    # chaque marche recule de 2 studs : la passe de pentes peut alors poser
    # de vraies pentes 45° (2 studs de profondeur, 3 plaques de haut).
    while depth - 4 * step >= 2:
        g.box(x0, y, z0 + 2 * step, width, 3, depth - 4 * step, roof)
        # pignon : la tranche du toit reste en couleur de mur
        g.paint_box(x0, y, z0 + 2 * step, 1, 3, depth - 4 * step, wall)
        g.paint_box(x1, y, z0 + 2 * step, 1, 3, depth - 4 * step, wall)
        y += 3
        step += 1
    # faîtage : 2 studs, une plaque au-dessus du toit
    g.box(x0, y, z0 + depth // 2 - 1, width, 1, 1, DGRAY)
    g.paint_box(x0, y, z0 + depth // 2 - 1, width, 1, 1, DGRAY)

    # cheminée qui traverse le toit
    chx, chz = x0 + width - 4, z0 + 3
    g.box(chx, h - 2, chz, 2, 15, 2, DGRAY)
    g.box(chx - 1, h + 13, chz - 1, 3, 1, 3, "0")
    g.box(chx, h + 14, chz, 2, 1, 2, "0")

    # haie fleurie sur le pourtour du jardin
    for x in range(0, W, 2):
        for z in (0, D - 1):
            g.box(x, 3, z, 2, 2, 1, DARKGREEN)
            if x % 4 == 0:
                g.paint_box(x, 4, z, 1, 1, 1, RED if x % 8 == 0 else YELLOW)
    for z in range(1, D - 1, 2):
        for x in (0, W - 1):
            g.box(x, 3, z, 1, 2, 2, DARKGREEN)
    # chemin dallé de la porte au bord
    g.paint_box(dx - 1, 2, 0, 5, 1, z0, "19")
    g.paint_box(dx - 1, 2, 0, 5, 1, 1, DGRAY)
    # deux arbres d'angle
    for (tx, tz) in ((1, D - 3), (W - 3, D - 3)):
        g.box(tx, 3, tz, 2, 6, 2, BROWN)
        g.ellipsoid(tx + 0.5, 11, tz + 0.5, 2.4, 2.4, 2.4, DARKGREEN)
        g.ellipsoid(tx + 0.5, 12, tz + 0.5, 1.6, 1.6, 1.6, GREEN)
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
    # roues : passage noir, pneu et moyeu clair
    for x in (2, 13):
        for z in (0, 7):
            g.paint_box(x, 0, z, 3, 3, 1, BLACK)
            g.paint_box(x + 1, 1, z, 1, 1, 1, LGRAY)
    g.paint_box(0, 3, 0, 1, 2, 8, DGRAY)      # pare-chocs
    g.paint_box(17, 3, 0, 1, 2, 8, DGRAY)
    # calandre, phares et feux arrière
    g.paint_box(0, 4, 2, 1, 2, 4, "0")
    for z in (1, 6):
        g.paint_box(0, 5, z, 1, 1, 1, YELLOW)
        g.paint_box(17, 5, z, 1, 1, 1, RED)
    # baguette latérale et poignées de porte
    g.paint_box(0, 7, 0, 18, 1, 1, DGRAY)
    g.paint_box(0, 7, 7, 18, 1, 1, DGRAY)
    for x in (6, 9):
        g.paint_box(x, 8, 0, 1, 1, 1, "0")
    # galerie de toit
    for z in (2, 5):
        g.box(5, 11, z, 6, 1, 1, DGRAY)
    for x in (5, 10):
        g.box(x, 11, 2, 1, 1, 4, DGRAY)
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
    # bandes d'identification jaunes et nez noir
    for x in (7, 12):
        g.paint_box(x, 6, 5, 1, 1, 8, YELLOW)
    # trains d'atterrissage : patins sous les pylônes
    for x in (4, 14):
        g.box(x, 0, 7, 2, 1, 3, DGRAY)

    # plaque de présentation (3 plaques : c'est un vrai support de briques)
    g.box(0, 0, 0, 22, 3, 22, DGRAY)
    return g.normalize()


def castle(size: int = 32, wall_h: int = 12, color: str = LGRAY,
           stone: str = DGRAY, roof: str = DARKBLUE,
           trim: str = "0") -> VoxelGrid:
    """Château fort détaillé, posé sur une plaque de base 32x32.

    Le château est **plein** : murs, tours et donjon reposent verticalement
    les uns sur les autres. Les détails ajoutés (mâchicoulis, contreforts,
    hourds, toits coniques) sont eux aussi des volumes supportés, pour que
    le compilateur n'ait jamais à inventer de pièce flottante :

      - douve, cour pavée en damier, chemin dallé ;
      - enceinte à contreforts et bandeau de pierre, meurtrières encadrées ;
      - mâchicoulis en encorbellement (anneau de 2 studs : 1 sur le mur,
        1 en saillie, donc tenu par les pièces qui enjambent) ;
      - tours rondes d'angle à parapet et toit conique étagé ;
      - châtelet à deux tours, porte cochère, pont-levis, chaînes ;
      - donjon à tourelles, fenêtres à meneaux, créneaux ;
      - cour vivante : escalier, puits, étals de marché, tonneaux, bannières.
    """
    g = VoxelGrid()
    m = 4                                   # marge de plateforme / douve
    g.box(0, 0, 0, size, 3, size, stone)
    wall_top = 3 + wall_h

    # ---- douve et sol -------------------------------------------------- #
    g.paint_box(0, 2, 0, 2, 1, size, BLUE)
    g.paint_box(size - 2, 2, 0, 2, 1, size, BLUE)
    g.paint_box(2, 2, 0, size - 4, 1, 2, BLUE)
    g.paint_box(2, 2, size - 2, size - 4, 1, 2, BLUE)
    for x in range(m, size - m, 2):         # dallage de la cour
        for z in range(m, size - m, 2):
            if ((x // 2) + (z // 2)) % 2 == 0:
                g.paint_box(x, 2, z, 2, 1, 2, color)
    g.paint_box(size // 2 - 1, 2, 2, 3, 1, m, "19")   # chemin

    # ---- enceinte ------------------------------------------------------ #
    x0, z0 = m, m
    x1, z1 = size - m - 1, size - m - 1
    span = x1 - x0 + 1
    g.box(x0, 3, z0, span, wall_h, 1, color)
    g.box(x0, 3, z1, span, wall_h, 1, color)
    g.box(x0, 3, z0 + 1, 1, wall_h, span - 2, color)
    g.box(x1, 3, z0 + 1, 1, wall_h, span - 2, color)
    band = 3 + wall_h // 2
    # soubassement plus sombre : lit de pierre visible sur tout le pourtour
    for (bx, bz, bw, bd) in ((x0, z0, span, 1), (x0, z1, span, 1),
                             (x0, z0, 1, span), (x1, z0, 1, span)):
        g.paint_box(bx, 3, bz, bw, 2, bd, stone)
    for (bx, bz, bw, bd) in ((x0, z0, span, 1), (x0, z1, span, 1),
                             (x0, z0, 1, span), (x1, z0, 1, span)):
        g.paint_box(bx, band, bz, bw, 1, bd, stone)

    # contreforts : 2 studs de large, 1 de saillie, à chaque tiers
    def _buttress(bx, bz, bw, bd):
        g.box(bx, 3, bz, bw, wall_h, bd, color)
        g.paint_box(bx, band, bz, bw, 1, bd, stone)

    for i in range(x0 + 4, x1 - 3, 6):
        _buttress(i, z0 - 1, 2, 1)
        _buttress(i, z1 + 1, 2, 1)
    for j in range(z0 + 4, z1 - 3, 6):
        _buttress(x0 - 1, j, 1, 2)
        _buttress(x1 + 1, j, 1, 2)

    # meurtrières : encadrement noir + fente trans bleue, sur les quatre murs
    for wax in range(x0 + 2, x1 - 1, 4):
        for wz in (z0, z1):
            g.paint_box(wax, band + 3, wz, 2, 5, 1, "0")
            g.paint_box(wax, band + 3, wz, 1, 4, 1, LBLUE)
    for waz in range(z0 + 2, z1 - 1, 4):
        for wx in (x0, x1):
            g.paint_box(wx, band + 3, waz, 1, 5, 2, "0")
            g.paint_box(wx, band + 3, waz, 1, 4, 1, LBLUE)

    # mâchicoulis : anneau de 2 studs (mur + saillie), 3 plaques
    g.box(x0 - 1, wall_top, z0 - 1, span + 2, 3, 2, color)
    g.box(x0 - 1, wall_top, z1, span + 2, 3, 2, color)
    g.box(x0 - 1, wall_top, z0 + 1, 2, 3, span - 2, color)
    g.box(x1, wall_top, z0 + 1, 2, 3, span - 2, color)
    # corbeaux peints sous la saillie
    for i in range(x0 - 1, x1 + 2, 2):
        g.paint_box(i, wall_top, z0 - 1, 1, 1, 1, stone)
        g.paint_box(i, wall_top, z1 + 1, 1, 1, 1, stone)
    for j in range(z0, z1 + 1, 2):
        g.paint_box(x0 - 1, wall_top, j, 1, 1, 1, stone)
        g.paint_box(x1 + 1, wall_top, j, 1, 1, 1, stone)
    _castle_crenellate(g, x0 - 1, z0 - 1, span + 2, span + 2,
                       wall_top + 3, color)

    # ---- porte, pont-levis, bannières ---------------------------------- #
    gate_x = size // 2 - 2
    g.paint_box(gate_x - 2, 3, z0, 8, 9, 1, "0")
    g.paint_box(gate_x - 1, 3, z0, 6, 8, 1, stone)
    g.paint_box(gate_x, 3, z0, 4, 7, 1, BROWN)
    g.paint_box(gate_x + 1, 4, z0, 1, 6, 1, "0")
    g.paint_box(gate_x, 3, z0, 4, 1, 1, "0")
    g.box(gate_x, 2, 0, 4, 1, z0, BROWN)              # tablier jusqu'au bord
    for cx in (gate_x, gate_x + 3):
        g.box(cx, 3, 0, 1, 6, 1, "0")                  # chaînes
    for bx in (gate_x - 2, gate_x + 6):
        g.paint_box(bx, 4, z0, 3, 7, 1, DARKRED)
        g.paint_box(bx, 8, z0, 3, 2, 1, YELLOW)
        g.paint_box(bx + 1, 4, z0, 1, 7, 1, WHITE)
    # torches et écus de part et d'autre de la porte
    for tx in (gate_x - 3, gate_x + 6):
        g.paint_box(tx, 9, z0, 1, 2, 1, "0")
        g.paint_box(tx, 11, z0, 1, 2, 1, YELLOW)
        g.paint_box(tx - 1, 13, z0, 1, 1, 1, ORANGE)
    for sx in (gate_x - 8, gate_x + 10):
        g.paint_box(sx, 7, z0, 3, 4, 1, BLUE)
        g.paint_box(sx + 1, 7, z0, 1, 4, 1, YELLOW)
        g.paint_box(sx, 8, z0, 3, 1, 1, YELLOW)
    # lierre sur les murs (taches de 2x2 pour survivre au nettoyage)
    for (ix, iz) in ((x0 - 1, z0 + 7), (x1 + 1, z0 + 14),
                     (x0 + 11, z1 + 1), (x1 - 2, z1 + 1)):
        g.paint_box(ix, 4, iz, 2, 4, 1, DARKGREEN)

    # ---- tours rondes d'angle ------------------------------------------ #
    for (tx, tz) in ((x0 + 2, z0 + 2), (x1 - 2, z0 + 2),
                     (x0 + 2, z1 - 2), (x1 - 2, z1 - 2)):
        _castle_round_tower(g, tx, tz, 3.3, 3, wall_h + 10, color,
                            roof, stone)

    # ---- châtelet : deux tours carrées encadrant la porte -------------- #
    gate_top = 3 + wall_h + 9
    for tx in (gate_x - 5, gate_x + 5):
        g.box(tx, 3, 0, 5, gate_top - 3, 5, color)
        g.paint_box(tx, band, 0, 5, 1, 5, stone)
        _castle_crenellate(g, tx, 0, 5, 5, gate_top, color)
        for (wx, wz) in ((tx + 1, 0), (tx + 3, 0), (tx, 2), (tx + 4, 2)):
            g.paint_box(wx, 8, wz, 1, 4, 1, "0")
            g.paint_box(wx, 8, wz, 1, 1, 1, LBLUE)

    # tour centrale du châtelet, au-dessus de la porte
    gt = gate_top
    g.box(gate_x, 3, 0, 5, gt - 3, 4, color)
    g.paint_box(gate_x, band, 0, 5, 1, 4, stone)
    g.paint_box(gate_x + 1, 4, 0, 3, 7, 1, DARKRED)     # bannière
    g.paint_box(gate_x + 2, 8, 0, 1, 3, 1, YELLOW)
    g.box(gate_x - 1, gt, 0, 7, 3, 5, color)            # mâchicoulis plein
    _castle_crenellate(g, gate_x - 1, 0, 7, 5, gt + 3, color)
    _castle_flag(g, gate_x + 2, gt + 3, 0, RED, YELLOW, scale=1)

    # ---- donjon -------------------------------------------------------- #
    kx = x0 + (span - 9) // 2
    kz = z0 + (span - 9) // 2
    keep_h = wall_h + 12
    keep_top = 3 + keep_h
    g.box(kx, 3, kz, 9, keep_h, 9, color)
    g.paint_box(kx, band, kz, 9, 1, 9, stone)
    for (dx, dz) in ((0, 0), (8, 0), (0, 8), (8, 8)):
        tx, tz = kx + dx + 1, kz + dz + 1
        g.cylinder(tx, tz, 3, keep_top + 3, 1.6, color)
        y = keep_top + 3
        for rad in (1.8, 1.1, 0.4):
            g.cylinder(tx, tz, y, y + 3, rad, roof)
            y += 3
        g.box(tx, y, tz, 1, 2, 1, trim)
    for off in (2, 6):
        g.paint_box(kx + off, keep_top - 9, kz, 2, 5, 1, "0")
        g.paint_box(kx + off, keep_top - 8, kz, 2, 3, 1, LBLUE)
        g.paint_box(kx + off, keep_top - 9, kz + 8, 2, 5, 1, "0")
        g.paint_box(kx + off, keep_top - 8, kz + 8, 2, 3, 1, LBLUE)
        g.paint_box(kx, keep_top - 9, kz + off, 1, 5, 2, "0")
        g.paint_box(kx, keep_top - 8, kz + off, 1, 3, 2, LBLUE)
        g.paint_box(kx + 8, keep_top - 9, kz + off, 1, 5, 2, "0")
        g.paint_box(kx + 8, keep_top - 8, kz + off, 1, 3, 2, LBLUE)
    _castle_crenellate(g, kx, kz, 9, 9, keep_top, color)
    # lanterne centrale : petite tour qui domine le donjon
    lx, lz = kx + 4, kz + 4
    g.cylinder(lx, lz, keep_top, keep_top + 9, 1.7, color)
    g.cylinder(lx, lz, keep_top + 9, keep_top + 12, 2.2, color)
    for rad in (2.0, 1.4, 0.7):
        g.cylinder(lx, lz, keep_top + 12, keep_top + 15, rad, roof)
    _castle_flag(g, lx, keep_top + 15, lz, RED, YELLOW, scale=2)

    # ---- cour vivante -------------------------------------------------- #
    # escalier d'angle contre l'enceinte est
    sx, sz = x1 - 9, z1 - 3
    for i in range(9):
        g.box(sx + i, 3, sz, 1, 2 + i, 2, stone)
    # puits (2x2) et son toit
    wx, wz = x0 + 3, z1 - 5
    g.box(wx, 3, wz, 3, 3, 3, stone)                  # margelle pleine
    g.paint_box(wx + 1, 5, wz + 1, 1, 1, 1, "0")       # eau
    for (dx, dz) in ((0, 0), (2, 0), (0, 2), (2, 2)):
        g.box(wx + dx, 6, wz + dz, 1, 4, 1, BROWN)
    g.box(wx, 10, wz, 3, 1, 3, DARKRED)
    # étals de marché (auvents colorés sur poteaux)
    for (mx, mz, c) in ((x0 + 3, z0 + 6, RED), (x0 + 7, z0 + 6, BLUE),
                        (x0 + 3, z0 + 10, GREEN)):
        g.box(mx, 3, mz, 3, 1, 2, BROWN)
        for (dx, dz) in ((0, 0), (2, 0), (0, 1), (2, 1)):
            g.box(mx + dx, 4, mz + dz, 1, 4, 1, BROWN)
        g.box(mx, 8, mz, 3, 1, 2, c)
    # tonneaux et caisses
    for (bx, bz) in ((x1 - 4, z0 + 3), (x1 - 6, z0 + 3), (x1 - 4, z0 + 5)):
        g.box(bx, 3, bz, 2, 3, 2, BROWN)
        g.paint_box(bx, 4, bz, 2, 1, 2, stone)
    # petites tours de guet aux angles de la cour
    for (tx, tz) in ((x0 + 1, z1 - 3), (x1 - 3, z1 - 3)):
        g.box(tx, 3, tz, 2, 6, 2, stone)
        g.box(tx, 9, tz, 2, 3, 2, color)
    return g.normalize()


def _castle_flag(g: VoxelGrid, x: int, y: int, z: int, cloth: str,
                 emblem: str, scale: int = 1) -> None:
    """Mât de 2x1 (deux appuis) et drapeau 3x2 qui déborde du mât."""
    g.box(x, y, z, 1, 5 * scale, 2, DGRAY)
    g.box(x, y + 4 * scale, z, 3, 1, 2, cloth)
    g.paint_box(x + 1, y + 5 * scale - 1, z, 1, 1, 2, emblem)


def _castle_round_tower(g: VoxelGrid, cx: int, cz: int, r: float,
                        y0: int, height: int, color: str, roof: str,
                        trim: str) -> None:
    """Tour cylindrique : fût, bandeaux, parapet plein, toit conique étagé.

    Chaque volume est un **sous-ensemble** du précédent : le parapet est un
    disque plein (pas un anneau), donc ses cellules extérieures sont portées
    par les cellules intérieures elles-mêmes posées sur le fût. C'est ce qui
    évite les débords d'un stud impossibles à tenir.
    """
    top = y0 + height
    g.cylinder(cx, cz, y0, top, r, color)
    g.cylinder(cx, cz, y0, y0 + 3, r + 0.7, color)          # plinthe
    g.paint_box(int(cx - r), y0 + height // 3, int(cz - r),
                int(2 * r) + 1, 1, int(2 * r) + 1, trim)
    g.cylinder(cx, cz, top, top + 3, r + 1.0, color)        # parapet plein
    # créneaux sur le pourtour du parapet
    rr = r + 1.0
    for a in range(0, 360, 45):
        wx = int(round(cx + rr * math.cos(math.radians(a))))
        wz = int(round(cz + rr * math.sin(math.radians(a))))
        g.box(wx, top + 3, wz, 1, 3, 1, color)
    for (dx, dz) in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        g.paint_box(int(round(cx + dx * (r - 0.2))),
                    y0 + height // 2,
                    int(round(cz + dz * (r - 0.2))), 1, 4, 1, "0")
    # toit conique : rayons strictement décroissants
    y = top + 3
    # marches de 3 plaques : la passe de pentes peut alors poser de vraies
    # pentes 45° (3039/3040b) sur chaque anneau, au lieu d'un empilement plat.
    for rad in (3.3, 2.9, 2.4, 1.9, 1.3, 0.6):
        g.cylinder(cx, cz, y, y + 3, rad, roof)
        y += 3
    g.box(int(cx), y, int(cz), 1, 3, 1, trim)


def _castle_crenellate(g: VoxelGrid, x: int, z: int, w: int, d: int,
                       y: int, color: str) -> None:
    """Merlons d'un stud sur le périmètre (un sur deux), 3 plaques de haut."""
    for i in range(0, w, 2):
        g.box(x + i, y, z, 1, 3, 1, color)
        g.box(x + i, y, z + d - 1, 1, 3, 1, color)
    for j in range(1, d - 1, 2):
        g.box(x, y, z + j, 1, 3, 1, color)
        g.box(x + w - 1, y, z + j, 1, 3, 1, color)


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
