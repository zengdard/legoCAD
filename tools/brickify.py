#!/usr/bin/env python3
"""Compilateur volume → briques : le cœur du pipeline « vrais modèles ».

Entrée : un `tools/voxel.VoxelGrid` (1 voxel = 1 stud × 1 plaque, coloré).
Sortie : un `LDrawModel` dont **chaque pièce est posée sur des studs**, avec
un ordre de montage suivable et un rapport de couverture.

Ce que fait le compilateur, dans l'ordre :

1. **Cours de briques** : une colonne dont les 3 plaques sont pleines et de
   la même couleur reçoit une brique (3 plaques). Les plaques restantes
   (dessus, détails, 1-2 plaques d'épaisseur) reçoivent des plates. C'est la
   répartition réelle des sets LEGO (les plates représentent ~50 % des
   pièces), au lieu du « tout brique » du mode solver.
2. **Appareillage** : chaque niveau est pavé par rangées, avec un décalage
   des joints par rapport au niveau précédent (running bond). Les pièces
   2×N sont utilisées quand deux rangées voisines sont identiques, les
   1×N pour les parois d'un stud d'épaisseur.
3. **Support réel** : un placement n'est accepté que si au moins un de ses
   studs repose sur une pièce déjà posée (ou sur le sol). Un porte-à-faux
   n'est créé que s'il est tenu par le reste de la pièce — sinon la cellule
   est laissée vide et signalée (jamais de pièce flottante).
4. **Finition** : les plates exposées du dessus deviennent des tiles
   (surface lisse), comme dans les sets réels.
5. **Ordre de montage** : `build_order.plan()` produit des étapes qu'un
   humain peut suivre (chaque pièce a son appui déjà posé).

Le résultat est rendu par LeoCAD, exporté en .ldr, et accompagné d'une
nomenclature (`tools/bom.py`) et d'une notice (`tools/instructions.py`).

Exemple :
    python3 tools/brickify.py models/exemple.vox.json --name demo
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_order                   # noqa: E402
import stability                     # noqa: E402
from ldraw_model import CollisionError, LDrawModel  # noqa: E402
from voxel import VoxelGrid          # noqa: E402

# --------------------------------------------------------------------------- #
# Pièces disponibles (catalogue curé, toutes réelles et courantes)
# --------------------------------------------------------------------------- #
# hauteur du corps (3 = brique, 1 = plate/tile) puis largeur (studs) ->
# longueur (studs) -> id LDraw.
BRICKS = {
    1: {1: "3005", 2: "3004", 3: "3622", 4: "3010", 6: "3009", 8: "3008"},
    2: {2: "3003", 3: "3002", 4: "3001", 6: "2456", 8: "3007"},
}
PLATES = {
    1: {1: "3024", 2: "3023", 3: "3623", 4: "3710", 6: "3666", 8: "3460"},
    2: {2: "3022", 3: "3021", 4: "3020", 6: "3795", 8: "3034"},
}
TILES = {
    1: {1: "3070b", 2: "3069b", 3: "63864", 4: "2431", 6: "6636"},
    2: {2: "3068b", 3: "26603", 4: "87079"},
}

# pénalité de préférence : les sets réels utilisent surtout des 4 et des 2
_LENGTH_PENALTY = {4: 0.0, 2: 0.004, 6: 0.010, 8: 0.014, 3: 0.018, 1: 0.030}


@dataclass
class BrickifyOptions:
    tiles_on_top: bool = True
    use_2x: bool = True
    max_parts_per_step: int = 12
    add_steps: bool = True
    bond: str = "running"        # running | stack
    alternate_axis: bool = True
    clean_colors: int = 3        # taille mini d'une tache de couleur (0 = off)
    repair_islands: bool = True
    slopes: bool = True          # convertir les marches de 3 plaques en pentes
    foundation: bool = True      # plaque de fond 4x4/4x8 (pièces 2D, liaisons)
    tile_cap: bool = True        # finition : une plaque de tile sur chaque sommet
    report_levels: bool = False


def _part_table(h: int, width: int, top: bool) -> dict:
    if h == 3:
        return BRICKS.get(width, {})
    if top:
        return TILES.get(width, PLATES.get(width, {}))
    return PLATES.get(width, {})


def _supported(cell, y, surface, ground):
    if ground:
        return True
    return surface.get(cell, -1) == y


def _dp_partition(n: int, supported: list[bool], lengths: list[int],
                  prev_seams: set | None = None,
                  preferred_first: int | None = None,
                  below_ids: list | None = None) -> tuple[list, list]:
    """Pave une rangée de n cellules en minimisant les pièces.

    Récompense les pièces 4/2 (les plus courantes) et surtout les pièces qui
    **enjambent** deux pièces du dessous (liaison réelle entre rangées),
    pénalise les joints alignés sur ceux du niveau précédent (appareillage),
    et exige que chaque pièce ait au moins une cellule supportée.
    Retourne (segments, gaps) où segments = [(début, longueur)].
    """
    INF = float("inf")
    dp: list[tuple[float, list]] = [(INF, [])] * (n + 1)
    dp[n] = (0.0, [])
    gap_dp: list[tuple[float, list]] = [(INF, [])] * (n + 1)
    gap_dp[n] = (0.0, [])
    for i in range(n - 1, -1, -1):
        best = (INF, [])
        choices = sorted(lengths, reverse=True)
        # appareillage : sur une rangée assez longue, on impose la longueur du
        # premier tronçon pour que les joints soient décalés d'un demi-élément
        # par rapport au niveau du dessous (sinon les deux niveaux restent
        # indépendants). On retombe sur le choix libre si ce n'est pas posable.
        forced = (preferred_first if preferred_first and i == 0
                  and preferred_first in lengths and preferred_first < n
                  and any(supported[:preferred_first]) else None)
        if forced:
            choices = [forced]
        for L in choices:
            if i + L > n:
                continue
            if not any(supported[i:i + L]):
                continue
            rest_cost, rest = dp[i + L]
            if rest_cost == INF:
                continue
            cost = rest_cost + 1.0 + _LENGTH_PENALTY.get(L, 0.02)
            if i + L < n and prev_seams and (i + L) in prev_seams:
                cost += 0.045
            if i == 0 and preferred_first and L != preferred_first:
                cost += 0.012
            if below_ids:
                ids = set()
                for j in range(i, i + L):
                    v = below_ids[j]
                    if v:
                        ids |= v if isinstance(v, set) else {v}
                if len(ids) > 1:
                    # la pièce relie plusieurs pièces du dessous : c'est ce
                    # qui rend le modèle d'un seul bloc
                    cost -= 0.09 * (len(ids) - 1)
            if cost < best[0]:
                best = (cost, [(i, L)] + rest)
        if best[0] == INF and forced:
            # le premier tronçon imposé n'a pas de support : on repart libre
            for L in sorted(lengths, reverse=True):
                if i + L > n or not any(supported[i:i + L]):
                    continue
                rest_cost, rest = dp[i + L]
                if rest_cost == INF:
                    continue
                cost = rest_cost + 1.0 + _LENGTH_PENALTY.get(L, 0.02)
                if below_ids:
                    ids = set()
                    for j in range(i, i + L):
                        v = below_ids[j]
                        if v:
                            ids |= v if isinstance(v, set) else {v}
                    if len(ids) > 1:
                        cost -= 0.09 * (len(ids) - 1)
                if cost < best[0]:
                    best = (cost, [(i, L)] + rest)
        dp[i] = best
        # version avec trou : on saute la cellule i (coût prohibitif)
        if dp[i][0] == INF:
            rest_cost, rest = gap_dp[i + 1]
            gap_dp[i] = (rest_cost + 100.0, [(i, 0)] + rest)
        else:
            gap_dp[i] = dp[i]
    cost, segs = dp[0]
    if cost == INF:
        cost, segs = gap_dp[0]
    return segs, [s for s in segs if s[1] == 0]


def _runs(cells: set, along: int, perp: int, value: int) -> list[tuple[int, int]]:
    """Plages continues d'une rangée (coordonnée perpendiculaire fixée)."""
    vals = sorted(c[along] for c in cells if c[perp] == value)
    out = []
    if not vals:
        return out
    start = prev = vals[0]
    for v in vals[1:]:
        if v == prev + 1:
            prev = v
            continue
        out.append((start, prev + 1))
        start = prev = v
    out.append((start, prev + 1))
    return out


