"""Read-only health checks. Each prints PASS/WARN/FAIL plus a one-line fix."""

import importlib.metadata
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from mnemobrain import __version__, config, deps

TIMEOUT = 2
HERMES_ROOT_ENV = "MNEMOBRAIN_HERMES_ROOT"
HERMES_ROOT_SEARCH = 5


def hermes_root():
    """Best-effort root of Hermes' install (a dir holding hermes_constants.py).

    MNEMOBRAIN_HERMES_ROOT (process env only — deliberate live override) wins;
    otherwise walk up from the `hermes` launcher a bounded number of levels.
    """
    env_root = os.environ.get(HERMES_ROOT_ENV)
    if env_root:
        return pathlib.Path(env_root).resolve()
    found = shutil.which("hermes")
    if not found:
        return None
    probe = pathlib.Path(found).resolve()
    for _ in range(HERMES_ROOT_SEARCH + 1):
        if (probe / "hermes_constants.py").is_file():
            return probe
        if probe.parent == probe:
            return None
        probe = probe.parent
    return None


def _print(status, name, detail, fix=""):
    line = f"{status:<4} {name:<12} {detail}"
    if fix:
        line += f"\n     fix: {fix}"
    print(line, file=sys.stderr)
    return status


def health_check():
    url = config.get_env("MNEMOBRAIN_GBRAIN_URL")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode() or "{}")
        return True, f"ok at {url} (version {data.get('version', 'unknown')})"
    except urllib.error.HTTPError as e:
        return True, f"reachable at {url} (HTTP {e.code}, no JSON health body)"
    except Exception as e:  # noqa: BLE001
        return False, f"unreachable at {url} ({type(e).__name__}: {e})"


def mcp_url():
    url = config.get_env("MNEMOBRAIN_GBRAIN_URL")
    if url.endswith("/health"):
        return url[: -len("/health")] + "/mcp"
    return url + "/mcp"


def admin_token():
    tok = os.environ.get("GBRAIN_ADMIN_BOOTSTRAP_TOKEN")
    if tok:
        return tok
    try:
        return (config.home() / "gbrain-admin.token").read_text().strip() or None
    except OSError:
        return None


def mcp_auth_check():
    """POST an MCP initialize against mcp_url; returns (status, detail, fix) or None."""
    token = admin_token()
    if token is None:
        _print(
            "SKIP",
            "mcp-auth",
            "no admin token (set GBRAIN_ADMIN_BOOTSTRAP_TOKEN or <home>/gbrain-admin.token)",
        )
        return None
    url = mcp_url()
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "mnemobrain-doctor", "version": __version__},
            },
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            r.read()
        return "PASS", f"mcp initialize ok at {url}", ""
    except urllib.error.HTTPError as e:
        if e.code == 401:
            try:
                err = json.loads(e.read().decode()).get("error", "invalid_token")
            except Exception:  # noqa: BLE001
                err = "invalid_token"
            return (
                "FAIL",
                f"process alive but token rejected ({err})",
                "mint a fresh admin token / re-run agent register",
            )
        return "WARN", f"mcp at {url} returned HTTP {e.code}", ""
    except Exception as e:  # noqa: BLE001
        _print(
            "SKIP",
            "mcp-auth",
            f"unreachable ({type(e).__name__}) — liveness check above covers it",
        )
        return None


def check_python():
    ok = sys.version_info >= (3, 11)
    detail = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    fix = "" if ok else "install python 3.11+ (apt install python3 / brew install python)"
    return _print("PASS" if ok else "FAIL", "python", detail, fix)


def check_bun():
    ok, detail, fix = deps.check_bun()
    return _print("PASS" if ok else "FAIL", "bun", detail, fix)


def check_mnemosyne():
    pin = config.get_env("MNEMOBRAIN_MNEMOSYNE_VERSION")
    try:
        found = importlib.metadata.version("mnemosyne-memory")
    except importlib.metadata.PackageNotFoundError:
        found = None
    if found == pin:
        return _print("PASS", "mnemosyne", f"mnemosyne-memory=={found}")
    if found is None:
        return _print(
            "FAIL",
            "mnemosyne",
            "mnemosyne-memory not importable in this interpreter",
            f"activate the venv from scripts/install.sh; pip install mnemosyne-memory=={pin}",
        )
    return _print(
        "FAIL", "mnemosyne", f"found {found}, pinned {pin}", f"pip install mnemosyne-memory=={pin}"
    )


def check_mnemosyne_hermes():
    try:
        found = importlib.metadata.version("mnemosyne-hermes")
    except importlib.metadata.PackageNotFoundError:
        return _print(
            "SKIP",
            "mnemosyne-hermes",
            "not installed in this interpreter (not a Hermes deployment?)",
        )
    if found in deps.MNEMOSYNE_HERMES_KNOWN_BAD:
        return _print(
            "FAIL",
            "mnemosyne-hermes",
            f"{found} is known-unconstructible (P1b binding guard raises in __init__)",
            f"mnemosyne-hermes {found} cannot build its provider; install a fixed release",
        )
    code = (
        "import hermes_constants\n"
        "from mnemosyne_hermes import MnemosyneMemoryProvider as P\n"
        "P(); print('OK')\n"
    )
    root = hermes_root()
    if root is None:
        return _print(
            "SKIP",
            "mnemosyne-hermes",
            f"{found} installed, but Hermes' runtime was not locatable — construction probe"
            " not conclusive",
            "set MNEMOBRAIN_HERMES_ROOT to Hermes' install directory to enable this check",
        )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return _print("WARN", "mnemosyne-hermes", "provider construction timed out after 60s")
    if r.returncode == 0 and "OK" in r.stdout:
        return _print("PASS", "mnemosyne-hermes", f"{found} provider constructs")
    out = (r.stderr or "") + (r.stdout or "")
    if "ModuleNotFoundError" in out:
        if "hermes_constants" in out:
            return _print(
                "SKIP",
                "mnemosyne-hermes",
                "could not establish Hermes' import environment — probe not conclusive",
            )
        return _print(
            "SKIP",
            "mnemosyne-hermes",
            "glue not importable in this interpreter (not a Hermes deployment?)",
        )
    lines = [line for line in out.splitlines() if line.strip()]
    detail = lines[-1][:160] if lines else "provider construction failed with no output"
    return _print(
        "FAIL",
        "mnemosyne-hermes",
        f"{found}: {detail}",
        f"mnemosyne-hermes {found} cannot build its provider; install a fixed release",
    )


