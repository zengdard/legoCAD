#!/usr/bin/env python3
"""Serveur MCP "text2legocad" : expose la génération de sets LEGO et le
rendu vidéo à n'importe quel client MCP (Claude, DeepSeek, etc.).

Lancer : python3 tools/mcp_server.py          (stdio)
       : python3 tools/mcp_server.py --http 8377
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from fastmcp import FastMCP  # noqa: E402

from ldraw_model import (  # noqa: E402
    COLORS, CollisionError, LDrawModel, UnknownPartError,
)
import parts_index  # noqa: E402
import render as rend  # noqa: E402

mcp = FastMCP("text2legocad")


# ---------------------------------------------------------------------- #
# Session de construction itérative (workflow à la FreeCAD MCP) :
# le LLM pose les briques appel par appel, avec erreur immédiate et
# screenshot de l'état courant comme feedback visuel.

_SESSION: dict = {"model": None}


def _session() -> LDrawModel:
    if _SESSION["model"] is None:
        raise ValueError("Aucune session : appelle d'abord session_start.")
    return _SESSION["model"]


def _session_path() -> Path:
    m = _session()
    safe_name = "".join(c if c.isalnum() else "_" for c in m.name).strip("_") or "session"
    return PROJECT / "models" / f"{safe_name}_session.ldr"


def _session_flush() -> str:
    p = _session_path()
    _session().save(p)
    return str(p)


@mcp.tool
def session_start(name: str = "session") -> str:
    """Démarre une nouvelle session de construction (vide la session précédente).
    Construis ensuite brique par brique avec session_add_part."""
    _SESSION["model"] = LDrawModel(name)
    return json.dumps({"ok": True, "name": name, "message":
                       "Session démarrée. Pose les briques avec session_add_part, "
                       "termine par session_save puis render_video."})


@mcp.tool
def session_add_part(part_id: str, x: int, z: int, y: int = 0,
                     color: str = "4", rot: int = 0) -> str:
    """Pose UNE brique dans la session en cours.
    - part_id : id LDraw exact (trouvé via search_parts)
    - x, z : position en studs du coin de la pièce (avant rotation)
    - y : niveau vertical en PLAQUES (1 brique = 3, 1 plaque = 1)
    - color : code couleur LDraw (ex "4" rouge, "15" blanc, "2" vert, "0" noir)
    - rot : 0, 90, 180 ou 270
    En cas d'erreur (collision, pièce inconnue), corrige et réessaie : la
    session n'est pas perdue."""
    try:
        brick = _session().place(part_id, x, z, y, color, rot)
    except (CollisionError, UnknownPartError, ValueError) as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps({"ok": True, "brick": brick,
                       "n_bricks": len(_session().bricks),
                       "warnings": _session().warnings[-3:]})


@mcp.tool
def session_add_step() -> str:
    """Termine l'étape de construction en cours (visible dans la vidéo)."""
    _session().add_step()
    return json.dumps({"ok": True, "n_bricks": len(_session().bricks)})


@mcp.tool
def session_undo() -> str:
    """Annule la dernière brique posée."""
    m = _session()
    if not m.bricks:
        return json.dumps({"ok": False, "error": "Session vide"})
    b = m.bricks.pop()
    m._occupied = {}
    for i, bb in enumerate(m.bricks):
        part = m.part(bb["part_id"])
        sx, sz = LDrawModel._footprint(part, bb["rot"])
        level_h = max(1, { "brick": 24, "round": 24, "slope": 24, "cylinder": 24,
                           "technic": 24, "other": 24, "cone": 48,
                           "plate": 8, "tile": 8, "baseplate": 8 }
                      .get(part["kind"], 24) // 8)
        for cx in range(bb["x"], bb["x"] + sx):
            for cz in range(bb["z"], bb["z"] + sz):
                for cy in range(bb["y"], bb["y"] + level_h):
                    m._occupied[(cx, cy, cz)] = i
    return json.dumps({"ok": True, "removed": b, "n_bricks": len(m.bricks)})


@mcp.tool
def session_state() -> str:
    """État de la session : nom, nombre de briques, dimensions, dernière erreur."""
    m = _session()
    x0, z0, x1, z1 = m.bounds()
    return json.dumps({"name": m.name, "n_bricks": len(m.bricks),
                       "n_steps": len(m.steps) + 1 if m.bricks else 0,
                       "bounds_studs": [x0, z0, x1, z1],
                       "parts_used": m.parts_summary(),
                       "warnings": m.warnings[-5:]})


@mcp.tool
def session_screenshot(lat: float = 30, lon: float = 45) -> str:
    """Rend une image de l'état courant de la session (feedback visuel).
    Utilise-la après quelques briques pour vérifier l'allure du modèle."""
    m = _session()
    if not m.bricks:
        return json.dumps({"error": "Session vide, rien à rendre"})
    p = _session_flush()
    png = PROJECT / "renders" / f"{_session_path().stem}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    try:
        rend.render_image(Path(p), png, lat=lat, lon=lon)
    except RuntimeError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"png": str(png), "n_bricks": len(m.bricks)})


