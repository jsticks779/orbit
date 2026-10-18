"""PDF and office documents (PyMuPDF, pdf2docx, LibreOffice, Ghostscript)."""

import shutil
import tempfile
from pathlib import Path

from ..core import progress
from ..core.actions import TOOLS, action
from ..core.filetypes import Kind
from ..core.naming import output_dir, output_path
from . import ActionError, need, run

PDF = [Kind.PDF]
OFFICE = [Kind.DOCUMENT, Kind.TEXT]


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError as e:
        raise ActionError("PDF tools need PyMuPDF (pip install pymupdf).") from e
    return fitz


def pdf_to_images(src: Path, fmt: str, dpi: int = 200) -> list[Path]:
    fitz = _fitz()
    doc = fitz.open(src)
    if doc.page_count == 1:
        out = output_path(src, fmt)
        doc[0].get_pixmap(dpi=dpi).save(out, jpg_quality=92) if fmt == "jpg" else doc[0].get_pixmap(dpi=dpi).save(out)
        return [out]
    folder = output_dir(src, fmt.upper())
    outs = []
    for i, page in enumerate(doc, 1):
        out = folder / f"{src.stem} {i:03d}.{fmt}"
        page.get_pixmap(dpi=dpi).save(out)
        outs.append(out)
        progress.step(i, doc.page_count)
    return outs


@action("pdf.to_jpg", "JPG", PDF, order=0)
def to_jpg(paths):
    return [o for p in paths for o in pdf_to_images(p, "jpg")]


@action("pdf.to_png", "PNG", PDF, order=1)
def to_png(paths):
    return [o for p in paths for o in pdf_to_images(p, "png")]


@action("pdf.to_txt", "TXT", PDF, order=2)
def to_txt(paths):
    fitz = _fitz()
    outs = []
    for p in paths:
        out = output_path(p, "txt")
        out.write_text("\n\n".join(page.get_text() for page in fitz.open(p)), encoding="utf-8")
        outs.append(out)
    return outs


@action("pdf.to_docx", "DOCX", PDF, order=3)
def to_docx(paths):
    try:
        from pdf2docx import Converter
    except ImportError as e:
        raise ActionError("PDF to DOCX needs pdf2docx (pip install pdf2docx).") from e
    outs = []
    for p in paths:
        out = output_path(p, "docx")
        cv = Converter(str(p))
        cv.convert(str(out))
        cv.close()
        outs.append(out)
    return outs


@action("pdf.merge", "Merge", PDF, multi=True, icon="merge", order=-1)
def merge(paths):
    fitz = _fitz()
    paths = sorted(paths)
    doc = fitz.open()
    for i, p in enumerate(paths, 1):
        doc.insert_pdf(fitz.open(p))
        progress.step(i, len(paths))
    out = output_path(paths[0], "pdf", "Merged")
    doc.save(out, garbage=3, deflate=True)
    return [out]


@action("pdf.compress", "Compress", PDF, page=TOOLS, icon="compress", order=0)
def compress(paths):
    outs = []
    for p in paths:
        out = output_path(p, "pdf", "Compressed")
        if shutil.which("gs"):
            run(["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5", "-dPDFSETTINGS=/ebook",
                 "-dNOPAUSE", "-dQUIET", "-dBATCH", f"-sOutputFile={out}", str(p)])
        else:
            _fitz().open(p).save(out, garbage=4, deflate=True, deflate_images=True)
        outs.append(out)
    return outs


@action("pdf.split", "Split Pages", PDF, page=TOOLS, icon="split", order=1)
def split(paths):
    fitz = _fitz()
    outs = []
    for p in paths:
        src = fitz.open(p)
        folder = output_dir(p, "Pages")
        for i in range(src.page_count):
            one = fitz.open()
            one.insert_pdf(src, from_page=i, to_page=i)
            out = folder / f"{p.stem} {i + 1:03d}.pdf"
            one.save(out)
            outs.append(out)
            progress.step(i + 1, src.page_count)
    return outs


@action("pdf.rotate", "Rotate", PDF, page=TOOLS, icon="rotate", order=2)
def rotate(paths):
    fitz = _fitz()
    outs = []
    for p in paths:
        doc = fitz.open(p)
        for page in doc:
            page.set_rotation((page.rotation + 90) % 360)
        out = output_path(p, "pdf", "Rotated")
        doc.save(out)
        outs.append(out)
    return outs


@action("pdf.images", "Extract Images", PDF, page=TOOLS, icon="images", order=3)
def extract_images(paths):
    fitz = _fitz()
    outs = []
    for p in paths:
        doc = fitz.open(p)
        folder = None
        for pno, page in enumerate(doc, 1):
            for n, info in enumerate(page.get_images(full=True), 1):
                data = doc.extract_image(info[0])
                folder = folder or output_dir(p, "Images")
                out = folder / f"page{pno:03d}_{n}.{data['ext']}"
                out.write_bytes(data["image"])
                outs.append(out)
    if not outs:
        raise ActionError("No images found in this PDF.")
    return outs


# ---- office documents via LibreOffice -----------------------------------------

def soffice_convert(src: Path, fmt: str) -> Path:
    exe = need("soffice", "Install it with: sudo apt install libreoffice")
    with tempfile.TemporaryDirectory() as tmp:
        # A private profile lets this run even while LibreOffice is open.
        run([exe, f"-env:UserInstallation=file://{tmp}/profile", "--headless",
             "--convert-to", fmt, "--outdir", tmp, str(src)], timeout=300)
        made = next((f for f in Path(tmp).iterdir() if f.is_file()), None)
        if not made:
            raise ActionError(f"LibreOffice could not convert {src.name}.")
        out = output_path(src, made.suffix.lstrip("."))
        shutil.move(made, out)
    return out


def _office(fmt: str, label: str, order: int, kinds=OFFICE):
    @action(f"office.to_{fmt}", label, kinds, skip_ext={fmt}, order=order)
    def convert(paths):
        return [soffice_convert(p, fmt) for p in paths]


_office("pdf", "PDF", 0)
_office("docx", "DOCX", 1, [Kind.DOCUMENT])
_office("odt", "ODT", 2, [Kind.DOCUMENT])
_office("txt", "TXT", 3, [Kind.DOCUMENT])
