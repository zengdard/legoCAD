#!/usr/bin/env python3
"""LEGO IR : représentation intermédiaire entre le LLM (architecte) et le
solver (constructeur).

Le LLM ne place JAMAIS de briques : il produit un blueprint JSON de
composants (murs, tours, dalles, boîtes) en coordonnées studs, avec des
objectifs globaux. Ce module :

  - parse et valide ce blueprint (validate -> liste d'erreurs en français,
    destinée à être renvoyée au LLM comme feedback déterministe) ;
  - découpe chaque composant en « régions » 3D sur la grille (ensembles de
    colonnes (x, z) à remplir du sol jusqu'à une hauteur, en plaques) :
    c'est le contrat passé au solver CP-SAT (tools/solver.py).

Unités : positions en studs, hauteurs de composants en NIVEAUX DE BRIQUES
(1 niveau = 3 plaques), ouvertures en plaques. Le sol est y=0 (repère
ldraw_model).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

LEVEL = 3  # plaques par niveau de brique

# Ensembles de briques autorisés par défaut (MVP : briques + plates 1xN/2xN).
DEFAULT_BRICKS_1 = ["3005", "3004", "3622", "3010", "3009", "3008"]        # 1x1..1x8
DEFAULT_BRICKS_2 = ["3003", "3002", "3001"]                                # 2x2..2x4
DEFAULT_PLATES_1 = ["3024", "3023", "3623", "3710"]                        # 1x1..1x4
DEFAULT_PLATES_2 = ["3022", "3021", "3020"]                                # 2x2..2x4

COMPONENT_TYPES = ("wall", "tower", "slab", "box")
ROOF_KINDS = ("none", "flat", "pitched", "conical")


@dataclass
class Opening:
    """Creux dans un mur : porte/fenêtre, en studs le long du mur + plaques."""
    kind: str          # "gate" | "window"
    offset: int        # distance en studs depuis le début du mur (côté x ou z)
    width: int         # largeur en studs le long du mur
    top: int           # hauteur en plaques (le creux va du sol/base à `top`)
    sill: int = 0      # pour une fenêtre : hauteur du dessous en plaques

    def levels(self) -> range:
        return range(self.sill, self.top)


@dataclass
class Component:
    type: str                       # wall | tower | slab | box
    x: int
    z: int
    width: int = 0                  # studs selon x
    depth: int = 0                  # studs selon z
    height: int = 3                 # niveaux de briques (walls/tower/box)
    color: str = "7"
    roof: str = "none"              # none | flat | pitched | conical
    floor: bool = False             # box : dalle au sol
    openings: list = field(default_factory=list)   # [Opening] (wall/box)
    pattern: str = "wall"           # variante de pattern (tools/patterns.py)
    cid: str = ""
    attach: dict = field(default_factory=dict)  # {"to": id, "side", "gap", "offset"}

    def height_plates(self) -> int:
        return self.height * LEVEL


@dataclass
class Blueprint:
    name: str = "model"
    terrain_width: int = 32
    terrain_depth: int = 32
    max_height: int = 24            # niveaux de briques max
    components: list = field(default_factory=list)  # [Component]
    objectives: dict = field(default_factory=lambda: {
        "max_pieces": 400, "min_stability": 0.8, "max_types": 12})
    palette: list = field(default_factory=list)     # codes LDraw autorisés


@dataclass
class Region:
    """Volume à remplir par le solver : colonnes (x, z) du sol (y_base,
    en plaques) jusqu'à y_top, creusées par `holes` (dict (x,z) -> niveaux
    interdits), briques autorisées et couleurs par niveau."""
    rid: str
    kind: str                       # wall | ring | slab
    cells: set                      # {(x, z)}
    y_base: int                     # plaques (0 = sol)
    y_top: int                      # plaques (exclu)
    allowed: dict                   # {(w, h): [part_id, ...]}  (h en plaques)
    colors: dict                    # {niveau plaque -> code couleur}
    holes: dict = field(default_factory=dict)
    roof: str = "none"
    comp: Component = None


# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------

def parse_openings(raw, depth, errors, ctx) -> list:
    out = []
    for i, o in enumerate(raw or []):
        if not isinstance(o, dict):
            errors.append(f"{ctx}: ouverture {i} doit être un objet")
            continue
        kind = o.get("kind", "window")
        if kind not in ("gate", "window"):
            errors.append(f"{ctx}: ouverture {i} kind inconnu ({kind!r})")
        off, w = int(o.get("offset", 0)), int(o.get("width", 2))
        top = int(o.get("top", LEVEL * 4))
        sill = int(o.get("sill", 0))
        if off < 0 or w <= 0:
            errors.append(f"{ctx}: ouverture {i} offset/width invalides")
            continue
        if kind == "window" and sill >= top:
            errors.append(f"{ctx}: fenêtre {i} sill >= top")
        out.append(Opening(kind, off, w, top, sill))
    return out


def _normalize_color(value: str, errors: list, ctx: str) -> str:
    """Accepte un code LDraw ('4') ou un nom de couleur ('Red'/'red') —
    les LLM produisent souvent le nom : on normalise vers le code."""
    value = str(value).strip()
    if value.isdigit():
        return value
    if not value:
        return "7"
    for code, info in _colors_index().items():
        if info["name"].lower() == value.lower():
            return code
    errors.append(f"{ctx} : couleur inconnue {value!r} (utilise un code "
                  f"LDraw ou un nom du catalogue)")
    return "7"


_COLORS: dict | None = None


def _colors_index() -> dict:
    global _COLORS
    if _COLORS is None:
        path = Path(__file__).resolve().parent.parent / "pieces_catalog.json"
        try:
            _COLORS = json.loads(path.read_text()).get("colors", {})
        except (OSError, ValueError):
            _COLORS = {}
    return _COLORS


def parse_component(raw, errors, idx) -> Component | None:
    ctx = f"composant #{idx}"
    if not isinstance(raw, dict):
        errors.append(f"{ctx} : doit être un objet")
        return None
    ctype = raw.get("type", "")
    if ctype not in COMPONENT_TYPES:
        errors.append(f"{ctx} : type inconnu {ctype!r} "
                      f"(attendu parmi {COMPONENT_TYPES})")
        return None
    comp = Component(
        type=ctype,
        x=int(raw.get("x", 0)), z=int(raw.get("z", 0)),
        width=int(raw.get("width", raw.get("w", 0))),
        depth=int(raw.get("depth", raw.get("d", 0))),
        height=int(raw.get("height", 3)),
        color=_normalize_color(raw.get("color", "7"), errors, ctx),
        roof=str(raw.get("roof", "none")),
        floor=bool(raw.get("floor", False)),
        pattern=str(raw.get("pattern", "wall")),
        cid=str(raw.get("id", f"{ctype}_{idx}")),
    )
    attach = raw.get("attach") or {}
    if not isinstance(attach, dict):
        errors.append(f"{ctx} ({comp.cid}) : attach doit être un objet")
    else:
        comp.attach = attach
    if comp.roof not in ROOF_KINDS:
        errors.append(f"{ctx} ({comp.cid}) : toit inconnu {comp.roof!r}")
    if comp.height < 1:
        errors.append(f"{ctx} ({comp.cid}) : height doit être >= 1")
    if ctype in ("tower",):
        if comp.width <= 0:
            comp.width = int(raw.get("size", 0))
            comp.depth = comp.width
        if comp.width < 4:
            errors.append(f"{ctx} ({comp.cid}) : tour de moins de 4 studs")
    elif ctype == "slab":
        comp.height = 1
        if comp.width < 1 or comp.depth < 1:
            errors.append(f"{ctx} ({comp.cid}) : slab avec width/depth nuls")
    else:  # wall / box
        if comp.width < 1 or comp.depth < 1:
            errors.append(f"{ctx} ({comp.cid}) : width/depth manquants")
    comp.openings = parse_openings(raw.get("openings"), comp.depth,
                                   errors, f"{ctx} ({comp.cid})")
    for o in comp.openings:
        span = comp.width if comp.depth <= comp.width else comp.depth
        if o.offset + o.width > span:
            errors.append(f"{ctx} ({comp.cid}) : ouverture déborde du mur "
                          f"({o.offset}+{o.width} > {span})")
        if o.top > comp.height_plates():
            errors.append(f"{ctx} ({comp.cid}) : ouverture plus haute que le mur")
    return comp


def from_dict(raw) -> tuple[Blueprint, list]:
    """Parse un blueprint JSON (dict) -> (Blueprint, erreurs)."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return Blueprint(), ["le blueprint doit être un objet JSON"]
    bp = Blueprint(
        name=str(raw.get("name", "model")),
        terrain_width=int(raw.get("terrain", {}).get("width",
                        raw.get("terrain_width", 32))),
        terrain_depth=int(raw.get("terrain", {}).get("depth",
                        raw.get("terrain_depth", 32))),
        max_height=int(raw.get("terrain", {}).get("max_height",
                       raw.get("max_height", 24))),
        objectives={**Blueprint().objectives,
                    **(raw.get("objectives") or {})},
        palette=[_normalize_color(c, errors, "palette")
                 for c in (raw.get("palette") or [])],
    )
    for i, rc in enumerate(raw.get("components") or []):
        comp = parse_component(rc, errors, i)
        if comp is not None:
            bp.components.append(comp)
    if not bp.components:
        errors.append("aucun composant dans le blueprint")
    errors.extend(resolve_layout(bp))
    errors.extend(validate(bp))
    return bp, errors


