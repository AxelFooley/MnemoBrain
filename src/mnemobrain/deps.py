"""Engine dependency checks and installs. Version pins come from config.get_env only."""

import json
import os
import pathlib
import shutil
import subprocess
import sys

from mnemobrain import config

MIN_BUN = (1, 3, 11)
BUN_INSTALL = "curl -fsSL https://bun.sh/install | bash"
GBRAIN_REPO = "github:garrytan/gbrain"


def version_tuple(text):
    parts = []
    for piece in text.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            raise ValueError(f"unparseable version: {text!r}")
        parts.append(int(digits))
    return tuple(parts)


def bun_version():
    if not shutil.which("bun"):
        return None
    r = subprocess.run(["bun", "--version"], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return None
    try:
        return version_tuple(r.stdout)
    except ValueError:
        return None


def check_bun():
    v = bun_version()
    if v is None:
        return False, "bun not found or not runnable", f"install bun: {BUN_INSTALL}"
    if v < MIN_BUN:
        return (
            False,
            f"bun {'.'.join(map(str, v))} < {'.'.join(map(str, MIN_BUN))}",
            f"upgrade bun: {BUN_INSTALL}",
        )
    return True, ".".join(map(str, v)), ""


def gbrain_bin():
    candidate = config.home() / "node_modules" / ".bin" / "gbrain"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    found = shutil.which("gbrain")
    return pathlib.Path(found) if found else None


def install_mnemosyne():
    version = config.get_env("MNEMOBRAIN_MNEMOSYNE_VERSION")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", f"mnemosyne-memory=={version}"], check=False
    )
    if r.returncode != 0:
        raise SystemExit(
            f"deps: pip install mnemosyne-memory=={version} failed (exit {r.returncode})"
        )
    return version


def install_gbrain():
    h = config.home()
    h.mkdir(parents=True, exist_ok=True)
    pkg = h / "package.json"
    if not pkg.exists():
        pkg.write_text(json.dumps({"name": "mnemobrain-stack", "private": True}, indent=2) + "\n")
    ref = config.get_env("MNEMOBRAIN_GBRAIN_REF")
    r = subprocess.run(
        ["bun", "add", "--ignore-scripts", f"{GBRAIN_REPO}#{ref}"], cwd=str(h), check=False
    )
    if r.returncode != 0:
        raise SystemExit(f"deps: bun add {GBRAIN_REPO}#{ref} failed (exit {r.returncode})")
    return ref


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