def check_gbrain_bin():
    path = deps.gbrain_bin()
    if path:
        return _print("PASS", "gbrain-bin", str(path))
    return _print(
        "FAIL",
        "gbrain-bin",
        "gbrain binary not found under $MNEMOBRAIN_HOME/node_modules/.bin",
        "run: mnemobrain install",
    )


def check_gbrain_version():
    installed = None
    pkg_json = config.home() / "node_modules" / "gbrain" / "package.json"
    try:
        installed = json.loads(pkg_json.read_text()).get("version")
    except (OSError, ValueError):
        return None
    if not installed:
        return None
    pinned = config.get_env("MNEMOBRAIN_GBRAIN_REF")
    if not re.match(r"v?\d", pinned):
        return _print("SKIP", "gbrain-version", "ref is not a version tag")
    if installed == pinned.lstrip("v"):
        return _print("PASS", "gbrain-version", f"installed {installed}, pinned {pinned}")
    return _print(
        "FAIL",
        "gbrain-version",
        f"installed {installed}, pinned {pinned}",
        f"rm {config.home()}/bun.lock && bun install (or: mnemobrain install), then re-check",
    )


def check_gbrain_cfg():
    path = config.home() / ".gbrain" / "config.json"
    if not path.exists():
        return _print("WARN", "gbrain-cfg", f"missing: {path}", "run: mnemobrain init")
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError) as e:
        return _print(
            "WARN",
            "gbrain-cfg",
            f"unparseable: {path} ({e})",
            f"edit or remove {path}, then run: mnemobrain init",
        )
    want = config.get_env("MNEMOBRAIN_EMBED_MODEL")
    got = data.get("embedding_model")
    if got == want:
        return _print("PASS", "gbrain-cfg", f"{path} (embedding_model {got})")
    return _print(
        "WARN",
        "gbrain-cfg",
        f"embedding_model {got!r} in config.json but {want!r} resolved",
        f"edit {path} or MNEMOBRAIN_EMBED_MODEL",
    )


def check_dirs():
    missing = [str(d) for d in config.dirs().values() if not (d.exists() and os.access(d, os.W_OK))]
    if not missing:
        return _print("PASS", "data-dirs", f"present and writable under {config.home()}")
    return _print(
        "FAIL", "data-dirs", f"missing or unwritable: {', '.join(missing)}", "run: mnemobrain init"
    )


def check_health():
    ok, detail = health_check()
    if ok:
        return _print("PASS", "gbrain-svc", detail)
    return _print("FAIL", "gbrain-svc", detail, "run: mnemobrain start gbrain")


def check_mcp_auth():
    res = mcp_auth_check()
    if res is None:
        return None
    status, detail, fix = res
    return _print(status, "mcp-auth", detail, fix)


def check_ollama():
    url = config.get_env("MNEMOBRAIN_OLLAMA_URL")
    model = config.get_env("MNEMOBRAIN_EMBED_MODEL")
    try:
        urllib.request.urlopen(url, timeout=TIMEOUT)
        reachable = True
    except urllib.error.HTTPError:
        reachable = True
    except Exception:  # noqa: BLE001
        reachable = False
    if reachable:
        return _print("PASS", "ollama", f"embedding engine reachable at {url}")
    return _print(
        "WARN",
        "ollama",
        f"embedding engine unreachable at {url} (model {model})",
        "optional: install ollama (https://ollama.com) then run: ollama pull bge-m3",
    )


def check_disk():
    target = config.home()
    while not target.exists() and target != target.parent:
        target = target.parent
    free = shutil.disk_usage(target).free
    if free > 1 << 30:
        return _print("PASS", "disk", f"{free >> 20} MiB free at {target}")
    return _print(
        "FAIL",
        "disk",
        f"only {free >> 20} MiB free at {target}",
        "free at least 1 GiB of disk space",
    )


def check_pidfile():
    path = config.dirs()["services"] / "gbrain.pid"
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return _print("WARN", "pidfile", f"unparseable: {path}", f"remove it: rm {path}")
    if deps.pid_alive(pid):
        return _print("PASS", "pidfile", f"gbrain pid {pid}")
    return _print(
        "WARN",
        "pidfile",
        f"stale pidfile {path} (pid {pid} not running)",
        "run: mnemobrain stop gbrain",
    )


CHECKS = (
    check_python,
    check_bun,
    check_mnemosyne,
    check_mnemosyne_hermes,
    check_gbrain_bin,
    check_gbrain_version,
    check_gbrain_cfg,
    check_dirs,
    check_health,
    check_mcp_auth,
    check_ollama,
    check_disk,
    check_pidfile,
)


def run():
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for check in CHECKS:
        status = check()
        if status:
            counts[status] = counts.get(status, 0) + 1
    print(f"doctor: {counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail")
    return 1 if counts["FAIL"] else 0
