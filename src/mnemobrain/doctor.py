"""Read-only health checks. Each prints PASS/WARN/FAIL plus a one-line fix."""

import importlib.metadata
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

from mnemobrain import config, deps

TIMEOUT = 2


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
    except Exception as e:
        return False, f"unreachable at {url} ({type(e).__name__}: {e})"


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
        return _print("FAIL", "mnemosyne", "mnemosyne-memory not importable in this interpreter",
                      f"activate the venv from scripts/install.sh; pip install mnemosyne-memory=={pin}")
    return _print("FAIL", "mnemosyne", f"found {found}, pinned {pin}", f"pip install mnemosyne-memory=={pin}")


def check_gbrain_bin():
    path = deps.gbrain_bin()
    if path:
        return _print("PASS", "gbrain-bin", str(path))
    return _print("FAIL", "gbrain-bin", "gbrain binary not found under $MNEMOBRAIN_HOME/node_modules/.bin",
                  "run: mnemobrain install")


def check_dirs():
    missing = [str(d) for d in config.dirs().values() if not (d.exists() and os.access(d, os.W_OK))]
    if not missing:
        return _print("PASS", "data-dirs", f"present and writable under {config.home()}")
    return _print("FAIL", "data-dirs", f"missing or unwritable: {', '.join(missing)}", "run: mnemobrain init")


def check_health():
    ok, detail = health_check()
    if ok:
        return _print("PASS", "gbrain-svc", detail)
    return _print("FAIL", "gbrain-svc", detail, "run: mnemobrain start gbrain")


def check_ollama():
    url = config.get_env("MNEMOBRAIN_OLLAMA_URL")
    model = config.get_env("MNEMOBRAIN_EMBED_MODEL")
    try:
        urllib.request.urlopen(url, timeout=TIMEOUT)
        reachable = True
    except urllib.error.HTTPError:
        reachable = True
    except Exception:
        reachable = False
    if reachable:
        return _print("PASS", "ollama", f"embedding engine reachable at {url}")
    return _print("WARN", "ollama", f"embedding engine unreachable at {url} (model {model})",
                  "optional: install ollama (https://ollama.com) then run: ollama pull bge-m3")


def check_disk():
    target = config.home()
    while not target.exists() and target != target.parent:
        target = target.parent
    free = shutil.disk_usage(target).free
    if free > 1 << 30:
        return _print("PASS", "disk", f"{free >> 20} MiB free at {target}")
    return _print("FAIL", "disk", f"only {free >> 20} MiB free at {target}", "free at least 1 GiB of disk space")


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
    return _print("WARN", "pidfile", f"stale pidfile {path} (pid {pid} not running)", "run: mnemobrain stop gbrain")


CHECKS = (check_python, check_bun, check_mnemosyne, check_gbrain_bin, check_dirs,
          check_health, check_ollama, check_disk, check_pidfile)


def run():
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for check in CHECKS:
        status = check()
        if status:
            counts[status] += 1
    print(f"doctor: {counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail")
    return 1 if counts["FAIL"] else 0
