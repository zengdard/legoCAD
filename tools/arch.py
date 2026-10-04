#!/usr/bin/env python3
"""Primitives d'architecture LEGO : formes composées que les LLM ratent
systématiquement (toits, créneaux, escaliers), générées de façon déterministe.

Chaque primitive choisit ses pièces, gère ses collisions et remplit l'intérieur
pour rester physiquement stable (une coque de pentes creuse serait instable).

Convention des pentes LDraw (vérifiée au rendu) :
    3037 (Slope 45 2x4) et 3039 (Slope 45 2x2)
    rot 0   -> descend vers -z        rot 180 -> descend vers +z
    rot 90  -> descend vers -x        rot 270 -> descend vers +x
"""
from __future__ import annotations

LEVEL_BRICK = 3

# Pente adaptée à la largeur à couvrir : 2x4 pour 4 studs, 2x2 pour 2.
_SLOPE = {4: "3037", 2: "3039", 1: "3040b"}


def _row_of_slopes(model, y, x, z, width, color, rot) -> int:
    """Pose une rangée de pentes couvrant `width` studs en x, orientées `rot`."""
    placed = 0
    xx = x
    while xx < x + width:
        remaining = x + width - xx
        size = 4 if remaining >= 4 else (2 if remaining >= 2 else 1)
        if model.try_place(_SLOPE[size], xx, z, y, color, rot):
            placed += 1
        xx += size
    return placed


