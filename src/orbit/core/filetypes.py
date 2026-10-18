"""Work out what kind of file we are dealing with."""

from enum import Enum
from pathlib import Path


class Kind(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    DOCUMENT = "document"
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"
    OTHER = "other"
    ANY = "*"


_EXT = {
    Kind.IMAGE: {"png", "jpg", "jpeg", "webp", "heic", "heif", "avif", "bmp", "tif", "tiff", "gif", "ico"},
    Kind.PDF: {"pdf"},
    Kind.DOCUMENT: {"docx", "doc", "odt", "rtf", "pptx", "ppt", "odp", "xlsx", "xls", "ods"},
    Kind.TEXT: {"txt", "md", "csv", "html", "htm"},
    Kind.AUDIO: {"mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "wma"},
    Kind.VIDEO: {"mp4", "mov", "mkv", "webm", "avi", "m4v", "flv", "wmv"},
}


def ext(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def kind_of(path: Path) -> Kind:
    e = ext(path)
    for kind, exts in _EXT.items():
        if e in exts:
            return kind
    return Kind.OTHER


def common_kind(paths: list[Path]) -> Kind | None:
    """The shared kind of every file, or None when they differ."""
    kinds = {kind_of(p) for p in paths}
    return kinds.pop() if len(kinds) == 1 else None