@mcp.tool
def session_save() -> str:
    """Sauvegarde le modèle de la session en un .ldr définitif (models/)."""
    m = _session()
    if not m.bricks:
        return json.dumps({"error": "Session vide"})
    safe_name = "".join(c if c.isalnum() else "_" for c in m.name).strip("_") or "model"
    final = PROJECT / "models" / f"{safe_name}.ldr"
    m.save(final)
    x0, z0, x1, z1 = m.bounds()
    return json.dumps({"ldr": str(final), "n_bricks": len(m.bricks),
                       "bounds_studs": [x0, z0, x1, z1],
                       "parts_used": m.parts_summary()})


@mcp.tool
def build_from_script(name: str, code: str, prompt: str = "") -> str:
    """Exécute un script Python de construction LEGO dans un sandbox isolé
    (timeout 120 s, imports réseau/système refusés). Le script a accès à :
    - model : LDrawModel -> model.place(part_id, x, z, y, color, rot),
      model.add_step() ; x,z en studs (coin), y en plaques (1 brique = 3)
    - find_parts(query) : recherche de pièces dans la bibliothèque LDraw
    - math ; pas d'open/eval/imports système
    Écris des boucles, des symétries, des fonctions : c'est le mode recommandé
    pour les formes libres. En cas d'erreur, corrige le code et relance.
    Retourne le chemin du .ldr, la liste de courses et les dimensions."""
    from sandbox_exec import run_sandbox
    return json.dumps(run_sandbox({"name": name, "code": code, "prompt": prompt}))


@mcp.tool
def build_screenshot(name: str, lat: float = 30, lon: float = 45) -> str:
    """Rend une image du modèle models/<name>.ldr (feedback visuel après
    build_from_script)."""
    ldr = PROJECT / "models" / f"{name}.ldr"
    if not ldr.exists():
        return json.dumps({"error": f"Modèle {name} introuvable"})
    png = PROJECT / "renders" / f"{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    try:
        rend.render_image(ldr, png, lat=lat, lon=lon)
    except RuntimeError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"png": str(png)})


@mcp.tool
def search_parts(query: str, family: str | None = None, limit: int = 15) -> str:
    """Cherche des pièces dans la bibliothèque LDraw complète (~23 000 pièces)
    par mots-clés de la description officielle ("brick 2 x 4", "slope 45",
    "tile 1 x 2", "cone", "wheel"...). family optionnelle parmi : brick,
    plate, tile, slope, round, cylinder, cone, baseplate, technic.
    Renvoie les ids EXACTS à utiliser dans session_add_part / generate_model."""
    results = parts_index.search(query, family=family, limit=limit)
    return json.dumps({"query": query, "n": len(results), "results": results})


@mcp.tool
def get_part(part_id: str) -> str:
    """Fiche complète d'une pièce LDraw : description, famille, hauteur."""
    info = parts_index.get(part_id)
    if not info:
        return json.dumps({"error": f"{part_id} introuvable"})
    return json.dumps(info)


def _model_from_spec(spec: dict) -> LDrawModel:
    """spec = {"name": str, "steps": [[brique, ...], ...]}
    brique = {"part": id, "x": int, "z": int, "y": int, "color": code, "rot": 0|90|180|270}"""
    model = LDrawModel(spec.get("name", "model"))
    for step in spec.get("steps", []):
        for b in step:
            model.place(
                part_id=str(b["part"]),
                x=int(b["x"]), z=int(b["z"]), y=int(b.get("y", 0)),
                color=str(b.get("color", "4")),
                rot=int(b.get("rot", 0)),
            )
        model.add_step()
    return model


@mcp.tool
def list_parts() -> str:
    """Catalogue des pièces disponibles (id, description, empreinte en studs,
    hauteur en unités brique) et des couleurs LDraw (code -> nom).
    Utilise ces ids EXACTEMENT dans generate_model."""
    parts = [
        {"id": p["id"], "desc": p["desc"], "kind": p["kind"],
         "footprint_studs": [p["studs_x"], p["studs_z"]],
         "height_brick_units": p["height_brick_units"]}
        for p in PARTS.values()
    ]
    return json.dumps({"parts": parts, "colors": COLORS}, ensure_ascii=False)


