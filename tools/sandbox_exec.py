#!/usr/bin/env python3
"""Lance le runner de sandbox en sous-processus borné dans le temps.

Séparé du serveur MCP pour garder chaque fichier lisible : la commande est
une liste d'arguments constante, sans interpréteur de commandes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 120


def run_sandbox(spec: dict) -> dict:
    """Écrit la spec, exécute sandbox_runner.py, retourne son résultat JSON."""
    spec_path = PROJECT / "out" / "_sandbox_spec.json"
    res_path = PROJECT / "out" / "_sandbox_result.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, ensure_ascii=False))
    res_path.unlink(missing_ok=True)
    try:
        res = subprocess.run(
            ["python3", "tools/sandbox_runner.py", str(spec_path), str(res_path)],
            capture_output=True, text=True, timeout=TIMEOUT_S,
            cwd=str(PROJECT), shell=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout : script trop long (max {TIMEOUT_S} s)"}
    if not res_path.exists():
        return {"ok": False, "error": "Le sandbox a crashé",
                "sandbox_stderr": res.stderr[-800:]}
    return json.loads(res_path.read_text())
