"""Real progress reporting from inside actions.

The app sets a callback for the worker thread; actions call `report(0.4)`
(or `step(i, n)`) as they go. Without a callback these do nothing, so the
CLI and tests are unaffected.
"""

import threading

_local = threading.local()


def set_callback(fn):
    _local.fn = fn


def report(fraction: float):
    fn = getattr(_local, "fn", None)
    if fn:
        fn(max(0.0, min(1.0, fraction)))


def step(done: int, total: int):
    report(done / total if total else 1.0)
