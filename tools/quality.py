#!/usr/bin/env python3
"""Score de qualité d'un modèle : le tableau de bord d'un set « réel ».

Aucun critère ne suffit seul. On agrège :

  - constructibilité : couverture du volume, un seul amas, aucune pièce
    non attachée, ordre de montage valide ;
  - stabilité : `min_stability` (le maillon faible) ;
  - disponibilité : couples pièce/couleur observés dans de vrais sets ;
  - réalisme : similarité de la répartition des pièces avec celle des sets
    officiels (data/part_colors.json) ;
  - lisibilité : nombre d'étapes et de pièces par étape.

Le score global est une moyenne pondérée : la constructibilité et la
stabilité dominent, car un beau modèle qui s'effondre n'a aucune valeur.
"""
from __future__ import annotations

WEIGHTS = {
    "buildability": 0.30,
    "stability": 0.22,
    "coverage": 0.18,
    "availability": 0.15,
    "realism": 0.08,
    "instructions": 0.07,
}


def validity(model, report: dict | None = None,
             collisions: int = 0) -> dict:
    """Contrat de validité « BrickBench » : pièces réelles, pas de collision,
    stable, un seul composant connexe, et constructible dans l'ordre.

    C'est la définition partagée par BrickGPT / BrickNet / BrickBench :
    un modèle qui échoue ici n'est pas publiable, même s'il est joli.
    """
    report = report or {}
    parts = int(report.get("pieces", len(getattr(model, "bricks", []))))
    components = int(report.get("islands", 0) or 0)
    unsupported = report.get("unsupported") or []
    stable = float(report.get("min_stability", 0.0)) >= 0.8 and not unsupported
    build_ok = not (report.get("build_errors") or [])
    reasons = []
    if parts <= 0:
        reasons.append("aucune pièce")
    if collisions:
        reasons.append(f"{collisions} collision(s)")
    if components != 1:
        reasons.append(f"{components} composant(s) au lieu de 1")
    if not stable:
        reasons.append("instable ou pièces non attachées")
    if not build_ok:
        reasons.append("ordre de montage invalide")
    return {"valid": not reasons, "parts": parts,
            "components": components, "collisions": collisions,
            "stable": stable, "buildable": build_ok, "reasons": reasons}


def score(model, report: dict, bom_meta: dict | None = None,
          availability: dict | None = None) -> dict:
    report = report or {}
    coverage = float(report.get("coverage", 0.0))
    islands = int(report.get("islands", 0) or 0)
    unsupported = report.get("unsupported") or []
    build_errors = report.get("build_errors") or []
    stable = float(report.get("min_stability", 0.0))

    build_ok = (coverage >= 0.999 and islands <= 1 and not unsupported
                and not build_errors and report.get("pieces", 0) > 0)
    buildability = 1.0 if build_ok else 0.0
    if not build_ok and report.get("pieces", 0) > 0:
        # crédit partiel : le volume est couvert mais il reste un amas
        buildability = 0.5 * coverage if coverage > 0.98 else 0.0

    avail = availability or (bom_meta or {}).get("availability") or {}
    availability = 1.0 if not avail.get("checked") else \
        float(avail.get("score", 0.0))

    steps = int(report.get("build_steps", 0) or 0)
    pieces = int(report.get("pieces", 0) or 0)
    per_step = pieces / steps if steps else pieces
    instructions = 1.0 if 2 <= per_step <= 16 else 0.6 if per_step <= 24 else 0.3

    realism = float((bom_meta or {}).get("mix_similarity", 0.0))

    values = {
        "buildability": round(buildability, 3),
        "stability": round(stable, 3),
        "coverage": round(coverage, 3),
        "availability": round(availability, 3),
        "realism": round(realism, 3),
        "instructions": round(instructions, 3),
    }
    overall = sum(values[k] * WEIGHTS[k] for k in WEIGHTS)

    val = validity(model, report, collisions=int(report.get("collisions", 0)))
    checks = [
        {"name": "Valide (BrickBench)", "ok": val["valid"],
         "detail": "pièces, collisions, stabilité, un bloc"},
        {"name": "Volume couvert", "ok": coverage >= 0.999,
         "detail": f"{coverage:.1%} des voxels"},
        {"name": "Un seul bloc", "ok": islands <= 1,
         "detail": f"{islands} amas"},
        {"name": "Pièces attachées", "ok": not unsupported,
         "detail": f"{len(unsupported)} non attachée(s)"},
        {"name": "Ordre de montage", "ok": not build_errors,
         "detail": f"{len(build_errors)} erreur(s)"},
        {"name": "Stabilité", "ok": stable >= 0.8,
         "detail": f"min {stable:.2f}"},
        {"name": "Pièces disponibles", "ok": availability >= 0.9,
         "detail": f"{availability:.0%} des couples observés"},
        {"name": "Allure des sets", "ok": realism >= 0.5,
         "detail": f"similarité {realism:.2f}"},
    ]
    fam = (report.get("connectors") or {})
    if any(k != "stud" for k in fam):
        extra = ", ".join(f"{k}:{v}" for k, v in fam.items() if k != "stud")
        checks.append({"name": "Connecteurs non-stud",
                       "ok": True,
                       "detail": f"{extra} (non modélisés)"})
    return {"overall": round(overall, 3), "values": values,
            "checks": checks, "weights": WEIGHTS, "validity": val,
            "grade": ("A" if overall >= 0.9 else "B" if overall >= 0.8
                      else "C" if overall >= 0.65 else "D")}


def summary_line(sc: dict) -> str:
    return (f"score {sc['overall']:.2f} ({sc['grade']}) — "
            + ", ".join(f"{k} {v:.2f}" for k, v in sc["values"].items()))
