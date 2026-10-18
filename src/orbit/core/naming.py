"""Output file naming. Orbit never overwrites: it always writes next to the source."""

from pathlib import Path


def output_path(src: Path, ext: str | None = None, suffix: str = "") -> Path:
    """`Page 001.pdf` -> `Page 001 Cropped.jpg`, adding ` (2)` etc. if taken."""
    ext = (ext or src.suffix.lstrip(".")).lower()
    stem = f"{src.stem} {suffix}".strip() if suffix else src.stem
    candidate = src.with_name(f"{stem}.{ext}")
    n = 2
    while candidate.exists():
        candidate = src.with_name(f"{stem} ({n}).{ext}")
        n += 1
    return candidate


def output_dir(src: Path, suffix: str) -> Path:
    d = src.with_name(f"{src.stem} {suffix}")
    n = 2
    while d.exists():
        d = src.with_name(f"{src.stem} {suffix} ({n})")
        n += 1
    d.mkdir()
    return d
