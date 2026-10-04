#!/usr/bin/env python3
"""Templates d'archétypes LEGO : le LLM ne choisit que des paramètres,
la géométrie est générée de façon déterministe (murs, pignons, toits,
porte et fenêtres toujours corrects).

Chaque template expose :
  - PARAMS_INFO : description des paramètres attendus (pour le prompt LLM)
  - DEFAULTS    : paramètres par défaut
  - build(params) -> LDrawModel
"""
from __future__ import annotations

from ldraw_model import CollisionError, LDrawModel, UnknownPartError

# Palettes courantes (codes LDraw).
BRICK = {"3004": 2, "3005": 1}          # 1x2, 1x1
WIDE = {"3010": 4, "3009": 6, "3008": 8}  # 1x4, 1x6, 1x8

LEVEL_BRICK = 3  # niveaux-plaques par brique


def _fill_row(model: LDrawModel, y: int, x: int, z: int, length: int,
              color: str, axis: str, holes: dict[int, str] | None = None):
    """Remplit une ligne de `length` studs le long de x ou z avec des briques
    1x4/1x2/1x1, en laissant des trous (portes/fenêtres) et en bordant les
    trous avec la couleur demandée."""
    holes = holes or {}
    i = 0
    while i < length:
        if i in holes:
            i += 1  # le trou sera rempli par le décor spécifique
            continue
        # plus grande brique qui tient sans chevaucher un trou
        for plen, piece in ((4, "3010"), (3, "3622"), (2, "3004"), (1, "3005")):
            if i + plen <= length and not any(h in holes for h in range(i, i + plen)):
                break
        coords = (x + i, z) if axis == "x" else (x, z + i)
        try:
            model.place(piece, coords[0], coords[1], y, color,
                        90 if axis == "z" else 0)
        except (CollisionError, UnknownPartError):
            pass  # coin déjà occupé par le mur perpendiculaire
        i += plen


def _fill_hole(model: LDrawModel, y: int, x: int, z: int,
               color: str, piece: str = "3004", rot: int = 0):
    try:
        model.place(piece, x, z, y, color, rot)
    except (CollisionError, UnknownPartError):
        pass


