#!/usr/bin/env python3
"""Client autonome texte -> LEGO via LLM (architecte) + solver CP-SAT
(constructeur) : usage C du README.

Le LLM produit un BLUEPRINT (composants, pas de briques — tools/lego_ir.py),
le solver CP-SAT place les briques (tools/solver.py). Chaque problème
détecté (blueprint invalide, région insatisfiable, brique sans appui) est
renvoyé au LLM comme feedback déterministe pour correction (2-3 tours).

  export DEEPSEEK_API_KEY=sk-...
  python3 tools/generate_solver.py "un château médiéval avec deux tours"
  python3 tools/generate_solver.py "..." --max-pieces 200 --no-video
  python3 tools/generate_solver.py "..." --no-llm --blueprint bp.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import lego_ir as ir          # noqa: E402
import solver as sv           # noqa: E402
import render as rend         # noqa: E402

MAX_ROUNDS = 5


def _client():
    from openai import OpenAI
    import os
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY manquante (ou utilise "
                         "--no-llm --blueprint fichier.json)")
    return OpenAI(api_key=key, base_url="https://api.deepseek.com")


def _ask(client, messages) -> dict:
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.6,
        max_tokens=2000,
    )
    return json.loads(resp.choices[0].message.content)


def ask_blueprint(client, prompt: str, max_pieces: int) -> dict:
    messages = [
        {"role": "system", "content": ir.BLUEPRINT_PROMPT + "\n\n"
         + "Patterns disponibles :\n" + _patterns_help()
         + f"\nContraintes globales : maximum {max_pieces} pièces ; "
           "garde le blueprint dans le terrain et simple."},
        {"role": "user", "content": prompt},
    ]
    return _ask(client, messages), messages


def _patterns_help() -> str:
    import patterns as pt
    return pt.describe()


def generate(prompt: str, max_pieces: int = 300, make_video: bool = True,
             blueprint_file: str | None = None, time_limit: float = 45.0):
    """Boucle LLM <-> solver. Retourne le dict résultat final."""
    if blueprint_file:
        raw = json.loads(Path(blueprint_file).read_text())
        messages = None
    else:
        client = _client()
        raw, messages = ask_blueprint(client, prompt, max_pieces)
        raw.setdefault("objectives", {})["max_pieces"] = max_pieces

    model = None
    report = {}
    for round_no in range(1, MAX_ROUNDS + 1):
        bp, errors = ir.from_dict(raw)
        if errors:
            feedback = ("Blueprint invalide, corrige-le et renvoie le JSON "
                        "complet corrigé :\n- " + "\n- ".join(errors))
        else:
            print(f"[tour {round_no}] solve du blueprint "
                  f"({len(bp.components)} composants)...", flush=True)
            model, report = sv.solve_blueprint(bp, time_limit=time_limit)
            if report["status"] == "OK":
                break
            feedback = ("Le solver a rejeté le blueprint, corrige-le et "
                        "renvoie le JSON complet corrigé :\n- "
                        + "\n- ".join(report["issues"]))
        print(f"[tour {round_no}] feedback au LLM :\n{feedback}", flush=True)
        if messages is None:
            break
        messages = messages + [
            {"role": "assistant", "content": json.dumps(raw,
                                                        ensure_ascii=False)},
            {"role": "user", "content": feedback},
        ]
        raw = _ask(client, messages)

    result = {"blueprint": raw, "report": report}
    if model is None:
        result["error"] = "aucun modèle valide après " \
                          f"{MAX_ROUNDS} tours"
        return result

    name = bp.name or "solver_model"
    ldr = PROJECT / "models" / f"{name}.ldr"
    model.save(ldr)
    png = PROJECT / "renders" / f"{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    print("[rendu] aperçu...", flush=True)
    rend.render_image(ldr, png, lat=30, lon=45)
    result.update({"ldr": str(ldr), "preview": str(png),
                   "n_bricks": len(model.bricks),
                   "parts_used": model.parts_summary()})
    if make_video:
        print("[rendu] vidéo (timelapse + 360°)...", flush=True)
        mp4 = rend.build_video(ldr, PROJECT / "renders" / f"{name}.mp4",
                               lat=30)
        result["video"] = str(mp4)
    return result


def main():
    ap = argparse.ArgumentParser(
        description="texte -> blueprint LLM -> solver CP-SAT -> vidéo")
    ap.add_argument("prompt", nargs="?", default="")
    ap.add_argument("--max-pieces", type=int, default=300)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-llm", action="store_true",
                    help="nécessite --blueprint (test sans clé API)")
    ap.add_argument("--blueprint", default=None,
                    help="fichier JSON de blueprint (bypass le LLM)")
    ap.add_argument("--time-limit", type=float, default=45.0,
                    help="budget CP-SAT par région (s)")
    ap.add_argument("--out", default=None, help="fichier JSON de résultat")
    args = ap.parse_args()

    if args.blueprint:
        result = generate("", max_pieces=args.max_pieces,
                          make_video=not args.no_video,
                          blueprint_file=args.blueprint,
                          time_limit=args.time_limit)
    elif args.no_llm:
        ap.error("--no-llm nécessite --blueprint fichier.json")
    else:
        result = generate(args.prompt, max_pieces=args.max_pieces,
                          make_video=not args.no_video,
                          time_limit=args.time_limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(
            json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
