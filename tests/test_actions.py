from pathlib import Path

import pytest
from PIL import Image

from orbit.actions import backdrop
from orbit.core.actions import get, pages_for
from orbit.core.naming import output_path


@pytest.fixture
def png(tmp_path) -> Path:
    p = tmp_path / "Page 001.png"
    Image.new("RGBA", (120, 80), (200, 60, 40, 255)).save(p)
    return p


def test_output_path_never_overwrites(tmp_path):
    src = tmp_path / "a.pdf"
    src.touch()
    assert output_path(src, "jpg").name == "a.jpg"
    (tmp_path / "a.jpg").touch()
    assert output_path(src, "jpg").name == "a (2).jpg"
    assert output_path(src, "jpg", "Cropped").name == "a Cropped.jpg"


def test_pages_hide_same_format(png):
    convert, tools = pages_for([png])
    labels = [a.label for a in convert]
    assert "PNG" not in labels and "JPG" in labels
    assert {"Crop", "Add BG", "Compress"} <= {a.label for a in tools}


def test_multi_file_actions_only_for_many(png, tmp_path):
    other = tmp_path / "b.png"
    Image.new("RGB", (10, 10)).save(other)
    assert "image.combine_pdf" not in [a.id for a in sum(pages_for([png]), [])]
    assert "image.combine_pdf" in [a.id for a in sum(pages_for([png, other]), [])]


@pytest.mark.parametrize("fmt", ["jpg", "webp", "avif", "bmp", "tiff", "pdf", "ico", "gif"])
def test_image_convert(png, fmt):
    out = get(f"image.to_{fmt}").run([png])[0]
    assert out.exists() and out.suffix == f".{fmt}" and out.stat().st_size > 0


def test_image_tools(png):
    for aid in ("image.compress", "image.metadata", "image.rotate", "image.resize", "image.grayscale", "any.zip"):
        assert get(aid).run([png])[0].exists(), aid
    assert Image.open(get("image.rotate").run([png])[0]).size == (80, 120)


def test_pdf_roundtrip(png):
    pdf = get("image.to_pdf").run([png])[0]
    assert get("pdf.to_png").run([pdf])[0].suffix == ".png"
    assert get("pdf.to_txt").run([pdf])[0].exists()
    merged = get("pdf.merge").run([pdf, get("pdf.rotate").run([pdf])[0]])[0]
    import pymupdf
    assert pymupdf.open(merged).page_count == 2


def test_backdrop_ratio_and_padding(png):
    img = Image.open(png)
    out = backdrop.render(img, backdrop.Backdrop(padding=20, ratio="Auto"))
    assert out.size == (160, 120)
    out = backdrop.render(img, backdrop.Backdrop(padding=20, ratio="1:1"))
    assert out.width == out.height


def test_every_slice_has_an_explanation(png):
    from orbit.core.actions import all_actions
    missing = [a.id for a in all_actions() if not a.hint]
    assert not missing, missing


def test_normal_paths_pass_through_portal_lookup(png):
    from orbit.core.portal import real_path
    assert real_path(png) == png


def test_progress_reports_per_page(png):
    from orbit.core import progress
    seen = []
    progress.set_callback(seen.append)
    try:
        pdf = get("image.to_pdf").run([png])[0]
        get("pdf.merge").run([pdf, pdf])
    finally:
        progress.set_callback(None)
    assert seen and seen[-1] == 1.0