def pitched_roof(model, x: int, z: int, w: int, d: int, y: int, color: str,
                 ridge: str = "x") -> int:
    """Toit à deux pans : rives en pente vers l'extérieur, intérieur plein.

    Chaque niveau est en retrait de 2 studs par côté, donc repose entièrement
    sur le précédent (stable par construction). Les rives montrent les pentes,
    l'intérieur reste plat et plein. La faîtière se ferme d'elle-même quand les
    deux rives se rejoignent.
    """
    placed = 0
    if ridge == "z":
        # même construction, rôles de x et z échangés
        return _pitched_roof_axis_z(model, x, z, w, d, y, color)
    levels = max(1, (d - 1) // 2)
    for i in range(levels):
        ly = y + i * LEVEL_BRICK
        za, zb = z + 2 * i, z + d - 1 - 2 * i
        if za + 1 > zb:
            break
        # rive avant (descend vers -z), rive arrière (descend vers +z)
        placed += _row_of_slopes(model, ly, x, za, w, color, 0)
        if zb - 1 > za:
            placed += _row_of_slopes(model, ly, x, zb - 1, w, color, 180)
        # intérieur plein, entre les deux rives
        for zz in range(za + 2, zb - 1):
            placed += model.slab(x, zz, w, 1, ly, color, 1)
        if zb - 1 <= za + 2:
            break  # faîte atteint
    return placed


def _pitched_roof_axis_z(model, x, z, w, d, y, color) -> int:
    """Toit à deux pans avec faîtière parallèle à z (pentes vers ±x)."""
    placed = 0
    levels = max(1, (w - 1) // 2)
    for i in range(levels):
        ly = y + i * LEVEL_BRICK
        xa, xb = x + 2 * i, x + w - 1 - 2 * i
        if xa + 1 > xb:
            break
        # rives latérales : pentes orientées vers ±x, étendues en z
        for zz in range(z, z + d, 2):
            placed += model.try_place("3037" if d - (zz - z) >= 4 else "3039",
                                      xa, zz, ly, color, 90)
        if xb - 1 > xa:
            for zz in range(z, z + d, 2):
                placed += model.try_place("3037" if d - (zz - z) >= 4 else "3039",
                                          xb - 1, zz, ly, color, 270)
        for xx in range(xa + 2, xb - 1):
            placed += model.slab(xx, z, 1, d, ly, color, 1)
        if xb - 1 <= xa + 2:
            break
    return placed


def pyramid_roof(model, x: int, z: int, size: int, y: int, color: str) -> int:
    """Toit pyramidal / « conique » d'une tour, en construction LEGO réelle.

    Le pourtour est pavé de blocs de 2x2 studs :
      - coin       -> 3045 (Slope 2x2 Double Convex) orientée vers son coin
                      (rot 0 = coin -x-z, 90 = +x-z, 180 = -x+z, 270 = +x+z)
      - bord       -> 3039 (Slope 2x2) orientée vers son bord
    L'intérieur est comblé à plat, et un cône 2x2 ferme la pointe. C'est la
    silhouette classique des tours de château LEGO.
    """
    if size < 2:
        return 0
    placed = 0
    half = size // 2
    for ix in range(half):
        for iz in range(half):
            on_x = ix in (0, half - 1)
            on_z = iz in (0, half - 1)
            if not (on_x or on_z):
                continue  # intérieur traité plus bas
            px, pz = x + ix * 2, z + iz * 2
            if on_x and on_z:
                # coin : orienté vers son coin extérieur
                key = (1 if ix == half - 1 else 0, 1 if iz == half - 1 else 0)
                rot = {(0, 0): 0, (1, 0): 90, (0, 1): 180, (1, 1): 270}[key]
                part = "3045"
            elif on_z:
                rot = 0 if iz == 0 else 180
                part = "3039"
            else:
                rot = 90 if ix == 0 else 270
                part = "3039"
            if model.try_place(part, px, pz, y, color, rot):
                placed += 1
    # intérieur : dalles plates qui porteront la pointe
    inner = size - 4
    if inner >= 2:
        placed += model.slab(x + 2, z + 2, inner, inner, y, color, 1)
    # pointe : cône 2x2 (repli : pente 2x2 + brique 1x1)
    cx, cz = x + size // 2 - 1, z + size // 2 - 1
    if not model.try_place("98100", cx, cz, y + LEVEL_BRICK, color):
        placed += model.try_place("3039", cx, cz, y + LEVEL_BRICK, color, 0)
        placed += model.try_place("3005", cx, cz, y + 2 * LEVEL_BRICK, color)
    else:
        placed += 1
    return placed


def crenellate(model, x: int, z: int, w: int, d: int, y: int, color: str,
               period: int = 2) -> int:
    """Créneaux sur le pourtour d'un rectangle w x d (merlons d'un stud)."""
    placed = 0
    for xx in range(x, x + w, period):
        placed += model.try_place("3005", xx, z, y, color)
        placed += model.try_place("3005", xx, z + d - 1, y, color)
    for zz in range(z + 1, z + d - 1, period):
        placed += model.try_place("3005", x, zz, y, color)
        placed += model.try_place("3005", x + w - 1, zz, y, color)
    return placed


def stairs(model, x: int, z: int, height: int, color: str, direction: str = "+z",
           width: int = 2) -> int:
    """Escalier : `height` marches d'un demi-niveau... ici une marche par
    niveau de plaque, montant de 2 studs en profondeur chacune."""
    placed = 0
    for i in range(height):
        ly = i
        dz = i * 2 if direction in ("+z", "-z") else 0
        dx = i * 2 if direction in ("+x", "-x") else 0
        if direction == "-z":
            dz = -dz
        if direction == "-x":
            dx = -dx
        placed += model.slab(x + dx, z + dz, width if direction in ("+z", "-z") else 2,
                             2 if direction in ("+z", "-z") else width,
                             ly, color, 1)
    return placed


# ---------------------------------------------------------------------- #
# Véhicules : briques de base d'un vaisseau. Un vaisseau réussi = un
# fuselage allongé, des ailes ATTACHÉES au fuselage, un cockpit sur le
# dessus avant et des propulseurs à l'arrière.
# ---------------------------------------------------------------------- #

def hull(model, x, z, w, d, layers, color, y=0, nose=True) -> int:
    """Fuselage : corps plein de w x d studs sur `layers` niveaux, avec un nez
    effilé en pentes du côté -z (l'avant du vaisseau). Le nez est plein à la
    base et recouvert de pentes en escalier, donc solidaire du corps."""
    placed = 0
    nose_d = 0
    if nose and d >= 6:
        nose_d = 2 if d < 10 else 4
    body_z = z + nose_d
    body_d = d - nose_d
    if body_d > 0:
        placed += model.slab(x, body_z, w, body_d, y, color, layers)
    if nose_d:
        # base du nez : pleine, sur un niveau de moins que le corps
        base_layers = max(1, layers - 1)
        placed += model.slab(x, z, w, nose_d, y, color, base_layers)
        # pentes du dessus, en escalier qui recule vers le corps
        ly = y + base_layers * LEVEL_BRICK
        for k in range(max(1, nose_d // 2)):
            zz = z + 2 * k
            if zz >= z + nose_d:
                break
            placed += _row_of_slopes(model, ly, x, zz, w, color, 0)
    return placed


def wing(model, x, z, w, d, y, color, side="-x") -> int:
    """Aile plate (deux niveaux de plaques) s'étendant de `w` studs, avec un
    bord d'attaque en pente. Doit chevaucher le fuselage d'au moins un stud,
    sinon elle sera détachée."""
    placed = 0
    for i in range(2):
        placed += model.slab(x, z, w, d, y + i, color, 1)
    # bord d'attaque : pentes juste au-dessus des deux plaques (y+2)
    placed += _row_of_slopes(model, y + 2, x, z, w, color, 0)
    return placed


def cockpit(model, x, z, w, d, y, color) -> int:
    """Verrière : socle plein surmonté de pentes vitrées formant un dôme."""
    placed = model.slab(x, z, w, d, y, color, 1)
    placed += _row_of_slopes(model, y + LEVEL_BRICK, x, z, w, color, 0)
    # pentes latérales si la verrière est assez profonde
    if d >= 2:
        for zz in range(z + 2, z + d, 2):
            placed += model.try_place("3039", x, zz, y + LEVEL_BRICK, color, 90)
            placed += model.try_place("3039", x + w - 2, zz, y + LEVEL_BRICK,
                                      color, 270)
    return placed


def engine(model, x, z, w, d, y, color, glow="43") -> int:
    """Propulseur : bloc moteur de deux niveaux, prolongé d'une tuyère
    lumineuse juste derrière (mêmes niveaux, donc accolée au moteur)."""
    placed = model.slab(x, z, w, d, y, color, 2)
    placed += model.slab(x, z + d, w, 1, y, glow, 2)
    return placed


PRIMITIVES = {
    "pitched_roof": pitched_roof,
    "pyramid_roof": pyramid_roof,
    "crenellate": crenellate,
    "stairs": stairs,
    "hull": hull,
    "wing": wing,
    "cockpit": cockpit,
    "engine": engine,
}
