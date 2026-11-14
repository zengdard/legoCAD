#!/usr/bin/env python3
"""Client text-to-LEGO par génération de code (approche Blender MCP / OpenSCAD) :

    prompt -> DeepSeek écrit un script Python (API LDrawModel)
           -> sandbox l'exécute (timeout, imports refusés)
           -> erreurs renvoyées au modèle, correction, relance (max 3 tours)
           -> .ldr -> aperçu -> vidéo

Prérequis : export DEEPSEEK_API_KEY=sk-...
Usage :
    python3 tools/generate_script.py "un château avec deux tours et un pont"
    python3 tools/generate_script.py "..." --rounds 4 --no-video
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from openai import OpenAI  # noqa: E402

from sandbox_exec import run_sandbox  # noqa: E402
import render as rend  # noqa: E402

CODER_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
VISION_MODEL = os.environ.get("DEEPSEEK_VISION_MODEL", "deepseek-flash")

SYSTEM_PROMPT = """Tu construis des modèles LEGO en écrivant un script Python.
Le script s'exécute avec une variable `model` pré-créée (LDrawModel) et une
fonction `find_parts(query)` qui cherche dans la bibliothèque LDraw (23 000
pièces). `math` est importé. N'IMPORTE rien d'autre : pas d'os, d'open, de
sys, de pathlib — tout le nécessaire est déjà fourni (écris en Python pur).