# --------------------------------------------------------------------- #
def build_house(p: dict) -> LDrawModel:
    """Maison rectangulaire : murs pleins, toit à deux pans avec pignons,
    porte encadrée et fenêtres vitrées."""
    w = max(8, min(24, int(p.get("width", 16))))
    d = max(8, min(20, int(p.get("depth", 10))))
    h = max(2, min(5, int(p.get("wall_height", 3))))       # niveaux de briques
    wall_c = str(p.get("wall_color", "19"))                # tan
    roof_c = str(p.get("roof_color", "4"))                 # rouge
    door_c = str(p.get("door_color", "14"))                # jaune
    glass_c = str(p.get("window_color", "43"))             # trans bleu clair
    baseplate = bool(p.get("baseplate", True))

    m = LDrawModel("house")
    # marge sur la baseplate 32x32, maison centrée dessus
    x0 = max(2, (32 - w) // 2) if baseplate else 0
    z0 = max(2, (32 - d) // 2) if baseplate else 0
    y0 = 1 if baseplate else 0   # la baseplate occupe le niveau 0

    if baseplate:
        try:
            m.place("3811", 0, 0, 0, "19")
        except (CollisionError, UnknownPartError):
            pass
    m.add_step()

    door_w, door_h = 2, 3                       # ouverture porte (studs x niveaux)
    door_x = x0 + w // 2 - 1                    # centrée sur la façade avant
    win_w = 2
    # fenêtres réparties sur la façade avant, hors porte
    n_win = max(0, min(2, int(p.get("windows", 1))))
    win_positions = []
    if n_win:
        if door_x - x0 >= 4:
            win_positions.append(door_x - 3)     # à gauche de la porte
        if x0 + w - (door_x + door_w) >= 4:
            win_positions.append(door_x + door_w + 1)  # à droite

    # --- murs (h niveaux de briques) ---
    for lvl in range(h):
        y = y0 + lvl * LEVEL_BRICK
        # mur avant (z = z0) avec porte + fenêtres
        holes = {}
        if lvl < door_h:  # la porte ne traverse que les premiers niveaux
            for i in range(door_w):
                holes[door_x - x0 + i] = "door"
        for wx in win_positions:
            if lvl == 0:  # fenêtres sur la rangée du bas uniquement
                for i in range(win_w):
                    holes[wx - x0 + i] = "window"
        _fill_row(m, y, x0, z0, w, wall_c, "x", holes)
        # mur arrière (z = z0 + d - 1)
        _fill_row(m, y, x0, z0 + d - 1, w, wall_c, "x", None)
        # murs latéraux (x = x0 et x = x0 + w - 1), entre les deux façades
        _fill_row(m, y, x0, z0 + 1, d - 2, wall_c, "z", None)
        _fill_row(m, y, x0 + w - 1, z0 + 1, d - 2, wall_c, "z", None)

        # décoration des trous de la façade avant
        if lvl < door_h:
            for i in range(door_w):
                _fill_hole(m, y, door_x + i, z0, door_c)      # battant jaune
        if lvl == 0:
            # vitres : 3 plaques empilées comblent exactement la rangée
            for wx in win_positions:
                for i in range(win_w):
                    for dy in range(LEVEL_BRICK):
                        _fill_hole(m, y0 + dy, wx + i, z0, glass_c, "3023")

    m.add_step()

    # --- toit à deux pans (primitive d'architecture) ---
    top_y = y0 + h * LEVEL_BRICK
    import arch
    arch.pitched_roof(m, x0, z0, w, d, top_y, roof_c)
    m.add_step()
    return m


# --------------------------------------------------------------------- #
def build_tower(p: dict) -> LDrawModel:
    """Tour cylindrique (base carrée) avec créneaux."""
    w = max(6, min(12, int(p.get("width", 8))))
    h = max(6, min(16, int(p.get("height", 10))))
    wall_c = str(p.get("wall_color", "71"))
    roof_c = str(p.get("roof_color", "4"))
    m = LDrawModel("tower")
    try:
        m.place("3811", 0, 0, 0, "19")
    except (CollisionError, UnknownPartError):
        pass
    m.add_step()
    x0 = z0 = max(2, (32 - w) // 2)   # centrée sur la baseplate
    y0 = 1  # la baseplate occupe le niveau 0
    for lvl in range(h):
        y = y0 + lvl * LEVEL_BRICK
        _fill_row(m, y, x0, z0, w, wall_c, "x", None)
        _fill_row(m, y, x0, z0 + w - 1, w, wall_c, "x", None)
        _fill_row(m, y, x0, z0 + 1, w - 2, wall_c, "z", None)
        _fill_row(m, y, x0 + w - 1, z0 + 1, w - 2, wall_c, "z", None)
    m.add_step()
    # créneaux sur le chemin de ronde, toit pyramidal au centre
    import arch
    top = y0 + h * LEVEL_BRICK
    inner = w - 2
    if inner >= 4:
        arch.crenellate(m, x0, z0, w, w, top, roof_c)
        arch.pyramid_roof(m, x0 + 1, z0 + 1, inner, top, roof_c)
    else:
        arch.pyramid_roof(m, x0, z0, w, top, roof_c)
    m.add_step()
    return m


def build_spaceship(p: dict) -> LDrawModel:
    """Vaisseau spatial : fuselage effilé, ailes symétriques attachées,
    cockpit vitré sur le dessus avant, propulseurs à l'arrière."""
    import arch
    length = max(12, min(26, int(p.get("length", 18))))
    width = max(4, min(8, int(p.get("width", 6))))
    span = max(0, min(10, int(p.get("wing_span", 6))))
    hull_c = str(p.get("hull_color", "71"))       # gris clair
    accent = str(p.get("accent_color", "272"))    # bleu foncé
    glass = str(p.get("cockpit_color", "43"))     # trans bleu clair
    n_eng = max(1, min(3, int(p.get("engines", 2))))

    m = LDrawModel("spaceship")
    x0 = 0
    z0 = 0
    # fuselage : 2 niveaux de briques
    arch.hull(m, x0, z0, width, length, 2, hull_c, y=0)
    m.add_step()

    # ailes : deux extensions symétriques qui chevauchent le fuselage
    if span >= 4:
        wing_d = max(4, length // 3)
        wz = z0 + length // 2 - wing_d // 2
        arch.wing(m, x0 - (span - 2), wz, span, wing_d, 0, accent)
        arch.wing(m, x0 + width - 2, wz, span, wing_d, 0, accent)
    m.add_step()

    # cockpit vitré sur le dessus avant
    arch.cockpit(m, x0 + width // 2 - 1, z0 + 3, 2, 4, 6, glass)
    m.add_step()

    # propulseurs arrière
    eng_w = max(1, (width - 1) // n_eng)
    for k in range(n_eng):
        arch.engine(m, x0 + 1 + k * (eng_w + 1), z0 + length, eng_w, 3, 0, accent)
    m.add_step()
    return m


TEMPLATES = {
    "house": {"build": build_house,
              "params": "width (8-24, défaut 16), depth (8-20, défaut 10), "
                        "wall_height (2-5, défaut 3), wall_color, roof_color, "
                        "door_color, window_color, windows (0-2), baseplate (bool)"},
    "tower": {"build": build_tower,
              "params": "width (6-12, défaut 8), height (6-16, défaut 10), "
                        "wall_color, roof_color, baseplate (bool)"},
    "spaceship": {"build": build_spaceship,
                  "params": "length (12-26, défaut 18), width (4-8, défaut 6), "
                            "wing_span (0-10, défaut 6), hull_color, "
                            "accent_color, cockpit_color, engines (1-3)"},
}

PARAM_PROMPT = """Tu paramètres un générateur LEGO déterministe. Réponds UNIQUEMENT
avec un JSON de paramètres (pas de briques, pas de coordonnées) :
{"type": "house"|"tower", ...paramètres...}
Paramètres disponibles :
- house : {params_house}
- tower : {params_tower}
Couleurs LDraw : 0 noir, 1 bleu, 2 vert, 4 rouge, 14 jaune, 15 blanc,
19 tan (beige), 25 orange, 43 trans bleu clair, 70 brun, 71 gris clair,
72 gris foncé, 272 bleu foncé, 320 rouge foncé.
Choisis le type le plus adapté à la demande et des dimensions cohérentes."""
