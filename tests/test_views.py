#!/usr/bin/env python3
"""Métriques de silhouette du banc 8 vues (sans LeoCAD)."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import views  # noqa: E402


def _square(size=100, box=(25, 25, 74, 74)):
    img = Image.new("L", (size, size), 0)
    ImageDraw.Draw(img).rectangle(box, fill=255)
    return img


def test_occupation_et_symetrie():
    m = views.silhouette_metrics(_square())
    assert abs(m["occupancy"] - 0.25) < 0.01
    assert abs(m["symmetry"] - 1.0) < 0.01
    assert 3.8 <= m["contour"] <= 4.2


def test_asymetrie_detectee():
    m = views.silhouette_metrics(_square(box=(5, 25, 54, 74)))
    assert m["symmetry"] < 0.6
    assert m["occupancy"] > 0.2


def test_masque_ignore_le_fond():
    img = Image.new("RGB", (60, 60), (20, 22, 26))
    ImageDraw.Draw(img).rectangle([10, 10, 49, 49], fill=(180, 180, 180))
    mask = views.mask_from_image(img)
    m = views.silhouette_metrics(mask)
    assert abs(m["occupancy"] - (40 * 40) / (60 * 60)) < 0.01
