#!/usr/bin/env python3
"""Exécute un script de volume fourni par un LLM, en sous-processus borné.

Le script reçoit une `VoxelGrid` et doit définir `build()` qui retourne la
grille. Aucun import n'est nécessaire (math est injecté) ; les primitives
couvrent les formes utiles. Le résultat est sérialisé en JSON.

Usage : python3 voxel_runner.py <spec.json> <result.json>
  spec   = {"name": str, "code": str}
  result = {"ok": bool, "error": str?, "grid": {...}?, "stats": {...}?}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

MAX_CELLS = 200_000
MAX_DIM = 96


def run(spec: dict) -> dict:
    import math
    import voxel
    from voxel import VoxelGrid

    try:
        code = str(spec.get("code") or "")
        if not code.strip():
            raise ValueError("script vide")
        if "import " in code:
            # les primitives et math suffisent ; un import est presque
            # toujours une tentative d'accès hors du bac à sable
            raise ValueError("les imports sont interdits : utilise les "
                             "primitives de VoxelGrid et math")
        safe_builtins = {
            "range": range, "len": len, "min": min, "max": max, "abs": abs,
            "int": int, "float": float, "round": round, "sum": sum,
            "enumerate": enumerate, "zip": zip, "sorted": sorted,
            "list": list, "tuple": tuple, "dict": dict, "set": set,
            "bool": bool, "str": str, "print": print, "pow": pow,
            "True": True, "False": False, "None": None,
        }
        env = {"__builtins__": safe_builtins, "VoxelGrid": VoxelGrid,
               "grid": VoxelGrid(), "math": math,
               "BOX": VoxelGrid.box, "COLORS": voxel.CHAR_COLORS}
        exec(compile(code, "<voxel_script>", "exec"), env)   # noqa: S102
        build = env.get("build")
        if not callable(build):
            raise ValueError("le script doit définir une fonction build()")
        result = build()
        if not isinstance(result, VoxelGrid):
            raise ValueError("build() doit retourner un VoxelGrid")
        grid = result.normalize()
        if grid.count() == 0:
            raise ValueError("le volume est vide")
        sx, sy, sz = grid.size()
        if max(sx, sy, sz) > MAX_DIM:
            raise ValueError(f"volume trop grand ({sx}×{sy}×{sz}, max "
                             f"{MAX_DIM} par côté)")
        if grid.count() > MAX_CELLS:
            raise ValueError(f"trop de voxels ({grid.count()} > {MAX_CELLS})")
        return {"ok": True, "grid": grid.to_dict(),
                "stats": {"voxels": grid.count(), "size": [sx, sy, sz]}}
    except Exception as exc:                                # feedback LLM
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: voxel_runner.py spec.json result.json")
    spec = json.loads(Path(sys.argv[1]).read_text())
    res = run(spec)
    Path(sys.argv[2]).write_text(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