def _axis_info(cells: set) -> dict:
    """Statistiques de pavage selon x et z.

    `runs` = nombre total de plages continues, `single` = chaque rangée n'a
    qu'une seule plage (volume compact). C'est ce qui permet de choisir l'axe
    de pavage : une bande de toit à deux rangées disjointes doit être pavée
    le long de sa longueur, pas dans le vide entre les deux.
    """
    info = {}
    for axis, (along, perp) in (("x", (0, 1)), ("z", (1, 0))):
        lanes: dict[int, list[int]] = {}
        for c in cells:
            lanes.setdefault(c[perp], []).append(c[along])
        runs, single, longest = 0, True, 0
        for vals in lanes.values():
            vals.sort()
            n, prev = 1, vals[0]
            for v in vals[1:]:
                if v != prev + 1:
                    n += 1
                prev = v
            runs += n
            longest = max(longest, len(vals))
            if n != 1:
                single = False
        info[axis] = {"runs": runs, "single": single, "longest": longest,
                      "lanes": len(lanes)}
    return info


def _foundation(model: LDrawModel, cells: set, colors: dict, y: int,
                surface: dict, surface_part: dict) -> tuple[int, list]:
    """Pose une plaque de fond 4×4/4×8 sur les grandes surfaces.

    Deux plaques 2×4 côte à côte ne sont pas attachées : une grande plaque
    4×4/4×8 (3031/3035, pièces réelles) relie les rangées. Les cellules qui
    ne peuvent pas être couvertes par une grande plaque sont laissées au
    tiler normal (1×N/2×N).
    """
    placed, gaps = 0, []
    todo = set(cells)
    candidates = ((8, 4, "3035", 0), (4, 4, "3031", 0),
                  (4, 2, "3020", 0), (2, 4, "3020", 90),
                  (2, 2, "3022", 0), (1, 4, "3710", 90),
                  (1, 2, "3023", 90), (1, 1, "3024", 0))
    for (x0, z0) in sorted(todo):
        if (x0, z0) not in todo:
            continue
        color = colors[(x0, z0)]
        for (w, d, pid, rot) in candidates:
            rect = {(x, z) for x in range(x0, x0 + w)
                    for z in range(z0, z0 + d)}
            if not rect <= todo:
                continue
            if any(colors[c] != color for c in rect):
                continue
            if model.try_place(pid, x0, z0, y, color, rot):
                for (x, z) in rect:
                    surface[(x, z)] = y + 1
                    surface_part[(x, z)] = len(model.bricks) - 1
                todo -= rect
                placed += 1
                break
        else:
            gaps.append((x0, z0))
    return placed, gaps


