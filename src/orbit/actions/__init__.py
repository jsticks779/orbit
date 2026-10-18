"""Built-in actions. Each module registers its actions on import."""

import shutil
import subprocess


class ActionError(RuntimeError):
    """A friendly error shown to the user as a notification."""


def need(tool: str, hint: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ActionError(f"{tool} is not installed. {hint}")
    return path


def run(cmd: list[str], timeout: int = 600) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-3:]
        raise ActionError(f"{cmd[0]} failed: {' '.join(tail)}")