# ---------------------------------------------------------------------------
# Solver design : résolution des attachements (placement des modules)
# ---------------------------------------------------------------------------

_SIDES = ("+x", "-x", "+z", "-z")


def resolve_layout(bp: Blueprint) -> list:
    """Place les composants déclarés avec un attachement relatif
    (le LLM décrit, le code calcule les coordonnées) :
      {"to": "tower_1", "side": "+x"|"-x"|"+z"|"-z", "gap": 0, "offset": 0}
    - side : le composant est collé au côté indiqué de l'ancre ;
    - gap  : distance en studs le long de l'axe du côté ;
    - offset : décalage le long de l'ancre (perpendiculaire au côté).
    Un composant sans « to » garde ses coordonnées explicites (racine).
    Erreurs : ancre inconnue, side invalide, cycle d'attachements."""
    errors: list[str] = []
    by_id = {c.cid: c for c in bp.components}
    state: dict = {}          # cid -> "ok" | "err"
    resolving: set = set()

    def resolve(c: Component) -> bool:
        if c.cid in state:
            return state[c.cid] == "ok"
        if c.cid in resolving:
            errors.append(f"{c.cid} : attachement cyclique")
            state[c.cid] = "err"
            return False
        to = (c.attach or {}).get("to")
        if not to:
            state[c.cid] = "ok"
            return True
        if to not in by_id:
            errors.append(f"{c.cid} : attaché à un composant inconnu "
                          f"{to!r}")
            state[c.cid] = "err"
            return False
        resolving.add(c.cid)
        ok = resolve(by_id[to])
        resolving.discard(c.cid)
        if not ok:
            state[c.cid] = "err"
            return False
        anchor = by_id[to]
        side = c.attach.get("side", "+x")
        gap = int(c.attach.get("gap", 0))
        off = int(c.attach.get("offset", 0))
        if side == "+x":
            c.x = anchor.x + anchor.width + gap
            c.z = anchor.z + off
        elif side == "-x":
            c.x = anchor.x - gap - c.width
            c.z = anchor.z + off
        elif side == "+z":
            c.z = anchor.z + anchor.depth + gap
            c.x = anchor.x + off
        elif side == "-z":
            c.z = anchor.z - gap - c.depth
            c.x = anchor.x + off
        else:
            errors.append(f"{c.cid} : side inconnu {side!r} "
                          f"(attendu parmi {_SIDES})")
            state[c.cid] = "err"
            return False
        state[c.cid] = "ok"
        return True

    for c in bp.components:
        resolve(c)
    return errors


