"""Engine dependency checks and installs. Version pins come from config.get_env only."""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

from mnemobrain import config

MCP_SMOKE_TIMEOUT = 30  # seconds; a #20-style break exits within ~1s
MCP_SMOKE_PROBE = "import sys; from mnemosyne.mcp_server import main; main([])"
_EXTRA_MISSING = re.compile("does not provide the extra", re.IGNORECASE)

MIN_BUN = (1, 3, 11)
BUN_INSTALL = (
    "curl -fsSL https://bun.sh/install | bash  (and ensure ~/.bun/bin is "
    "exported in ~/.profile for login shells)"
)


def bun_bin():
    """Locate bun: PATH first, then the default install dir (WSL login shells
    that do not read .bashrc otherwise produce a false "not found")."""
    found = shutil.which("bun")
    if found:
        return pathlib.Path(found)
    fallback = pathlib.Path.home() / ".bun" / "bin" / "bun"
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return fallback
    return None


def bun_version():
    bun = bun_bin()
    if bun is None:
        return None
    r = subprocess.run([str(bun), "--version"], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return None
    try:
        return version_tuple(r.stdout)
    except ValueError:
        return None


GBRAIN_REPO = "github:garrytan/gbrain"


def version_tuple(text):
    parts = []
    for piece in text.strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            raise ValueError(f"unparseable version: {text!r}")
        parts.append(int(digits))
    return tuple(parts)


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


def _pip_install(spec):
    """Run pip for spec, streaming its output through (never silent)."""
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", spec],
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    return r


def mcp_smoke():
    """(ok, detail): spawn the real MCP entry `mnemosyne mcp` with stdin at EOF
    and verify it starts without import errors (#20). The engine's own error
    containment reports a broken install only as the opaque
    'cli_unexpected_failure' at first agent use, so the installer must check
    itself and surface the engine's real error text instead."""
    try:
        r = subprocess.run(
            [sys.executable, "-c", MCP_SMOKE_PROBE],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=MCP_SMOKE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return True, f"mcp server still running after {MCP_SMOKE_TIMEOUT}s — no import errors"
    return (r.returncode == 0, (r.stderr or r.stdout or "").strip())


def install_mnemosyne():
    version = config.get_env("MNEMOBRAIN_MNEMOSYNE_VERSION")
    base = f"mnemosyne-memory=={version}"
    # Install the [mcp] extra by default (#20): it provides the mcp/anyio
    # deps the MCP server needs, which a bare install misses (4.0.0b3+ ships
    # only PyYAML). Pins without the extra degrade to a bare install with a
    # loud warning line — never silent.
    r = _pip_install(f"mnemosyne-memory[mcp]=={version}")
    probed = r.stderr + r.stdout
    if r.returncode != 0:
        if _EXTRA_MISSING.search(probed):
            print(
                f"deps: warning: mnemosyne-memory=={version} defines no [mcp] extra; "
                "installing bare",
                file=sys.stderr,
            )
            r = _pip_install(base)
            if r.returncode != 0:
                raise SystemExit(f"deps: pip install {base} failed (exit {r.returncode})")
        else:
            raise SystemExit(
                f"deps: pip install mnemosyne-memory[mcp]=={version} failed (exit {r.returncode})"
            )
    elif _EXTRA_MISSING.search(probed):
        print(
            f"deps: warning: mnemosyne-memory=={version} defines no [mcp] extra; "
            "installed bare — MCP server may be unavailable until it is installed too",
            file=sys.stderr,
        )
    ok, detail = mcp_smoke()
    if not ok:
        raise SystemExit(
            f"deps: post-install mcp smoke check failed:\n{detail}\n"
            f'deps: verify with: pip install "mnemosyne-memory[mcp]=={version}"'
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
