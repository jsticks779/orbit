"""The action registry: every slice of the ring is an Action.

Action modules register themselves with @action(...). The ring asks
`actions_for(paths)` which actions fit the dropped files and shows them
in pages (page 0 = convert, page 1 = tools).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .filetypes import Kind, common_kind

CONVERT, TOOLS = 0, 1


@dataclass
class Action:
    id: str
    label: str
    kinds: set[Kind]
    run: Callable[[list[Path]], list[Path]]
    page: int = CONVERT
    icon: str = ""                 # symbolic icon name (filled from core.hints)
    multi: bool = False            # needs 2+ files (merge, combine)
    dialog: str | None = None      # opens a UI dialog instead of running directly
    skip_ext: set[str] = field(default_factory=set)  # hide "PNG" for .png files
    order: int = 50
    hint: str = ""                 # one-line explanation shown while hovering
    requires: tuple = ()           # python modules or programs it needs


_REGISTRY: list[Action] = []


def action(id, label, kinds, page=CONVERT, icon="", multi=False, dialog=None, skip_ext=(), order=50, requires=()):
    def deco(fn):
        from .hints import hint_for, icon_for
        _REGISTRY.append(Action(id, label, set(kinds), fn, page, icon_for(label), multi, dialog,
                                set(skip_ext), order, hint_for(id, label), tuple(requires)))
        return fn
    return deco


def _load():
    # Importing the modules fills the registry.
    from ..actions import archive, document, image, media  # noqa: F401


def all_actions() -> list[Action]:
    if not _REGISTRY:
        _load()
    return _REGISTRY


def get(action_id: str) -> Action:
    for a in all_actions():
        if a.id == action_id:
            return a
    raise KeyError(action_id)


def available(a: Action) -> bool:
    """Hide slices whose tool isn't installed, instead of offering them and failing."""
    import importlib.util
    import shutil
    return all(shutil.which(r[1:]) if r.startswith("!") else importlib.util.find_spec(r) for r in a.requires)


def actions_for(paths: list[Path]) -> list[Action]:
    kind = common_kind(paths)
    exts = {p.suffix.lower().lstrip(".") for p in paths}
    exts |= {"jpeg"} if "jpg" in exts else set()
    exts |= {"jpg"} if "jpeg" in exts else set()
    many = len(paths) > 1
    out = []
    for a in all_actions():
        if Kind.ANY not in a.kinds and kind not in a.kinds:
            continue
        if a.multi and not many:
            continue
        if exts and exts <= a.skip_ext:
            continue
        if not available(a):
            continue
        out.append(a)
    return sorted(out, key=lambda a: (a.page, a.order))


def pages_for(paths: list[Path]) -> list[list[Action]]:
    acts = actions_for(paths)
    pages = [[a for a in acts if a.page == p] for p in (CONVERT, TOOLS)]
    return [p for p in pages if p]