def _tile_layer(model: LDrawModel, cells: set, colors: dict, y: int, h: int,
                surface: dict, surface_part: dict, grid_cells: set,
                opts: BrickifyOptions, layer_index: int,
                seams: dict) -> tuple[int, list]:
    """Pave un niveau (h plaques) ; retourne (nb pièces, cellules manquées)."""
    if not cells:
        return 0, []
    ground = y == 0
    # axe : on pave en rangées le long du côté qui donne le plus longues
    # plages ; sur les volumes compacts, on alterne l'orientation d'un cours
    # à l'autre (comme un vrai mur d'appareillage) pour que les rangées d'un
    # niveau lient celles du niveau précédent.
    info = _axis_info(cells)
    axis = "x" if (info["x"]["runs"], -info["x"]["longest"]) <= \
        (info["z"]["runs"], -info["z"]["longest"]) else "z"
    span_x = max(c[0] for c in cells) - min(c[0] for c in cells) + 1
    span_z = max(c[1] for c in cells) - min(c[1] for c in cells) + 1
    if (opts.bond == "running" and opts.alternate_axis
            and layer_index % 2 == 1
            and info["x"]["single"] and info["z"]["single"]
            and min(span_x, span_z) >= 3):
        axis = "z" if axis == "x" else "x"
    along, perp = (0, 1) if axis == "x" else (1, 0)
    lanes: dict[int, dict] = {}
    for c in cells:
        lanes.setdefault(c[perp], {}).setdefault(colors[c], set()).add(c)

    placed = 0
    gaps: list = []
    used_lanes: set[tuple[int, int]] = set()
    perp_values = sorted(lanes)
    prev_seams = seams.get(axis, set())

    for pi, p in enumerate(perp_values):
        for color, color_cells in lanes[p].items():
            for (a0, a1) in _runs(color_cells, along, perp, p):
                if (p, a0, color) in used_lanes:
                    continue
                width = 1
                partner = None
                # décalage d'un demi-stud d'un cours à l'autre : les pièces
                # 2×N enjambent alors les joints du dessous (appareillage)
                pair_parity = layer_index % 2 if opts.bond == "running" else 0
                if opts.use_2x and p + 1 in lanes and p % 2 == pair_parity \
                        and color in lanes[p + 1]:
                    runs2 = _runs(lanes[p + 1][color], along, perp, p + 1)
                    if (a0, a1) in runs2 and \
                            (p + 1, a0, color) not in used_lanes:
                        width = 2
                        partner = p + 1
                run_len = a1 - a0

                def _layout(w):
                    part = partner if w == 2 else None
                    lc = [((a, p) if axis == "x" else (p, a))
                          for a in range(a0, a1)]
                    sp = [_supported(c, y, surface, ground) for c in lc]
                    if w == 2:
                        lc += [((a, part) if axis == "x" else (part, a))
                               for a in range(a0, a1)]
                        sp = [sp[i] or _supported(
                            ((a0 + i, part) if axis == "x"
                             else (part, a0 + i)), y, surface, ground)
                            for i in range(a1 - a0)]
                    tb = _part_table(h, w, top=_is_top(lc, y, h, grid_cells))
                    return lc, sp, tb

                # une pièce 2×N n'existe pas dans toutes les longueurs : si
                # la rangée est trop courte, on repasse en 1×N
                length_cells, supp, table = _layout(width)
                lengths = sorted(table.keys())
                if width == 2 and (not lengths or min(lengths) > run_len):
                    width, partner = 1, None
                    length_cells, supp, table = _layout(1)
                    lengths = sorted(table.keys())
                if not lengths:
                    gaps.extend(length_cells)
                    continue
                pref = None
                if opts.bond == "running" and not ground and run_len >= 6:
                    # alterne le premier joint : 2 ou 4 selon la rangée/niveau
                    pref = 2 if ((pi + layer_index) % 2) else 4
                    if pref > run_len:
                        pref = None
                below_ids = []
                for a in range(a0, a1):
                    ids = set()
                    for q in ([p, partner] if width == 2 else [p]):
                        coord = (a, q) if axis == "x" else (q, a)
                        if surface.get(coord) == y:
                            pid_below = surface_part.get(coord)
                            if pid_below is not None:
                                ids.add(pid_below)
                    below_ids.append(ids or None)
                segs, _ = _dp_partition(run_len, supp, lengths,
                                        prev_seams={s - a0 for s in prev_seams},
                                        preferred_first=pref,
                                        below_ids=below_ids)
                for (i, L) in segs:
                    if L == 0:
                        gaps.extend([(a0 + i, p)] +
                                    ([(a0 + i, partner)] if width == 2 else []))
                        continue
                    pid = table.get(L)
                    if pid is None:
                        gaps.extend([(a0 + i + k, p) for k in range(L)] +
                                    ([(a0 + i + k, partner)
                                      for k in range(L)] if width == 2 else []))
                        continue
                    color_code = color
                    if axis == "x":
                        px, pz, rot = a0 + i, p, 0
                    else:
                        px, pz, rot = p, a0 + i, 90
                    try:
                        model.place(pid, px, pz, y, color_code, rot)
                    except (CollisionError, ValueError):
                        gaps.extend([(a0 + i + k, p) for k in range(L)])
                        continue
                    placed += 1
                    for k in range(L):
                        for q in ([p, partner] if width == 2 else [p]):
                            coord = ((a0 + i + k, q) if axis == "x"
                                     else (q, a0 + i + k))
                            surface[coord] = y + h
                            surface_part[coord] = len(model.bricks) - 1
                    if i + L < run_len:
                        if axis == "x":
                            seams["x"].add(a0 + i + L)
                        else:
                            seams["z"].add(a0 + i + L)
                    # bords de la rangée = futurs joints dans l'autre axe
                    if axis == "x":
                        seams["z"].add(p)
                        seams["z"].add(p + width)
                    else:
                        seams["x"].add(p)
                        seams["x"].add(p + width)
                if width == 2:
                    used_lanes.add((partner, a0, color))
    return placed, gaps


