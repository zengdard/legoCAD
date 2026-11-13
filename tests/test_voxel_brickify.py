#!/usr/bin/env python3
"""Tests du pipeline v2 : volume → briques → nomenclature → notice.

Lancer : python3 -m pytest tests/ -q
"""
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import bom as bmod                      # noqa: E402
import brickify                         # noqa: E402
import instructions                     # noqa: E402
import preview_svg                      # noqa: E402
import quality                          # noqa: E402
import shapes                           # noqa: E402
import studs                            # noqa: E402
import voxel                            # noqa: E402


def _box(w=8, h=6, d=6, name="t"):
    return brickify.brickify(voxel.VoxelGrid().box(0, 0, 0, w, h, d, "4"),
                             name)


# --- volume → briques ------------------------------------------------- #

def test_boite_compile_sans_trou():
    model, rep = _box()
    assert rep["coverage"] == 1.0
    assert rep["gap_count"] == 0
    assert rep["islands"] == 1
    assert rep["min_stability"] >= 0.8
    assert rep["build_errors"] == []
    assert rep["pieces"] > 0


def test_chaque_piece_est_posee_sur_des_studs():
    model, _ = _box(10, 6, 8)
    rep = studs.report(model)
    assert rep["islands"] == 1
    assert rep["unsupported"] == []
    assert rep["connections"] > 0