@mcp.tool
def generate_model(spec: dict) -> str:
    """Génère un fichier .ldr à partir d'une spécification structurée.
    spec = {"name": "nom_du_set",
            "steps": [ [ {"part": "3001", "x": 0, "z": 0, "y": 0, "color": "4", "rot": 0}, ... ], ... ]}
    - x, z : coordonnées en studs du coin de la pièce (avant rotation)
    - y : niveau vertical en PLAQUES (1 brique = 3 plaques, une plaque = 1)
    - color : code couleur LDraw (voir list_parts)
    - rot : 0, 90, 180 ou 270
    Chaque sous-liste de "steps" devient une étape visible dans la vidéo.
    Retourne le chemin du .ldr, la liste de courses et les dimensions."""
    try:
        model = _model_from_spec(spec)
    except (CollisionError, UnknownPartError, KeyError, ValueError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    name = spec.get("name", "model")
    ldr = PROJECT / "models" / f"{name}.ldr"
    model.save(ldr, comments=spec.get("description", ""))
    x0, z0, x1, z1 = model.bounds()
    return json.dumps({
        "ldr_path": str(ldr),
        "n_bricks": len(model.bricks),
        "n_steps": len(model.steps) + 1 if model.bricks else 0,
        "bounds_studs": [x0, z0, x1, z1],
        "parts_used": model.parts_summary(),
    }, ensure_ascii=False)


@mcp.tool
def solve_blueprint(blueprint: dict, time_limit: float = 45.0) -> str:
    """Mode solver : génère un modèle à partir d'un BLUEPRINT LEGO IR
    (composants : wall / tower / slab / box), le solver CP-SAT place les
    briques (schéma exact dans tools/lego_ir.py : BLUEPRINT_PROMPT).
    Retourne le rapport déterministe : pièces, stabilité, amas, steps,
    et la liste des problèmes à corriger dans le blueprint le cas échéant."""
    import lego_ir as ir
    import solver as sv
    try:
        bp, errors = ir.from_dict(blueprint)
        if errors:
            return json.dumps({"status": "INVALID_BLUEPRINT",
                               "issues": errors}, ensure_ascii=False)
        model, report = sv.solve_blueprint(bp, time_limit=time_limit)
        if model is None:
            return json.dumps(report, ensure_ascii=False)
        ldr = PROJECT / "models" / f"{bp.name or 'solver_model'}.ldr"
        model.save(ldr)
        report["ldr_path"] = str(ldr)
        return json.dumps(report, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool
def generate_solved(prompt: str, max_pieces: int = 300,
                    make_video: bool = False) -> str:
    """Mode solver complet : le prompt devient un blueprint (LLM archi-
    tecte), le solver CP-SAT place les briques, avec boucle de correction
    (2-3 tours). Nécessite DEEPSEEK_API_KEY. Retourne blueprint, rapport
    du solver, chemins .ldr / aperçu / vidéo."""
    import generate_solver as gs
    try:
        result = gs.generate(prompt, max_pieces=max_pieces,
                             make_video=make_video)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool
def render_preview(name: str, lat: float = 30, lon: float = 45) -> str:
    """Rend une image PNG du modèle <name>.ldr (généré par generate_model)."""
    ldr = PROJECT / "models" / f"{name}.ldr"
    if not ldr.exists():
        return json.dumps({"error": f"Modèle {name} introuvable"})
    png = PROJECT / "renders" / f"{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    try:
        rend.render_image(ldr, png, lat=lat, lon=lon)
    except RuntimeError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"png": str(png)})


@mcp.tool
def render_video(name: str, lat: float = 30, turntable: bool = True) -> str:
    """Produit la vidéo timelapse de construction (+ rotation 360° finale)
    du modèle <name>.ldr. Peut prendre plusieurs minutes."""
    ldr = PROJECT / "models" / f"{name}.ldr"
    if not ldr.exists():
        return json.dumps({"error": f"Modèle {name} introuvable"})
    try:
        mp4 = rend.build_video(ldr, PROJECT / "renders" / f"{name}.mp4",
                               lat=lat, turntable=turntable)
    except (RuntimeError, ValueError) as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"video": str(mp4)})


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--http") + 1]) if len(sys.argv) > sys.argv.index("--http") + 1 else 8377
        mcp.run(transport="http", host="127.0.0.1", port=port)
    else:
        mcp.run()