def _boxes_overlap(a: Component, b: Component) -> bool:
    return (a.x < b.x + b.width and b.x < a.x + a.width and
            a.z < b.z + b.depth and b.z < a.z + a.depth and
            a.height > 0 and b.height > 0)


def validate(bp: Blueprint) -> list:
    """Contrôles géométriques déterministes (feedback solver -> LLM)."""
    errors = []
    if bp.terrain_width < 4 or bp.terrain_depth < 4:
        errors.append("terrain trop petit (< 4 studs)")
    if bp.max_height < 1:
        errors.append("max_height doit être >= 1")
    for comp in bp.components:
        tag = comp.cid or comp.type
        if comp.x < 0 or comp.z < 0 or \
           comp.x + comp.width > bp.terrain_width or \
           comp.z + comp.depth > bp.terrain_depth:
            errors.append(f"{tag} : hors terrain "
                          f"({comp.x},{comp.z} + {comp.width}x{comp.depth} "
                          f"> {bp.terrain_width}x{bp.terrain_depth})")
        if comp.height > bp.max_height:
            errors.append(f"{tag} : hauteur {comp.height} > max_height "
                          f"{bp.max_height}")
    if bp.palette:
        for comp in bp.components:
            if comp.color not in bp.palette:
                errors.append(f"{comp.cid or comp.type} : couleur "
                              f"{comp.color} hors palette {bp.palette}")
    # non-recouvrement des empreintes (les composants peuvent se toucher,
    # pas se chevaucher)
    for i in range(len(bp.components)):
        for j in range(i + 1, len(bp.components)):
            a, b = bp.components[i], bp.components[j]
            if _boxes_overlap(a, b):
                hint = ""
                # cas fréquent : un slab/plancher posé sur le périmètre
                # d'un box au lieu de son intérieur
                for outer, inner in ((a, b), (b, a)):
                    if (inner.type == "slab" and
                            outer.x <= inner.x and outer.z <= inner.z and
                            inner.x + inner.width <= outer.x + outer.width and
                            inner.z + inner.depth <= outer.z + outer.depth):
                        hint = (f" — pour un plancher intérieur à "
                                f"{outer.cid or outer.type} : x={outer.x + 1}, "
                                f"z={outer.z + 1}, width={outer.width - 2}, "
                                f"depth={outer.depth - 2}")
                        break
                errors.append(f"{a.cid or a.type} et {b.cid or b.type} "
                              f"chevauchent leurs empreintes{hint}")
    # un composant d'un seul tenant : tout doit toucher le sol (MVP :
    # pas de pièces volantes par conception, chaque composant part de y=0)
    return errors


