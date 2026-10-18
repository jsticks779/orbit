"""Run every action the panel can offer on a real sample of every file kind.

Slow (LibreOffice, ffmpeg), so it's opt-in:  ORBIT_FULL=1 pytest tests/test_everything.py -v
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from orbit.core.actions import actions_for

pytestmark = pytest.mark.skipif(not os.environ.get("ORBIT_FULL"), reason="set ORBIT_FULL=1 to run")


def _samples(d: Path) -> dict[str, Path]:
    s = {}
    img = Image.radial_gradient("L").convert("RGBA").resize((320, 200))
    for ext in ("png", "jpg", "gif"):
        s[ext] = d / f"sample.{ext}"
        (img.convert("RGB") if ext == "jpg" else img).save(s[ext])
    import pymupdf
    doc = pymupdf.open()
    for n in (1, 2):
        page = doc.new_page()
        page.insert_text((72, 72), f"Orbit test page {n}", fontsize=20)
        page.insert_image(pymupdf.Rect(72, 100, 272, 225), filename=str(s["png"]))
    s["pdf"] = d / "sample.pdf"
    doc.save(s["pdf"])
    s["txt"] = d / "notes.txt"
    s["txt"].write_text("Hello from Orbit.\nSecond line.\n")
    if shutil.which("soffice"):
        from orbit.actions.document import soffice_convert
        s["docx"] = soffice_convert(s["txt"], "docx").rename(d / "letter.docx")
    if shutil.which("ffmpeg"):
        s["mp4"] = d / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25",
                        "-f", "lavfi", "-i", "sine=duration=3", "-shortest", "-c:v", "libx264", "-c:a", "aac",
                        str(s["mp4"])], check=True)
        s["wav"] = d / "tone.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=2", str(s["wav"])], check=True)
    return s


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    return _samples(tmp_path_factory.mktemp("samples"))


CASES = ["png", "jpg", "gif", "pdf", "txt", "docx", "mp4", "wav"]


@pytest.mark.parametrize("kind", CASES)
def test_every_action_on(kind, samples):
    if kind not in samples:
        pytest.skip(f"no tool to make a {kind} sample")
    src = samples[kind]
    report = []
    for act in actions_for([src]):
        if act.dialog:
            continue
        outs = act.run([src])
        assert outs, f"{act.id} produced nothing"
        for o in outs:
            assert o.exists() and o.stat().st_size > 0, f"{act.id}: empty {o}"
        report.append(f"{act.id} -> {outs[0].name}")
    print(f"\n{kind}: {len(report)} actions OK\n  " + "\n  ".join(report))
    assert report


def test_multi_file_actions(samples, tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    shutil.copy(samples["png"], a)
    shutil.copy(samples["jpg"], b.with_suffix(".jpg"))
    b = b.with_suffix(".jpg")
    ids = [x.id for x in actions_for([a, b])]
    assert "image.combine_pdf" in ids and "any.zip" in ids
    from orbit.core.actions import get
    assert get("image.combine_pdf").run([a, b])[0].exists()
    p1 = tmp_path / "one.pdf"
    shutil.copy(samples["pdf"], p1)
    import pymupdf
    merged = get("pdf.merge").run([samples["pdf"], p1])[0]
    assert pymupdf.open(merged).page_count == 4


def test_editors_save(samples):
    from orbit.actions import backdrop
    from orbit.actions.image import open_image, save_as
    from orbit.ui.editors import adjust
    img = open_image(samples["png"])
    opt = {"rotate": 90, "flip_h": True, "flip_v": False, "brightness": 20, "contrast": 10,
           "saturation": -30, "warmth": 40, "sharpness": 50}
    assert adjust(img, opt).size == (img.height, img.width)
    assert save_as(samples["png"], "png", "Cropped", img.crop((10, 10, 110, 60))).exists()
    out = backdrop.render(img, backdrop.Backdrop(padding=40, corners=30, shadow=20, ratio="16:9"))
    assert abs(out.width / out.height - 16 / 9) < 0.01
    if "mp4" in samples:
        from orbit.actions.media import duration, export_clip
        clip = export_clip(samples["mp4"], 0.5, 2.5, mute=True, speed=2.0)
        assert 0.8 < duration(clip) < 1.3
