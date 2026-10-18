"""Actions that work on any file."""

import zipfile
from pathlib import Path

from ..core.actions import TOOLS, action
from ..core.filetypes import Kind
from ..core.naming import output_path


@action("any.zip", "ZIP", [Kind.ANY], page=TOOLS, icon="zip", order=90)
def to_zip(paths: list[Path]) -> list[Path]:
    paths = sorted(paths)
    out = output_path(paths[0], "zip", "Archive" if len(paths) > 1 else "")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p.is_dir():
                for f in p.rglob("*"):
                    z.write(f, f.relative_to(p.parent))
            else:
                z.write(p, p.name)
    return [out]
