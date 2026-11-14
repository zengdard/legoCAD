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


def design_flags(model, report: dict | None = None) -> list[dict]:
    """Anti-patterns observés dans les échecs de BrickBench (GLM, Muse, …).

    Ce ne sont pas des erreurs de validité : un modèle peut être « valide »
    et être un tapis de plaques 1×1. Chaque drapeau est une **alerte de
    design**, affichée sans bloquer la génération.
    """
    from collections import Counter
    report = report or {}
    bricks = list(getattr(model, "bricks", []))
    total = len(bricks) or 1
    counts = Counter(str(b["part_id"]) for b in bricks)
    top_id, top_n = counts.most_common(1)[0] if counts else ("", 0)
    top_share = top_n / total
    tiny = ("3024", "3070b", "6141", "98138", "4073", "54200")
    tiny_n = sum(counts[p] for p in tiny)
    tiles = sum(1 for b in bricks
                if str(model.part(b["part_id"]).get("kind")) == "tile")
    pieces = int(report.get("pieces", total) or total)
    islands = int(report.get("islands", 0) or 0)
    flags = []

    def add(code, detail, severity="warning"):
        flags.append({"code": code, "severity": severity,
                      "detail": detail})

    if top_share > 0.60:
        add("type_dominant",
            f"{top_id} = {top_share:.0%} des pièces (seuil 60 %)")
    if tiny_n / total > 0.40:
        add("trop_de_1x1",
            f"{tiny_n / total:.0%} de pièces 1×1 (seuil 40 %)")
    if tiles / total > 0.50:
        add("trop_de_tuiles",
            f"{tiles / total:.0%} de tuiles (seuil 50 %)")
    if islands > 10:
        add("composants_eclates",
            f"{islands} composants (seuil 10 ; une scène vise 2–6)",
            "error")
    if 395 <= pieces <= 405:
        add("plancher_de_pieces",
            f"{pieces} pièces : proche du plancher 400, risque de remplissage")
    # socle vide : colonnes du socle sans aucune pièce au sol
    if bricks:
        xs = [b["x"] for b in bricks]
        zs = [b["z"] for b in bricks]
        area = (max(xs) - min(xs) + 1) * (max(zs) - min(zs) + 1)
        ground = set()
        for b in bricks:
            if b["y"] != 0:
                continue
            sx, sz = model._footprint(model.part(b["part_id"]), b["rot"])
            for dx in range(sx):
                for dz in range(sz):
                    ground.add((b["x"] + dx, b["z"] + dz))
        if area and 1 - len(ground) / area > 0.50:
            add("socle_vide",
                f"{1 - len(ground) / area:.0%} de l'empreinte sans pièce au sol")
    return flags


def variety(model, report: dict | None = None) -> dict:
    """Variété de vocabulaire : types, entropie, part du type dominant.

    BrickBench montre que les bons Sets utilisent 47–69 types de pièces ;
    en dessous de 20, le modèle se rabat sur des plaques.
    """
    import math
    from collections import Counter
    bricks = list(getattr(model, "bricks", []))
    counts = Counter(str(b["part_id"]) for b in bricks)
    total = sum(counts.values()) or 1
    entropy = -sum((n / total) * math.log(n / total + 1e-12)
                   for n in counts.values())
    max_entropy = math.log(len(counts)) if len(counts) > 1 else 1.0
    return {"types": len(counts),
            "entropy": round(entropy / max_entropy, 3) if max_entropy else 0.0,
            "dominant_share": round((counts.most_common(1)[0][1] / total)
                                    if counts else 0.0, 3),
            "target_types": "25–50 pour une scène de 600–1500 pièces"}


def validity(model, report: dict | None = None,
             collisions: int = 0, max_components: int = 1) -> dict:
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
    if not (1 <= components <= max_components):
        reasons.append(f"{components} composant(s) (max {max_components})")
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
    flags = design_flags(model, report)
    if flags:
        checks.append({"name": "Anti-patterns de design",
                       "ok": False,
                       "detail": ", ".join(f["code"] for f in flags)})
    return {"overall": round(overall, 3), "values": values,
            "checks": checks, "weights": WEIGHTS, "validity": val,
            "flags": flags, "variety": variety(model, report),
            "grade": ("A" if overall >= 0.9 else "B" if overall >= 0.8
                      else "C" if overall >= 0.65 else "D")}


def summary_line(sc: dict) -> str:
    return (f"score {sc['overall']:.2f} ({sc['grade']}) — "
            + ", ".join(f"{k} {v:.2f}" for k, v in sc["values"].items()))