# ---------------------------------------------------------------------------
# Découpe en régions (contrat solver)
# ---------------------------------------------------------------------------

def _wall_cells(comp: Component) -> set:
    return {(x, z)
            for x in range(comp.x, comp.x + comp.width)
            for z in range(comp.z, comp.z + comp.depth)}


def _ring_cells(comp: Component) -> set:
    """Périmètre d'un rectangle (tour creuse, murs d'une boîte)."""
    x0, z0 = comp.x, comp.z
    x1, z1 = comp.x + comp.width - 1, comp.z + comp.depth - 1
    cells = set()
    for x in range(x0, x1 + 1):
        cells.add((x, z0))
        cells.add((x, z1))
    for z in range(z0, z1 + 1):
        cells.add((x0, z))
        cells.add((x1, z))
    return cells


def _apply_openings(comp: Component, cells: set) -> dict:
    """Creuse les ouvertures : (x, z) -> set(niveaux plaques interdits)."""
    holes: dict = {}
    if comp.openings and comp.width >= comp.depth:
        axis, base = "x", comp.z       # mur le long de x
    else:
        axis, base = "z", comp.x       # mur le long de z
    for o in comp.openings:
        for k in range(o.offset, o.offset + o.width):
            x, z = (comp.x + k, base) if axis == "x" else (base, comp.z + k)
            if (x, z) in cells:
                holes.setdefault((x, z), set()).update(o.levels())
    return holes


def allowed_parts_for(comp: Component, depth2: bool) -> dict:
    """{(largeur studs, hauteur plaques): [part_id]} selon le pattern."""
    from patterns import part_mix          # import local (évite les cycles)
    return part_mix(comp.pattern, depth2)