PIÈCES — ATTENTION À LA CONVENTION DE NOMMAGE (source d'erreur n°1) :
dans le nom « Brick A x B », A est la PROFONDEUR (z) et B la LARGEUR (x).
Une « Brick 2 x 4 » (3001) posée en rot=0 occupe donc 4 studs en x et
2 studs en z. Empreintes réelles (rot=0) :
    3005 Brick 1x1   : 1x 1z        3004 Brick 1x2   : 2x 1z
    3622 Brick 1x3   : 3x 1z        3010 Brick 1x4   : 4x 1z
    3003 Brick 2x2   : 2x 2z        3001 Brick 2x4   : 4x 2z
    3008 Brick 2x8   : 8x 2z        3020 Plate 2x4   : 4x 2z
    3023 Plate 1x2   : 2x 1z        3024 Plate 1x1   : 1x 1z
    3039 Slope 2x2   : 2x 2z        3037 Slope 2x4   : 4x 2z
Avec rot=90 ou 270, x et z sont échangés. find_parts() renvoie l'empreinte
exacte (footprint_x, footprint_z) : vérifie-la en cas de doute.

PRIMITIVES D'ARCHITECTURE — OBLIGATOIRES pour ces formes, ne les code jamais
à la main (tu te tromperais dans les décalages) :
Bâtiments :
- arch.pitched_roof(x, z, w, d, y, color, ridge="x")
    Toit à deux pans avec rives en pente et faîtière (ridge="z" pour tourner).
- arch.pyramid_roof(x, z, size, y, color)
    Toit pyramidal / conique d'une tour (size paire : 4 ou 6).
- arch.crenellate(x, z, w, d, y, color, period=2)
    Créneaux sur le pourtour d'un chemin de ronde.
- arch.stairs(x, z, height, color, direction="+z")
    Escalier.
Véhicules :
- arch.hull(x, z, w, d, layers, color, y=0)
    Fuselage : corps plein avec nez effilé vers -z (l'avant).
- arch.wing(x, z, w, d, y, color)
    Aile plate à bord d'attaque en pente. DOIT chevaucher le fuselage d'au
    moins un stud, sinon elle sera détachée.
- arch.cockpit(x, z, w, d, y, color)
    Verrière en pente (utilise une couleur transparente : 43, 47).
- arch.engine(x, z, w, d, y, color, glow="43")
    Propulseur avec tuyère lumineuse, à poser au cul du fuselage.

Un VAISSEAU réussi = arch.hull au centre, puis deux arch.wing symétriques qui
chevauchent le fuselage, un arch.cockpit sur le dessus avant, et un ou deux
arch.engine à l'arrière (z = z + longueur du fuselage).

STRUCTURES — comment construire :
- Une TOUR est une COQUE : quatre murs (slab de profondeur 1), jamais un pavé
  plein (slab(w, d) avec layers élevés gaspille des centaines de pièces).
- Un BÂTIMENT : dalle au sol, murs en slab(..., 1, ...) sur la hauteur, puis
  arch.pitched_roof au sommet des murs.
- Les murs d'enceinte : slab(x, z, longueur, 1, 0, couleur, layers=h).

DÉCALAGE VERTICAL (piège n°2) : une brique occupe 3 niveaux-plaques. Pour
empiler, y avance de 3 (jamais de 1). Exemple : dalle à y=0 (occupe 0-2),
murs à y=3 (occupent 3-5), toit à y=6.

EXEMPLE COMPLET — BÂTIMENT (copie ce squelette puis adapte) :
    model.slab(0, 0, 16, 12, 0, "19")              # dalle
    model.slab(0, 0, 16, 1, 3, "19", layers=3)     # mur avant
    model.slab(0, 11, 16, 1, 3, "19", layers=3)    # mur arrière
    model.slab(0, 0, 1, 12, 3, "19", layers=3)     # mur gauche
    model.slab(15, 0, 1, 12, 3, "19", layers=3)    # mur droit
    arch.pitched_roof(0, 0, 16, 12, 12, "4")       # toit à deux pans

EXEMPLE COMPLET — VAISSEAU (copie ce squelette puis adapte) :
    arch.hull(0, 0, 6, 20, 2, "71")                # fuselage : x, z, larg, long
    arch.wing(0, 6, 7, 6, 0, "272")                # aile gauche (chevauche)
    arch.wing(6, 6, 7, 6, 0, "272")                # aile droite
    arch.cockpit(2, 3, 2, 4, 6, "43")              # verrière vitrée
    arch.engine(1, 20, 2, 3, 0, "272")             # propulseur (z = z+hull_d)
    arch.engine(4, 20, 2, 3, 0, "272")             # propulseur

EXEMPLE COMPLET — TOUR (copie ce squelette puis adapte) :
    for lvl in range(8):                           # coque de 4 murs, 8 briques
        y = lvl * 3
        model.slab(0, 0, 6, 1, y, "71")            # mur avant
        model.slab(0, 5, 6, 1, y, "71")            # mur arrière
        model.slab(0, 1, 1, 4, y, "71")            # mur gauche
        model.slab(5, 1, 1, 4, y, "71")            # mur droit
    arch.crenellate(0, 0, 6, 6, 24, "71")          # créneaux
    arch.pyramid_roof(1, 1, 4, 24, "4")            # toit conique

API de model :
- model.place(part_id, x, z, y=0, color="4", rot=0)
    x, z : coordonnées en studs du COIN de la pièce (y compris après rotation)
    y    : niveau vertical en PLAQUES (1 brique = 3, 1 plaque = 1, tuile = 1)
    rot  : 0, 90, 180, 270 (degrés autour de la verticale)
    Une "Brick 2 x 4" (id 3001) posée en (x,z) occupe x..x+3 en largeur et
    z..z+1 en profondeur (rot 0) ; l'échange avec rot 90.
- model.add_step() : termine une étape de construction (visible en vidéo)

PRIMITIVES DE HAUT NIVEAU — utilise-les en priorité, elles choisissent les
pièces et évitent les collisions par construction :
- model.slab(x, z, w, d, y=0, color="4", layers=1, openings=None)
    Pave un rectangle de w x d studs (coin en x,z) sur `layers` niveaux de
    briques. Un MUR = slab(x, z, longueur, 1, ...) ; un SOL/TOIT =
    layers=1 ; un BLOC plein = layers=n.
    openings = [(ox, oz, ow, od), ...] laisse des trous (portes, fenêtres).
    Retourne le nombre de pièces posées.
- model.column(x, z, layers, color="4", part="3005")
    Empile `layers` briques à la verticale (tour, pilier, tronc).
- model.clearance(x, z, w, d, layers, y=0) -> bool
    Vrai si le volume est libre (à tester avant d'ajouter une structure).
- model.connectivity() -> dict
    {"islands": n, ...} : n = nombre de blocs détachés. Un modèle correct a
    islands = 1. Vérifie-le avant de terminer !
- model.stability() -> dict
    {"min_stability": 0..1, "unsupported": [...], "tipping_joints": [...]}
    Physique du modèle. Le harness exige min_stability >= 0.8 :
    - 1.0 = tout est posé ; 0.8 = brique simplement accolée latéralement
      (accepté) ; 0.5 = un joint bascule ; 0.0 = brique sans aucun appui.
    Les deux derniers sont éliminatoires. N'écris PAS d'assert : regarde la
    valeur à la fin et corrige ta construction si elle est trop basse — une
    assertion qui échoue t'empêcherait de recevoir les informations de correction.
- model.try_place(...) : comme place() mais retourne False au lieu de lever
    une exception (détails décoratifs).
- model.parts_summary(), model.bounds() pour inspecter l'état.

Exemple de mur avec une porte :
    model.slab(0, 0, 16, 1, 0, "19", layers=3, openings=[(7, 0, 2, 1)])

Pièges à éviter :
- ne pose jamais deux briques au même endroit : préfère slab()/column() qui
  gèrent ça, ou monte y de 3 par brique (y+3) ;
- une pièce 1x4 (3010) le long de z doit être posée avec rot=90 ;
- compte tes bornes de boucle : une rangée de longueur L en briques 1x2
  avance de 2 par itération ;
- vérifie model.connectivity()["islands"] == 1 et
  model.stability()["min_stability"] >= 0.9 avant de finir : un modèle en
  plusieurs morceaux, avec des briques sans appui ou un joint qui bascule
  (centre de gravité hors de la zone d'appui) est refusé.

Conseils :
- définis des fonctions (mur, tour, symétrie miroir) et boucle : le code est
  plus court et plus fiable qu'une liste de place() littérales ;
- utilise des briques de GRANDE TAILLE (3001 2x4, 3010 1x4, 3004 1x2) pour
  les murs pleins : une tour en 1x1 (3005) est interdite sauf créneaux et
  détails ; vise moins de 200 briques au total ;
- respecte les couleurs demandées dans la description (codes LDraw :
  0 noir, 1 bleu, 2 vert, 4 rouge, 14 jaune, 15 blanc, 19 beige, 25 orange,
  70 brun, 71 gris clair, 72 gris foncé, 272 bleu foncé, 320 rouge foncé) ;
- utilise find_parts("slope 45") pour découvrir les ids exacts au runtime ;
- garde le total <= 600 briques, empreinte <= 40x40 studs ;
- termine par model.add_step().

Réponds UNIQUEMENT avec le code Python (pas de markdown, pas d'explication).
Le script DOIT définir le nom via l'appel initial : ne touche pas au nom,
utilise simplement `model`."""


def ask_script(client, prompt: str, history: list[dict]) -> str:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history + \
           [{"role": "user", "content": prompt}]
    resp = client.chat.completions.create(
        model=CODER_MODEL, messages=msgs, temperature=0.6, max_tokens=6000)
    code = resp.choices[0].message.content.strip()
    if code.startswith("```"):
        code = code.split("```")[1]
        if code.startswith("python"):
            code = code[6:]
    return code.strip()


CRITIC_PROMPT = """Tu es un critique de constructions LEGO. On te montre des
rendus (3 angles) d'un modèle généré pour satisfaire cette demande :
"{prompt}"
Compare ce qui est montré à la demande. Liste 3 à 5 problèmes CONCRETS et
ACTIONNABLES dans le code de construction (éléments manquants, couleurs
fausses, parties détachées ou flottantes, proportions absurdes, symétrie
cassée). Pour chaque problème, indique où agir (quelle partie du modèle).
Si le modèle répond déjà bien à la demande, réponds exactement :
RIEN A SIGNALER"""


def _image_msg(png: Path) -> dict:
    import base64
    b64 = base64.b64encode(png.read_bytes()).decode()
    return {"type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"}}


def critique_build(client, prompt: str, ldr: Path, workdir: Path) -> str:
    """Rend 3 angles du modèle et demande une critique au modèle vision."""
    views = []
    for i, (lat, lon) in enumerate([(30, 45), (30, 225), (80, 45)]):
        png = workdir / f"view_{i}.png"
        try:
            rend.render_image(ldr, png, lat=lat, lon=lon)
            views.append(png)
        except RuntimeError:
            continue
    if not views:
        return ""
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": CRITIC_PROMPT.format(prompt=prompt)},
            *[_image_msg(v) for v in views]]}],
        temperature=0.3, max_tokens=4000)
    return resp.choices[0].message.content.strip()


def _geom_defects(result: dict) -> bool:
    """Le modèle est-il physiquement défaillant ? (construit, mais instable)
    Seuils alignés sur la sémantique du score : 1.0 = parfait, 0.8 = brique
    simplement accolée (décoratif, toléré), 0.5 = joint qui bascule, 0.0 =
    brique sans aucun appui. Seuls les deux derniers sont éliminatoires.
    Un modèle en plusieurs morceaux détachés (islands > 1) l'est aussi : rien
    ne le tient, même si chaque morceau est stable isolément."""
    st = result.get("stability", {}) or {}
    return bool(st.get("unsupported") or st.get("tipping_joints")
                or st.get("min", 1.0) < 0.8
                or result.get("islands", 1) > 1)


def _geom_feedback(result: dict) -> str:
    """Message de correction géométrique adressé au modèle."""
    st = result.get("stability", {}) or {}
    lines = [
        "Le modèle se construit mais n'est pas acceptable physiquement :",
        f"- min_stability = {st.get('min')} (il faut >= 0.8)",
        f"- {st.get('unsupported', 0)} brique(s) sans aucun appui (à supprimer ou reposer)",
        f"- {st.get('tipping_joints', 0)} joint(s) qui basculent : le centre de "
        "gravité sort de la zone d'appui (élargis la base ou réduis le porte-à-faux)",
        f"- {st.get('overhang_cells', 0)} brique(s) en appui partiel",
    ]
    if result.get("islands", 1) > 1:
        sizes = result.get("island_sizes", [])
        lines.append(
            f"- le modèle est en {result['islands']} morceaux DÉTACHÉS "
            f"(tailles {sizes}) : des éléments ne touchent rien. Relie-les au "
            "reste (chevauche d'au moins un stud) ou supprime-les.")
    weak = result.get("weak") or []
    if weak:
        lines.append("Briques faibles : " + "; ".join(
            f"{w['part']} en {w['pos']} ({w['reason']})" for w in weak[:6]))
    lines.append(
        "Corrige en réutilisant les primitives (arch.pitched_roof, "
        "arch.pyramid_roof, arch.crenellate) plutôt qu'en construisant les "
        "toits et créneaux à la main, et vérifie que ton empilement avance bien "
        "de 3 niveaux par brique. Renvoie le script COMPLET.")
    return "\n".join(lines)


def _n_shifts(result: dict) -> float:
    """Score de défaut d'un build : plus il est bas, meilleur est le modèle.
    Agrège les réparations automatiques, les briques sans appui, les
    porte-à-faux et le déficit de stabilité (min_stability = maillon faible,
    la métrique qui compte d'après la littérature)."""
    st = result.get("stability", {}) or {}
    return (result.get("settled", 0)
            + len(result.get("warnings", []))
            + 3 * st.get("unsupported", 0)          # éliminatoire
            + 2 * st.get("tipping_joints", 0)       # basculement
            + 0.2 * st.get("overhang_cells", 0)
            + 2 * (1.0 - st.get("min", 1.0)))


def generate(prompt: str, max_rounds: int = 3, make_video: bool = True,
             visual_rounds: int = 2) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Définis DEEPSEEK_API_KEY (export DEEPSEEK_API_KEY=sk-...)")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    history: list[dict] = []
    result: dict | None = None
    code = ""
    for round_no in range(1, max_rounds + 1):
        print(f"[tour {round_no}/{max_rounds}] DeepSeek écrit le script...", flush=True)
        code = ask_script(client, prompt, history)
        print(f"      exécution sandbox ({len(code)} chars)...", flush=True)
        result = run_sandbox({"name": "build", "code": code, "prompt": prompt})
        if result.get("ok"):
            st = result.get("stability", {})
            print(f"      OK : {result['n_bricks']} briques, "
                  f"{result['n_steps']} étapes, settle: {result.get('settled', 0)}, "
                  f"stabilité min {st.get('min', '?')} "
                  f"({st.get('unsupported', 0)} sans appui, "
                  f"{st.get('tipping_joints', 0)} basculement(s))", flush=True)
            # boucle géométrique : un modèle construit mais physiquement faible
            # est renvoyé au modèle avec les détails, au lieu d'être accepté.
            if _geom_defects(result) and round_no < max_rounds:
                print("      stabilité insuffisante -> correction demandée",
                      flush=True)
                history.append({"role": "assistant", "content": code})
                history.append({"role": "user", "content": _geom_feedback(result)})
                continue
            break
        error = result.get("error", "?")
        print(f"      ERREUR : {error[:200]}", flush=True)
        history.append({"role": "assistant", "content": code})
        history.append({"role": "user", "content":
                        "Ton script a échoué à l'exécution :\n" + error +
                        "\nAVANT de réécrire : raisonne sur la cause. Une "
                        "collision en (x,y,z) avec une pièce déjà posée en "
                        "(px,py,pz) signifie que leurs empreintes se "
                        "chevauchent : vérifie la taille de CHAQUE pièce "
                        "(une Brick 2x4 couvre 4 studs en x et 2 en z avec "
                        "rot 0) et l'avancement de tes boucles. "
                        "Renvoie le script COMPLET corrigé (uniquement du "
                        "Python)."})
    if not result or not result.get("ok"):
        raise SystemExit("Échec après " + str(max_rounds) + " tours : " +
                         str((result or {}).get("error", "?")))

    ldr = Path(result["ldr"])
    ldr = Path(result["ldr"])

    # --- boucle visuelle : le modèle vision critique, le codeur corrige ---
    for v in range(max(0, visual_rounds)):
        print(f"[visuel {v+1}/{visual_rounds}] critique par {VISION_MODEL}...",
              flush=True)
        critique = critique_build(client, prompt, ldr, PROJECT / "out")
        if not critique:
            break
        if "RIEN A SIGNALER" in critique.upper():
            print("      rien à signaler", flush=True)
            break
        print("      " + critique[:160].replace("\n", " "), flush=True)
        history.append({"role": "assistant", "content": code})
        history.append({"role": "user", "content":
                        "Le rendu du modèle a été examiné par un modèle de "
                        "vision qui signale :\n" + critique +
                        "\nCorrige le script COMPLET pour traiter ces points "
                        "en touchant AUSSI PEU DE CHOSE que possible : ne "
                        "déplace pas les structures existantes, ne change pas "
                        "les dimensions générales, ajuste uniquement ce qui "
                        "est signalé (Python uniquement, mêmes règles)."})
        kept_ldr = Path(result["ldr"])
        kept_content = kept_ldr.read_bytes()  # la correction écrase le fichier
        code = ask_script(client, prompt, history)
        r2 = run_sandbox({"name": "build", "code": code, "prompt": prompt})
        if not r2.get("ok"):
            print(f"      correction rejetée ({r2.get('error', '?')[:120]}) — "
                  "on garde la version précédente", flush=True)
            kept_ldr.write_bytes(kept_content)
            history = history[:-2]  # la critique sera reformulée au prochain tour
            break
        # Une correction ne doit ni multiplier les réparations automatiques
        # (briques flottantes/décalées) ni supprimer des structures : au-delà
        # de 25 % de briques en moins, ce n'est plus une correction.
        worse_repairs = _n_shifts(r2) > _n_shifts(result)
        shrunk = r2["n_bricks"] < 0.75 * result["n_bricks"]
        if worse_repairs or shrunk:
            why = (f"réparations {_n_shifts(r2)} > {_n_shifts(result)}"
                   if worse_repairs else
                   f"taille {result['n_bricks']} -> {r2['n_bricks']}")
            print(f"      correction rejetée ({why}) — version gardée", flush=True)
            kept_ldr.write_bytes(kept_content)  # restaure le .ldr retenu
            break
        result = r2
        ldr = Path(r2["ldr"])
        print(f"      corrigé : {r2['n_bricks']} briques", flush=True)

    png = PROJECT / "renders" / f"{ldr.stem}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    print("[rendu] aperçu...", flush=True)
    rend.render_image(ldr, png, lat=30, lon=45)
    out = {"ldr": str(ldr), "preview": str(png),
           "n_bricks": result["n_bricks"], "parts_used": result["parts_used"],
           "code": code}
    if make_video:
        print("[rendu] vidéo (timelapse + 360°)...", flush=True)
        mp4 = rend.build_video(ldr, PROJECT / "renders" / f"{ldr.stem}.mp4", lat=30)
        out["video"] = str(mp4)
    return out


def main():
    ap = argparse.ArgumentParser(description="text -> script Python -> LEGO -> vidéo")
    ap.add_argument("prompt")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--visual-rounds", type=int, default=1,
                    help="tours de critique visuelle (0 = désactivé)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    result = generate(args.prompt, max_rounds=args.rounds,
                      make_video=not args.no_video,
                      visual_rounds=args.visual_rounds)
    Path(PROJECT / "out").mkdir(exist_ok=True)
    (PROJECT / "out" / "last_build_script.py").write_text(result.pop("code"))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("script sauvegardé : out/last_build_script.py")
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