def _is_top(cells, y: int, h: int, grid_cells: set) -> bool:
    return all((c[0], y + h, c[1]) not in grid_cells for c in cells)


def _brickify_once(grid: VoxelGrid, name: str,
                    opts: BrickifyOptions) -> tuple[LDrawModel, dict]:
    """Compilation d'une grille déjà nettoyée (une passe)."""
    cap_cells: set = set()
    if opts.tile_cap:
        # une plaque de finition (tile) sur chaque sommet : surface lisse
        add = {}
        tops: dict[tuple, int] = {}
        for (x, yy, z) in grid.cells:
            tops[(x, z)] = max(tops.get((x, z), 0), yy + 1)
        for (x, z), t in tops.items():
            color = grid.cells.get((x, t - 1, z), "15")
            add[(x, t, z)] = color
        cap_cells = set(add)
        grid = VoxelGrid({**grid.cells, **add})

    model = LDrawModel(name)
    surface: dict[tuple, int] = {}
    surface_part: dict[tuple, int] = {}
    seams: dict[str, set] = {"x": set(), "z": set()}
    all_gaps: list = []
    cells = grid.cells
    if not cells:
        return model, {"status": "EMPTY", "pieces": 0, "coverage": 0.0,
                       "gaps": [], "error": "grille vide"}

    # plaque de fond sur la couche 0 (grandes surfaces uniquement)
    foundation_gaps: list = []
    if opts.foundation:
        base_cells = {(x, z) for (x, yy, z) in cells if yy == 0}
        base_colors = {c: cells[(c[0], 0, c[1])] for c in base_cells}
        _n, foundation_gaps = _foundation(model, base_cells, base_colors,
                                         0, surface, surface_part)

    y = 0
    y_max = max(c[1] for c in cells) + 1
    layer_index = 0
    while y < y_max:
        level = {(x, z) for (x, yy, z) in cells if yy == y}
        # cellules déjà couvertes par une brique posée plus bas
        level = {c for c in level if surface.get(c, -1) <= y}
        if level:
            # cours de briques : 3 plaques pleines, même couleur sur la
            # colonne ET empreinte qui ne s'élargit pas (sinon une brique de
            # 3 plaques bloque le débord de la couche suivante : le volume ne
            # peut plus être posé). Les zones qui s'élargissent sont donc
            # pavées en plaques, ce qui laisse la couche au-dessus déborder
            # depuis un appui réel.
            fp = {(x, z) for (x, z) in level}
            fp1 = {(x, z) for (x, yy, z) in cells if yy == y + 1}
            fp2 = {(x, z) for (x, yy, z) in cells if yy == y + 2}
            grows = not (fp1 <= fp and fp2 <= fp)
            brickable = set()
            for (x, z) in level:
                col = [cells.get((x, y + k, z)) for k in range(3)]
                if grows:
                    continue
                if any((x, y + k, z) in cap_cells for k in range(3)):
                    continue
                if None not in col and len(set(col)) == 1 \
                        and surface.get((x, z), -1) <= y:
                    brickable.add((x, z))
            plates = level - brickable
            n, g = _tile_layer(model, brickable, {c: cells[(c[0], y, c[1])]
                                                  for c in brickable},
                               y, 3, surface, surface_part, cells, opts,
                               layer_index, seams)
            all_gaps.extend(g)
            n2, g2 = _tile_layer(model, plates, {c: cells[(c[0], y, c[1])]
                                                 for c in plates},
                                 y, 1, surface, surface_part, cells, opts,
                                 layer_index, seams)
            all_gaps.extend(g2)
            layer_index += 1
        y += 1

    # pentes sur les marches de 3 plaques (toits, capots, nez)
    slope_stats = {"slopes": 0}
    if opts.slopes:
        import slopes
        model, slope_stats = slopes.apply(model)

    # ordre de montage
    steps = build_order.plan(model, opts.max_parts_per_step) if opts.add_steps \
        else []
    build_errors = build_order.validate(model, steps) if steps else []
    if steps:
        build_order.apply(model, steps)

    covered = set()
    for b in model.bricks:
        part = model.part(b["part_id"])
        sx, sz = model._footprint(part, b["rot"])
        h = 3 if part["kind"] == "brick" and not part["desc"].lower().startswith("plate") else 1
        # hauteur réelle (les tiles/plates font 1 plaque)
        from ldraw_model import _NOMINAL_H, LDU_PER_LEVEL
        h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
        for cx in range(b["x"], b["x"] + sx):
            for cz in range(b["z"], b["z"] + sz):
                for cy in range(b["y"], b["y"] + h):
                    covered.add((cx, cy, cz))
    voxels = set(cells)
    missing = voxels - covered

    stab = stability.analyze(model)
    report = {
        "status": "OK" if not missing and not build_errors else "INCOMPLETE",
        "pieces": len(model.bricks),
        "types": len(model.parts_summary()),
        "voxels": len(voxels),
        "coverage": round(len(voxels & covered) / max(1, len(voxels)), 4),
        "gaps": sorted(missing)[:40],
        "gap_count": len(missing),
        "build_steps": len(steps),
        "build_errors": build_errors[:10],
        "islands": stab.get("islands", 0),
        "connections": stab.get("connections", 0),
        "min_stability": stab.get("min_stability", 0.0),
        "unsupported": stab.get("unsupported", []),
        "tipping_joints": stab.get("tipping_joints", []),
        "single_stud": len(stab.get("single_stud", [])),
        "slopes": slope_stats.get("slopes", 0),
        "connectors": stab.get("families", {}).get("counts", {}),
        "bounds": model.bounds(),
    }
    return model, report



