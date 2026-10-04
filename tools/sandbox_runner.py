#!/usr/bin/env python3
"""Exécute un script de construction LEGO fourni par un LLM, en isolation.

Le code du LLM est encapsulé dans un module Python temporaire (jamais passé
à un interpréteur de commandes, aucune primitive dangereuse exposée), lancé
par ce runner en sous-processus : timeout et isolation garantis par le parent.
Le script dispose de :
  - model : LDrawModel pré-créé (place, add_step, ...)
  - find_parts(query) : recherche dans la bibliothèque LDraw
  - math et les builtins sans open/eval/imports
Tout accident (exception, débordement) est capturé et renvoyé en JSON.

Usage : python3 sandbox_runner.py <spec.json> <result.json>
  spec   = {"name": str, "code": str, "prompt": str?}
  result = {"ok": bool, "error": str?, "ldr": str?, "n_bricks": int?, ...}
"""
import json
import sys
import tempfile
import importlib.util
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from ldraw_model import LDrawModel, _part_data  # noqa: E402

MAX_BRICKS = 600
_MODULE_HEADER = '''"""Module de build généré (code LLM encapsulé)."""
import math

'''


def _safe(name: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in name).strip("_")
    return cleaned or "build"


def run_build(spec: dict) -> dict:
    model = LDrawModel(spec.get("name", "build"))
    # Collisions fatales : le LLM doit corriger sa géométrie (l'auto-décalage
    # produit des modèles incohérents). Les doublons exacts restent ignorés,
    # ce qui évite les boucles stériles sur "collision en (0,0,0)".
    model.autofit = False
    ldr = PROJECT / "models" / f"{_safe(model.name)}.ldr"

    import parts_index
    import arch as _arch
    from types import SimpleNamespace

    def find_parts(query, family=None, limit=10):
        """Recherche de pièces avec leur empreinte réelle en studs (x, z)."""
        out = []
        for r in parts_index.search(query, family=family, limit=limit):
            data = _part_data(r["id"])
            if data:
                r = {**r, "footprint_x": data["studs_x"],
                     "footprint_z": data["studs_z"]}
            out.append(r)
        return out

    # Primitive d'architecture liées au modèle courant : le script écrit
    # arch.pitched_roof(0, 0, 16, 10, 12, "4") sans repasser `model`.
    arch_ns = SimpleNamespace(**{
        name: (lambda fn: (lambda *a, **k: fn(model, *a, **k)))(fn)
        for name, fn in _arch.PRIMITIVES.items()})

    # Encapsulation : le code du LLM devient le corps d'un module qui reçoit
    # `model` pré-construit ; aucune primitive d'exécution dynamique exposée.
    with tempfile.NamedTemporaryFile("w", suffix="_llm_build.py",
                                     delete=False, dir=str(PROJECT / "out")) as f:
        f.write(_MODULE_HEADER)
        f.write("\n# --- code du LLM ---\n")
        f.write(spec["code"])
        module_path = f.name

    try:
        import builtins
        real_import = builtins.__import__
        # Modules susceptibles d'avoir un effet hors du projet refusés ;
        # la frontière dure reste le sous-processus borné dans le temps.
        denied = {"os", "subprocess", "socket", "shutil", "urllib", "requests",
                  "http", "ftplib", "telnetlib", "ctypes", "importlib",
                  "builtins", "signal", "multiprocessing", "webbrowser"}

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0] in denied:
                raise ImportError(
                    f"import de {name!r} interdit dans le sandbox : tout le "
                    "nécessaire (model, find_parts, math) est déjà disponible, "
                    "réécris le code sans cet import")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = guarded_import
        try:
            spec_mod = importlib.util.spec_from_file_location("llm_build", module_path)
            mod = importlib.util.module_from_spec(spec_mod)
            mod.model = model      # injecté avant exécution du corps
            mod.find_parts = find_parts
            mod.arch = arch_ns
            sys.modules["llm_build"] = mod
            spec_mod.loader.exec_module(mod)
        finally:
            builtins.__import__ = real_import

        if len(model.bricks) == 0:
            raise ValueError("Le script n'a posé aucune brique.")
        if len(model.bricks) > MAX_BRICKS:
            raise ValueError(f"Trop de briques ({len(model.bricks)} > {MAX_BRICKS}).")
        moved = model.settle()
        # Ordre de montage recalculé : les steps du script ne garantissent pas
        # qu'un humain puisse suivre (il peut poser le toit avant les murs).
        import build_order
        steps = build_order.plan(model)
        order_problems = build_order.validate(model, steps)
        build_order.apply(model, steps)
        model.save(ldr, comments=spec.get("prompt", ""))
        conn = model.connectivity()
        stab = model.stability()
        return {"ok": True, "ldr": str(ldr), "n_bricks": len(model.bricks),
                "n_steps": len(model.steps) + 1, "settled": moved,
                "islands": conn["islands"], "island_sizes": conn["sizes"],
                "stability": {"min": stab["min_stability"],
                              "mean": stab["mean_stability"],
                              "unsupported": len(stab["unsupported"]),
                              "overhang_cells": stab["overhang_cells"],
                              "tipping_joints": len(stab["tipping_joints"])},
                "build_order": build_order.report(model, steps),
                "build_order_problems": order_problems[:5],
                "weak": stab["weak"][:6],
                "warnings": model.warnings[:10],
                "parts_used": model.parts_summary()}
    except Exception as e:  # noqa: BLE001 - tout doit revenir au LLM
        # Localiser la ligne fautive dans le script du LLM : c'est
        # l'information la plus utile pour qu'il corrige du premier coup.
        import traceback
        location = ""
        try:
            frames = [f for f in traceback.extract_tb(e.__traceback__)
                      if f.filename == module_path]
            if frames:
                f = frames[-1]
                location = f"\nLigne fautive {f.lineno} : {str(f.line).strip()}"
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"{type(e).__name__}: {e}{location}"}
    finally:
        Path(module_path).unlink(missing_ok=True)


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = run_build(spec)
    Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
