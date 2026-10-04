#!/usr/bin/env python3
"""Générateur de modèles LDraw : assemble des fichiers .ldr à partir d'un
catalogue de pièces, sur une grille de studs, avec détection de collision.

Repère LDraw : X vers la droite, Y vers le bas, Z vers l'avant.
  - 1 stud = 20 LDU ; hauteur brique = 24 LDU ; hauteur plaque = 8 LDU.
  - Le sol est à Y=0 : une brique posée au sol a son centre à Y=-12.

L'API publique travaille en coordonnées "briques" :
  place(part_id, x, z, y=0, color="4", rot=0)
    x, z : coin du côté stud le plus petit (coin avant-gauche, avant rotation)
    y    : niveau en PLAQUES (1 brique = 3, 1 plaque = 1)
    rot  : 0 ou 90 (degrés, rotation autour de Y)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STUD = 20          # LDU par stud
BRICK_H = 24       # LDU par brique
PLATE_H = 8        # LDU par plaque
LDU_PER_LEVEL = PLATE_H  # l'axe vertical est gradué en plaques
LEVEL_BRICK = BRICK_H // PLATE_H  # 3 niveaux-plaques par brique

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "pieces_catalog.json"
_catalog = json.loads(_CATALOG_PATH.read_text())
PARTS = _catalog["parts"]
COLORS = _catalog["colors"]

# Résolution étendue : n'importe quelle pièce de la bibliothèque LDraw
# complète (~25 000) peut être posée, pas seulement les 51 du catalogue curé.
_sys_path_added = False


def _part_data(part_id: str) -> dict | None:
    """Fiche unifiée d'une pièce : catalogue curé d'abord, index complet ensuite."""
    global _sys_path_added
    if part_id in PARTS:
        return PARTS[part_id]
    if not _sys_path_added:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        _sys_path_added = True
    import parts_index
    import build_catalog
    info = parts_index.get(part_id)
    if info is None:
        return None
    path = Path(__file__).resolve().parent.parent / "ldraw" / "ldraw" / "parts" / f"{part_id}.dat"
    desc, dims = build_catalog.parse_part(path)
    dx, dy, dz = dims if dims else (20, info["height_ldu"], 20)
    return {
        "id": part_id,
        "desc": info["desc"],
        "bbox_ldu": [round(dx), round(dy), round(dz)],
        "studs_x": round(dx / 20, 2),
        "studs_z": round(dz / 20, 2),
        "height_brick_units": round(info["height_ldu"] / 24, 3),
        "kind": info["family"] if info["family"] != "other" else "brick",
    }


class CollisionError(ValueError):
    pass


class UnknownPartError(ValueError):
    pass


# Hauteur nominale en LDU par famille : le bbox réel inclut le stud
# supérieur (+4 LDU), on utilise donc la hauteur de construction normalisée.
_NOMINAL_H = {"brick": 24, "round": 24, "slope": 24, "cylinder": 24,
              "technic": 24, "other": 24,
              "cone": 48, "plate": 8, "tile": 8, "baseplate": 8}


class LDrawModel:
    def __init__(self, name: str = "model"):
        self.name = name
        self.bricks: list[dict] = []      # ordre de pose = ordre de construction
        self.steps: list[int] = []        # indices (dans bricks) où commencer un step
        self._occupied: dict[tuple, int] = {}  # (x_cell, y_level, z_cell) -> index brique
        self._resolved: dict[str, dict] = {}   # cache de fiches de pièces
        self.warnings: list[str] = []
        self.autofit = False  # si True, une collision décale la pièce au lieu d'échouer

    def part(self, part_id: str) -> dict:
        if part_id not in self._resolved:
            data = _part_data(part_id)
            if data is None:
                raise UnknownPartError(
                    f"Pièce {part_id} introuvable dans la bibliothèque LDraw. "
                    "Utilise search_parts pour trouver un id valide.")
            self._resolved[part_id] = data
        return self._resolved[part_id]

    # ------------------------------------------------------------------ #
    def place(self, part_id: str, x: int, z: int, y: int = 0,
              color: str = "4", rot: int = 0) -> dict:
        """Pose une pièce. Retourne la brique ajoutée.
        Lève UnknownPartError / CollisionError."""
        part = self.part(part_id)

        # pose idempotente : le doublon exact est ignoré silencieusement
        for b in self.bricks:
            if (b["part_id"] == part_id and b["x"] == x and b["z"] == z
                    and b["y"] == y and b["rot"] == rot and b["color"] == str(color)):
                return b

        sx, sz = self._footprint(part, rot)
        if abs(part["studs_x"] - round(part["studs_x"])) > 0.05 or \
           abs(part["studs_z"] - round(part["studs_z"])) > 0.05:
            self.warnings.append(
                f"{part_id} ({part['desc']}) a une empreinte non entière "
                f"({part['studs_x']}x{part['studs_z']} studs) : arrondie à {sx}x{sz}.")
        level_h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
        try:
            self._check_collision(x, z, y, sx, sz, level_h, part)
        except CollisionError:
            if not self.autofit:
                raise
            # auto-réparation : premier emplacement libre voisin (spirale)
            placed = False
            for r in (1, 2, 3):
                for dx in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        if max(abs(dx), abs(dz)) != r:
                            continue
                        try:
                            self._check_collision(x + dx, z + dz, y, sx, sz,
                                                  level_h, part)
                        except CollisionError:
                            continue
                        x, z = x + dx, z + dz
                        placed = True
                        break
                    if placed:
                        break
                if placed:
                    break
            if not placed:
                self.warnings.append(f"{part_id} en ({x},{z}) rejetée: "
                                     "aucun emplacement libre voisin")
                return {"part_id": part_id, "x": x, "z": z, "y": y,
                        "color": str(color), "rot": rot, "rejected": True}

        brick = {"part_id": part_id, "x": x, "z": z, "y": y,
                 "color": str(color), "rot": rot}
        self.bricks.append(brick)
        for cx in range(x, x + sx):
            for cz in range(z, z + sz):
                for cy in range(y, y + level_h):
                    self._occupied[(cx, cy, cz)] = len(self.bricks) - 1
        return brick

    def try_place(self, part_id: str, x: int, z: int, y: int = 0,
                  color: str = "4", rot: int = 0) -> bool:
        """Comme place() mais retourne False au lieu de lever une exception
        si la pose est impossible (collision ou pièce inconnue)."""
        try:
            self.place(part_id, x, z, y, color, rot)
            return True
        except (CollisionError, UnknownPartError, ValueError):
            return False

    # ------------------------------------------------------------------ #
    # Primitives de haut niveau : le script décrit des volumes, le moteur
    # choisit les pièces et gère les collisions. C'est ce qui évite au LLM
    # de calculer des coordonnées une par une.
    # ------------------------------------------------------------------ #

    def slab(self, x: int, z: int, w: int, d: int, y: int = 0, color: str = "4",
             layers: int = 1, openings: list | None = None,
             part_override: str | None = None) -> int:
        """Pave un rectangle de w x d studs (coin en x,z) sur `layers` niveaux
        de briques, en choisissant les plus grandes pièces possibles.
        `openings` : liste de (ox, oz, ow, od) en studs, laissées vides à tous
        les niveaux (portes, fenêtres, puits). Retourne le nombre de pièces posées.
        Un mur est un slab de profondeur 1 ; un toit/sol, un slab de layers=1."""
        open_cells = set()
        for (ox, oz, ow, od) in (openings or []):
            for cx in range(ox, ox + ow):
                for cz in range(oz, oz + od):
                    open_cells.add((cx, cz))
        placed = 0
        for layer in range(max(1, layers)):
            ly = y + layer * LEVEL_BRICK
            zz = z
            while zz < z + d:
                band = 2 if zz + 2 <= z + d else 1
                xx = x
                while xx < x + w:
                    for (pw, pd, pid) in ((4, band, "3001" if band == 2 else "3010"),
                                          (2, band, "3003" if band == 2 else "3004"),
                                          (1, band, "3004" if band == 2 else "3005")):
                        if xx + pw > x + w:
                            continue
                        cells = [(cx, cz) for cx in range(xx, xx + pw)
                                 for cz in range(zz, zz + pd)]
                        if any(c in open_cells for c in cells):
                            continue
                        rot = 90 if (band == 2 and pw == 1) else 0
                        if self.try_place(part_override or pid, xx, zz, ly,
                                          color, rot):
                            placed += 1
                            xx += pw
                            break
                    else:
                        xx += 1  # cellule occupée : on avance d'un stud
                zz += band
        return placed

    def column(self, x: int, z: int, layers: int, color: str = "4",
               part: str = "3005") -> int:
        """Empile `layers` briques (ou la pièce `part`) à la verticale."""
        placed = 0
        for i in range(max(1, layers)):
            if self.try_place(part, x, z, i * LEVEL_BRICK, color):
                placed += 1
        return placed

    def clearance(self, x: int, z: int, w: int, d: int, layers: int,
                  y: int = 0) -> bool:
        """Vrai si le volume w x d x layers est entièrement libre."""
        for cx in range(x, x + w):
            for cz in range(z, z + d):
                for cy in range(y, y + layers * LEVEL_BRICK):
                    if (cx, cy, cz) in self._occupied:
                        return False
        return True

    # ------------------------------------------------------------------ #
    def stability(self) -> dict:
        """Rapport de stabilité physique (appui, porte-à-faux, basculement).
        `min_stability` est le maillon faible : 1.0 = tout est stable."""
        import stability as _st
        return _st.analyze(self)

    def connectivity(self) -> dict:
        """Composantes connexes du modèle (voxels adjacents par face).
        Détecte les amas de briques détachés du reste — un modèle en un seul
        bloc a islands = 1."""
        voxels: dict[tuple, int] = {}
        for i, b in enumerate(self.bricks):
            part = self.part(b["part_id"])
            sx, sz = self._footprint(part, b["rot"])
            level_h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
            for cx in range(b["x"], b["x"] + sx):
                for cz in range(b["z"], b["z"] + sz):
                    for cy in range(b["y"], b["y"] + level_h):
                        voxels[(cx, cy, cz)] = i
        parent: dict[tuple, tuple] = {v: v for v in voxels}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for (cx, cy, cz) in voxels:
            for nb in ((cx + 1, cy, cz), (cx, cy + 1, cz), (cx, cy, cz + 1)):
                if nb in voxels:
                    union((cx, cy, cz), nb)
        groups: dict[tuple, set] = {}
        for v, brick_i in voxels.items():
            groups.setdefault(find(v), set()).add(brick_i)
        sizes = sorted((len(g) for g in groups.values()), reverse=True)
        return {"islands": len(sizes), "largest": sizes[0] if sizes else 0,
                "sizes": sizes[:8]}

    def add_step(self) -> None:
        """Termine l'étape de construction en cours (visible dans le timelapse)."""
        if self.bricks and len(self.steps) - 1 != len(self.bricks) - 1:
            self.steps.append(len(self.bricks))

    def _voxels(self):
        """Retourne (cellules par brique, index voxel -> brique)."""
        cells_per: list[list[tuple]] = []
        owner: dict[tuple, int] = {}
        for i, b in enumerate(self.bricks):
            part = self.part(b["part_id"])
            sx, sz = self._footprint(part, b["rot"])
            level_h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
            cells = [(cx, cy, cz)
                     for cx in range(b["x"], b["x"] + sx)
                     for cz in range(b["z"], b["z"] + sz)
                     for cy in range(b["y"], b["y"] + level_h)]
            cells_per.append(cells)
            for c in cells:
                owner[c] = i
        return cells_per, owner

    def floating_bricks(self) -> list[int]:
        """Indices des briques sans appui : ni support vertical, ni accolement
        (direct ou par chaîne) à une brique posée au sol."""
        if not self.bricks:
            return []
        cells_per, owner = self._voxels()
        reachable = {i for i, b in enumerate(self.bricks) if b["y"] == 0}
        stack = list(reachable)
        while stack:
            i = stack.pop()
            for (cx, cy, cz) in cells_per[i]:
                for nb in ((cx + 1, cy, cz), (cx - 1, cy, cz),
                           (cx, cy, cz + 1), (cx, cy, cz - 1),
                           (cx, cy + 1, cz), (cx, cy - 1, cz)):
                    j = owner.get(nb)
                    if j is not None and j not in reachable:
                        reachable.add(j)
                        stack.append(j)
        return [i for i in range(len(self.bricks)) if i not in reachable]

    def settle(self) -> int:
        """Repose les briques qui ne tiennent à rien (aucun support vertical,
        aucun accolement à une brique elle-même soutenue). Les briques tenues
        par leurs studs latéraux — planchers, toits, porte-à-faux volontaires —
        restent en place. Retourne le nombre de briques reposées."""
        floating = self.floating_bricks()
        if not floating:
            return 0
        cells_per, _ = self._voxels()
        # sommet atteint par colonne (x, z), en ignorant les flottantes
        tops: dict[tuple, int] = {}
        heights: dict[int, int] = {}
        for i, b in enumerate(self.bricks):
            if i in floating:
                continue
            part = self.part(b["part_id"])
            level_h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
            heights[i] = level_h
            for (cx, cy, cz) in cells_per[i]:
                if cy == b["y"] + level_h - 1:
                    tops[(cx, cz)] = max(tops.get((cx, cz), 0), cy + 1)
        moved = 0
        for i in sorted(floating):
            b = self.bricks[i]
            part = self.part(b["part_id"])
            sx, sz = self._footprint(part, b["rot"])
            level_h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
            cols = [(cx, cz) for cx in range(b["x"], b["x"] + sx)
                    for cz in range(b["z"], b["z"] + sz)]
            y_new = max((tops.get(c, 0) for c in cols), default=0)
            if y_new != b["y"]:
                b["y"] = y_new
                moved += 1
            for c in cols:
                tops[c] = y_new + level_h
        self._rebuild_occupied()
        return moved

    def _rebuild_occupied(self) -> None:
        self._occupied = {}
        for i, b in enumerate(self.bricks):
            part = self.part(b["part_id"])
            sx, sz = self._footprint(part, b["rot"])
            level_h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
            for cx in range(b["x"], b["x"] + sx):
                for cz in range(b["z"], b["z"] + sz):
                    for cy in range(b["y"], b["y"] + level_h):
                        self._occupied[(cx, cy, cz)] = i

    # ------------------------------------------------------------------ #
    @staticmethod
    def _footprint(part: dict, rot: int) -> tuple[int, int]:
        """Empreinte au sol en studs après rotation."""
        sx = max(1, round(part["studs_x"]))
        sz = max(1, round(part["studs_z"]))
        # les tuiles rondes etc. ont des empreintes fractionnaires : on
        # n'accepte que des pièces alignées sur la grille
        if rot in (90, 270):
            sx, sz = sz, sx
        return sx, sz

    def _check_collision(self, x, z, y, sx, sz, level_h, part=None):
        for cx in range(x, x + sx):
            for cz in range(z, z + sz):
                for cy in range(y, y + level_h):
                    if (cx, cy, cz) in self._occupied:
                        other = self._occupied[(cx, cy, cz)]
                        b = self.bricks[other]
                        raise CollisionError(
                            f"Collision en ({cx},{cy},{cz}) : ta pièce "
                            f"{part['id']} posée en ({x},{y},{z}) couvre "
                            f"x:{x}..{x+sx-1}, z:{z}..{z+sz-1}, y:{y}..{y+level_h-1} "
                            f"et chevauche {b['part_id']} posée en "
                            f"({b['x']},{b['y']},{b['z']})")

    # ------------------------------------------------------------------ #
    def to_ldraw(self, comments: str | None = None) -> str:
        lines = [
            f"0 {self.name}",
            f"0 Name: {self.name}.ldr",
            "0 Author: text2legoCAD",
            "0 BFC CERTIFY CC-WITEMPORARY",
            "",
        ]
        if comments:
            lines += [f"0 // {c}" for c in comments.splitlines()] + [""]
        step_starts = set(self.steps)
        for i, b in enumerate(self.bricks):
            lines += self._brick_lines(b)
            if (i + 1) in step_starts or i == len(self.bricks) - 1:
                lines.append("0 STEP")
                lines.append("")
        return "\n".join(lines) + "\n"

    def _brick_lines(self, b: dict) -> list[str]:
        part = self.part(b["part_id"])
        sx = part["studs_x"]
        sz = part["studs_z"]
        dx, dz = (sx, sz) if b["rot"] == 0 else (sz, sx)
        dx = max(dx, 1.0)
        dz = max(dz, 1.0)
        cx = (b["x"] + dx / 2.0 - 0.5) * STUD
        cz = (b["z"] + dz / 2.0 - 0.5) * STUD
        cy = -(b["y"] * LDU_PER_LEVEL) - _NOMINAL_H.get(part["kind"], 24) / 2.0
        rot = b["rot"]
        if rot == 0:
            mat = "1 0 0 0 1 0 0 0 1"
        elif rot == 90:
            mat = "0 0 1 0 1 0 -1 0 0"
        elif rot == 180:
            mat = "-1 0 0 0 1 0 0 0 -1"
        elif rot == 270:
            mat = "0 0 -1 0 1 0 1 0 0"
        else:
            raise ValueError(f"Rotation {rot} non supportée (0/90/180/270)")
        return [f"1 {b['color']} {cx:g} {cy:g} {cz:g} {mat} {b['part_id']}.dat"]

    # ------------------------------------------------------------------ #
    def save(self, path: str | Path, comments: str | None = None) -> Path:
        path = Path(path)
        path.write_text(self.to_ldraw(comments))
        return path

    def parts_summary(self) -> dict:
        """Liste de courses (id -> quantité)."""
        out: dict[str, int] = {}
        for b in self.bricks:
            key = f"{b['part_id']}"
            out[key] = out.get(key, 0) + 1
        return out

    def bounds(self) -> tuple[int, int, int, int]:
        """(min_x, min_z, max_x_exclusif, max_z_exclusif) en studs."""
        if not self.bricks:
            return (0, 0, 0, 0)
        xs, zs = [], []
        for b in self.bricks:
            sx, sz = self._footprint(self.part(b["part_id"]), b["rot"])
            xs += [b["x"], b["x"] + sx]
            zs += [b["z"], b["z"] + sz]
        return (min(xs), min(zs), max(xs), max(zs))