def test_collision_impossible_dans_le_compile():
    """Le compilateur ne doit jamais produire deux pièces qui se chevauchent."""
    from ldraw_model import _NOMINAL_H, LDU_PER_LEVEL
    model, _ = _box(12, 9, 12)
    seen = set()
    for b in model.bricks:
        part = model.part(b["part_id"])
        sx, sz = model._footprint(part, b["rot"])
        h = max(1, _NOMINAL_H.get(part["kind"], 24) // LDU_PER_LEVEL)
        for x in range(b["x"], b["x"] + sx):
            for z in range(b["z"], b["z"] + sz):
                for y in range(b["y"], b["y"] + h):
                    key = (x, y, z)
                    assert key not in seen, f"collision en {key}"
                    seen.add(key)


def test_appareillage_decale_les_joints():
    """Deux cours de briques ne doivent pas être alignés (sinon le modèle
    se sépare en colonnes indépendantes)."""
    model, rep = brickify.brickify(
        voxel.VoxelGrid().box(0, 0, 0, 16, 6, 8, "4"), "t")
    assert rep["islands"] == 1
    y0 = {b["x"] for b in model.bricks if b["y"] == 0 and b["z"] == 0}
    y3 = {b["x"] for b in model.bricks if b["y"] == 3 and b["z"] == 0}
    assert y0 != y3


def test_volume_qui_s_elargit_reste_constructible():
    """Un escalier qui s'élargit d'un stud par niveau est constructible : la
    pièce du dessus enjambe le bord et repose sur la couche précédente."""
    g = voxel.VoxelGrid()
    g.box(0, 0, 0, 4, 3, 4, "4")
    g.box(0, 3, 0, 5, 3, 4, "4")
    g.box(0, 6, 0, 6, 3, 4, "4")
    model, rep = brickify.brickify(g, "elargi")
    # un débord d'un stud peut être perdu au coin (le compilateur refuse une
    # pièce sans appui) : on tolère une petite perte, mais pas un modèle cassé
    assert rep["coverage"] >= 0.9
    assert rep["islands"] == 1


def test_couleur_isolee_est_nettoyee():
    g = voxel.VoxelGrid().box(0, 0, 0, 6, 3, 6, "15")
    g.add(3, 2, 3, "0")            # un pixel noir isolé
    model, rep = brickify.brickify(g, "propre")
    assert rep["coverage"] == 1.0
    assert all(b["color"] == "15" for b in model.bricks)


def test_import_ldr_roundtrip(tmp_path):
    model, _ = _box(8, 6, 6)
    path = tmp_path / "m.ldr"
    model.save(path)
    grid = voxel.from_ldr(path)
    assert grid.count() > 0
    model2, rep = brickify.brickify(grid, "m2")
    assert rep["pieces"] > 0
    assert model2.bricks


def test_import_natif_conserve_les_pieces(tmp_path):
    import ldr_io
    model, _ = _box(8, 6, 6)
    path = tmp_path / "n.ldr"
    model.save(path)
    native, stats = ldr_io.load(path)
    assert stats["pieces"] == len(model.bricks)
    assert stats["collisions"] == 0
    assert stats["skipped_rotated"] == 0
    assert studs.report(native)["islands"] == 1


def test_validite_brickbench():
    model, rep = _box(8, 6, 6)
    val = quality.validity(model, rep)
    assert val["valid"] and val["components"] == 1
    assert val["collisions"] == 0 and val["stable"]


def test_degrade_contraintes_impossible():
    """Un volume vide ne doit pas planter le compilateur."""
    model, rep = brickify.brickify(voxel.VoxelGrid(), "vide")
    assert rep["status"] == "EMPTY"
    assert model.bricks == []


def test_pentes_sur_marche_de_trois_plaques():
    g = voxel.VoxelGrid().box(0, 0, 0, 4, 3, 4, "4")
    g.box(0, 3, 2, 4, 3, 2, "4")
    model, rep = brickify.brickify(g, "pente")
    slopes = {"3040b", "3039", "3037", "4286", "3298"}
    assert rep["slopes"] >= 1
    assert any(b["part_id"] in slopes for b in model.bricks)
    assert rep["coverage"] == 1.0 and rep["islands"] == 1


def test_tile_cap_lisse_le_dessus():
    model, rep = _box(8, 6, 6)
    tiles = {"3070b", "3069b", "63864", "2431", "6636", "3068b",
             "26603", "87079"}
    assert rep["coverage"] == 1.0
    assert any(b["part_id"] in tiles for b in model.bricks)


def test_fondation_4x4_2d():
    from ldraw_model import _NOMINAL_H, LDU_PER_LEVEL
    model, rep = _box(12, 6, 12)
    big = {"3031", "3035"}
    assert any(b["part_id"] in big for b in model.bricks)
    assert rep["islands"] == 1


def test_familles_de_connecteurs():
    model, _ = _box(8, 6, 8)
    fam = studs.families(model)
    assert fam["counts"].get("stud", 0) == len(model.bricks)
    assert fam["non_stud"] == []


def test_snot_connexion_laterale(tmp_path):
    import snot
    scene = snot.demo()
    assert len(scene.items) == 4
    assert scene.connected()
    path = scene.save(tmp_path / "snot.ldr")
    text = path.read_text()
    assert "4070.dat" in text
    assert text.count("\n1 ") == 4


def test_profondeur_avec_masque(tmp_path):
    from PIL import Image
    import depth_to_voxel
    d = Image.new("L", (16, 16), 0)
    px = d.load()
    for y in range(16):
        for x in range(16):
            px[x, y] = 255 - (abs(x - 8) + abs(y - 8)) * 12
    dp = tmp_path / "d.png"; d.save(dp)
    m = Image.new("L", (16, 16), 0)
    mp = m.load()
    for y in range(4, 12):
        for x in range(4, 12):
            mp[x, y] = 255
    mk = tmp_path / "m.png"; m.save(mk)
    plain = depth_to_voxel.from_depth(dp, width=8, max_height=6)
    masked = depth_to_voxel.from_depth(dp, width=8, max_height=6, mask=mk)
    assert 0 < masked.count() < plain.count()


def test_profondeur_vers_relief(tmp_path):
    from PIL import Image
    import depth_to_voxel
    d = Image.new("L", (24, 18), 0)
    px = d.load()
    for y in range(18):
        for x in range(24):
            px[x, y] = 255 - (abs(x - 12) + abs(y - 9)) * 10
    dp = tmp_path / "d.png"
    d.save(dp)
    c = Image.new("RGB", (24, 18), (200, 30, 30))
    cp = tmp_path / "c.png"
    c.save(cp)
    g = depth_to_voxel.from_depth(dp, cp, width=16, max_height=8)
    assert g.count() > 0
    model, rep = brickify.brickify(g, "relief")
    assert rep["coverage"] == 1.0
    assert rep["islands"] == 1


# --- formes de démonstration ----------------------------------------- #

def test_formes_demo_constructibles():
    for name in ("house", "rocket", "car", "tree", "brick", "spaceship", "duck", "castle"):
        model, rep = brickify.brickify(shapes.make(name), name)
        assert rep["coverage"] >= 0.99, (name, rep["coverage"])
        assert rep["islands"] == 1, name
        assert rep["min_stability"] >= 0.8, name
        assert rep["unsupported"] == [], name


def test_mosaique_image(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (8, 8), "white")
    for x in range(2, 6):
        for y in range(2, 6):
            img.putpixel((x, y), (200, 20, 20))
    p = tmp_path / "img.png"
    img.save(p)
    g = shapes.mosaic(p, max_width=8)
    assert g.count() > 0
    assert "4" in g.color_counts()


# --- stabilité / connexions ------------------------------------------ #

def test_accolement_lateral_ne_cree_pas_de_connexion():
    from ldraw_model import LDrawModel
    m = LDrawModel("lateral")
    m.place("3001", 0, 0, 0, "4")
    m.place("3001", 4, 0, 0, "1")       # à côté, même niveau
    rep = studs.report(m)
    assert rep["islands"] == 2


def test_piece_sur_tile_n_est_pas_attachee():
    from ldraw_model import LDrawModel
    m = LDrawModel("tile")
    m.place("3001", 0, 0, 0, "4")       # brique
    m.place("3069b", 0, 0, 3, "15")     # tile 1x2 sur le dessus
    m.place("3001", 0, 0, 4, "1")       # brique sur la tile (pas de studs)
    rep = studs.report(m)
    assert 2 in rep["unsupported"]


# --- livrables ------------------------------------------------------- #

def test_bom_exporte_et_disponibilite(tmp_path):
    model, _ = _box(10, 6, 8)
    rows = bmod.build(model)
    assert rows and sum(r.count for r in rows) == len(model.bricks)
    csv = bmod.to_csv(rows)
    assert "part_id" in csv and "quantity" in csv
    xml, missing = bmod.to_bricklink_xml(rows)
    assert "<INVENTORY>" in xml and "<ITEM>" in xml
    avail = bmod.check_availability(rows)
    if avail.get("checked"):
        assert 0.0 <= avail["score"] <= 1.0
    files = bmod.export_all(model, tmp_path, "test")
    assert Path(files["csv"]).exists()
    assert Path(files["xml"]).exists()


def test_score_qualite():
    model, rep = _box(10, 6, 8)
    bom_meta = {"mix_similarity": 0.5, "availability": {"checked": False}}
    sc = quality.score(model, rep, bom_meta)
    assert sc["overall"] > 0.8
    assert sc["grade"] in ("A", "B")
    assert all("ok" in c for c in sc["checks"])


def test_notice_html_sans_leocad(tmp_path):
    model, rep = _box(8, 6, 6)
    ldr = tmp_path / "m.ldr"
    model.save(ldr)
    path = instructions.build(model, ldr, tmp_path / "notice",
                              render_steps=True, use_leocad=False)
    html = path.read_text()
    assert "Inventaire" in html and "Montage" in html
    assert "steps/step01.svg" in html
    assert (tmp_path / "notice" / "steps" / "step01.svg").exists()


def test_svg_est_valide_et_colore():
    model, _ = _box(6, 6, 6)
    svg = preview_svg.render_svg(model, title="test")
    assert svg.startswith("<svg")
    assert "polygon" in svg and "ellipse" in svg