def _colors_per_level(comp: Component) -> dict:
    colors = {}
    for y in range(comp.height_plates()):
        if comp.pattern == "decorative":
            colors[y] = comp.color if (y // LEVEL) % 2 == 0 else "15"
        else:
            colors[y] = comp.color
    return colors


def region_for(comp: Component) -> list:
    """Composant -> une ou deux régions (corps + dalle de sol pour box)."""
    regions = []
    if comp.type == "slab":
        cells = _wall_cells(comp)
        allowed = allowed_parts_for(comp, min(comp.width, comp.depth) >= 2)
        regions.append(Region(comp.cid or "slab", "slab", cells, 0, LEVEL,
                              allowed, {0: comp.color}, comp=comp))
        return regions
    if comp.type == "wall":
        cells = _wall_cells(comp)
        holes = _apply_openings(comp, cells)
        allowed = allowed_parts_for(comp, comp.depth >= 2)
        regions.append(Region(comp.cid or "wall", "wall", cells, 0,
                              comp.height_plates(), allowed,
                              _colors_per_level(comp), holes, "none", comp))
        return regions
    if comp.type == "tower":
        cells = _ring_cells(comp)
        allowed = allowed_parts_for(comp, True)
        regions.append(Region(comp.cid or "tower", "ring", cells, 0,
                              comp.height_plates(), allowed,
                              _colors_per_level(comp), {}, comp.roof, comp))
        return regions
    if comp.type == "box":
        allowed = allowed_parts_for(comp, comp.depth >= 2)
        regions.append(Region(comp.cid or "box", "ring", _ring_cells(comp),
                              0, comp.height_plates(), allowed,
                              _colors_per_level(comp),
                              _apply_openings(comp, _ring_cells(comp)),
                              comp.roof, comp))
        if comp.floor:
            ring = _ring_cells(comp)
            inner = {(x, z)
                     for x in range(comp.x, comp.x + comp.width)
                     for z in range(comp.z, comp.z + comp.depth)} - ring
            regions.append(Region(comp.cid + "_floor", "slab", inner, 0,
                                  LEVEL, allowed_parts_for(comp, True),
                                  {0: comp.color}, comp=comp))
        return regions
    return regions


def regions(bp: Blueprint) -> list:
    out = []
    for comp in bp.components:
        out.extend(region_for(comp))
    return out


# ---------------------------------------------------------------------------
# Prompt LLM
# ---------------------------------------------------------------------------

BLUEPRINT_PROMPT = """Tu es un architecte LEGO. À partir de la demande, produis
UNIQUEMENT un objet JSON de blueprint (pas de briques : le solver les placera).

Schéma :
{
  "name": str,
  "terrain": {"width": 16..64, "depth": 16..64, "max_height": 4..24},
  "components": [
    {"type": "wall",  "id": "wall_n", "x": int, "z": int, "width": int,
     "depth": int, "height": int_niveaux_briques, "color": code,
     "pattern": "cheap"|"strong"|"decorative",
     "openings": [{"kind": "gate"|"window", "offset": int, "width": int,
                   "top": plaques, "sill": plaques}]},
    {"type": "tower", "id": "tower_1", "x": int, "z": int, "size": int(>=4),
     "height": int, "color": code, "roof": "conical"|"none"},
    {"type": "slab",  "id": "floor_1", "x": int, "z": int, "width": int,
     "depth": int, "color": code},
    {"type": "box",   "id": "house_1", "x": int, "z": int, "width": int,
     "depth": int, "height": int, "color": code, "floor": true,
     "roof": "pitched"|"flat"|"none",
     "openings": [{"kind": "gate"|"window", "offset": int, "width": int,
                   "top": plaques, "sill": plaques}]}
  ],
  "objectives": {"max_pieces": int, "min_stability": 0.8, "max_types": 12},
  "palette": ["codes LDraw autorisés"]
}

Règles :
- x, z : coin du composant en studs ; le composant doit tenir dans le terrain.
- Les composants ne se chevauchent PAS (ils peuvent se toucher) : une tour
  d'angle touche le bout d'un mur, sans le recouvrir.
- PLACEMENT RELATIF (recommandé) : au lieu de donner x/z, attache chaque
  composant à un autre : "attach": {"to": "id_ancre", "side": "+x"|"-x"|
  "+z"|"-z", "gap": 0, "offset": 0}. Le premier composant (racine) garde
  x/z explicites. Des composants attachés se touchent => structure connexe.
- "height" est en NIVEAUX DE BRIQUES (1 niveau = 3 plaques) ; "top"/"sill"
  des ouvertures sont en PLAQUES.
- Garde le blueprint SIMPLE : 2 à 10 composants maximum.
"""


if __name__ == "__main__":
    demo = {
        "name": "petit_chateau",
        "terrain": {"width": 24, "depth": 24, "max_height": 16},
        "components": [
            {"type": "tower", "id": "t1", "x": 0, "z": 0, "size": 6,
             "height": 8, "color": "72", "roof": "conical"},
            {"type": "tower", "id": "t2", "x": 14, "z": 0, "size": 6,
             "height": 8, "color": "72", "roof": "conical"},
            {"type": "wall", "id": "w1", "x": 6, "z": 2, "width": 8,
             "depth": 2, "height": 5, "color": "72",
             "openings": [{"kind": "gate", "offset": 2, "width": 4,
                           "top": 9}]},
        ],
        "palette": ["72", "15", "1"],
    }
    bp, errs = from_dict(demo)
    print("erreurs:", errs)
    for r in regions(bp):
        print(r.rid, r.kind, f"{len(r.cells)} cellules",
              f"y {r.y_base}..{r.y_top}", "trous:", len(r.holes))