def brickify(grid: VoxelGrid, name: str = "model",
             opts: BrickifyOptions | None = None) -> tuple[LDrawModel, dict]:
    """Compile une grille de voxels en modèle constructible.

    Le compilateur travaille en plusieurs passes si nécessaire : un petit
    îlot de pièces isolé (détail de surface impossible à attacher) est
    retiré, puis la grille est recompilée. Le résultat est ainsi **un seul
    objet soulevable**, pas une poignée de pièces posées côte à côte.
    """
    import studs
    opts = opts or BrickifyOptions()
    grid = grid.normalize()
    if opts.clean_colors:
        grid = grid.clean_colors(opts.clean_colors)
    removed = 0
    model, report = _brickify_once(grid, name, opts)
    for _ in range(2):
        if not opts.repair_islands or report.get("islands", 0) <= 1:
            break
        comps = studs.components(model)
        if len(comps) < 2:
            break
        biggest = max(comps, key=len)
        if len(biggest) < 0.6 * len(model.bricks):
            break                      # deux moitiés : on ne casse pas tout
        drop = set()
        for c in comps:
            if c is biggest:
                continue
            for i in c:
                g = studs.part_geometry(model, i)
                for (x, z) in g["footprint"]:
                    for y in range(g["base"], g["top"]):
                        drop.add((x, y, z))
        if not drop:
            break
        grid = VoxelGrid({k: v for k, v in grid.cells.items()
                          if k not in drop})
        removed += len(drop)
        model, report = _brickify_once(grid, name, opts)
    report["removed_cells"] = removed
    return model, report


def main():
    ap = argparse.ArgumentParser(description="volume .vox.json -> .ldr constructible")
    ap.add_argument("vox", help="fichier .vox.json ou .vox.txt")
    ap.add_argument("--name", default=None)
    ap.add_argument("--no-tiles", action="store_true")
    ap.add_argument("--stack", action="store_true",
                    help="appareillage droit (joints alignés) au lieu de running bond")
    ap.add_argument("--no-steps", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    grid = VoxelGrid.load(args.vox)
    name = args.name or Path(args.vox).stem
    opts = BrickifyOptions(tiles_on_top=not args.no_tiles,
                           bond="stack" if args.stack else "running",
                           add_steps=not args.no_steps)
    model, report = brickify(grid, name, opts)
    out = Path(args.out) if args.out else \
        Path(__file__).resolve().parent.parent / "models" / f"{name}.ldr"
    model.save(out)
    print(f"sauvé : {out}")
    print(report)


if __name__ == "__main__":
    main()
