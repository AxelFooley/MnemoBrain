"""Path resolution, the single defaults table, and the atomic config writer.

Every environment variable in the stack is read through get_env() — no
scattered os.environ lookups elsewhere.
"""

import json
import os
import pathlib
import tempfile

DEFAULTS = {
    "MNEMOBRAIN_HOME": "~/.mnemobrain",
    "MNEMOBRAIN_GBRAIN_REF": "v0.54.1.1",
    "MNEMOBRAIN_MNEMOSYNE_VERSION": "4.0.0b3",
    "MNEMOBRAIN_GBRAIN_PORT": "3131",
    "MNEMOBRAIN_GBRAIN_URL": "",  # derived from MNEMOBRAIN_GBRAIN_PORT, see default_value()
    "MNEMOBRAIN_OLLAMA_URL": "http://localhost:11434/v1",
    "MNEMOBRAIN_EMBED_MODEL": "ollama:bge-m3",
    "MNEMOBRAIN_EMBED_DIMS": "1024",
    "MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS": "168",
}

FILE_KEYS = tuple(k for k in DEFAULTS if k != "MNEMOBRAIN_HOME")


def default_value(name):
    if name == "MNEMOBRAIN_GBRAIN_URL":
        return f"http://127.0.0.1:{get_env('MNEMOBRAIN_GBRAIN_PORT')}/health"
    return DEFAULTS[name]


def file_key(name):
    return name[len("MNEMOBRAIN_") :].lower()


def parse_config(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def get_env(name):
    """Precedence: process env > config file > built-in default."""
    if name in os.environ:
        return os.environ[name]
    if name in FILE_KEYS:
        value = parse_config(_read_config_text()).get(file_key(name))
        if value:
            return value
    return default_value(name)


def home():
    return pathlib.Path(get_env("MNEMOBRAIN_HOME")).expanduser()


def dirs():
    h = home()
    return {
        "home": h,
        "bin": h / "bin",
        "services": h / "services",
        "config": h / "config",
        "gbrain_data": h / "data" / "gbrain",
        "mnemosyne_data": h / "data" / "mnemosyne",
        "logs": h / "logs",
    }


def _read_config_text():
    try:
        return (dirs()["config"] / "mnemobrain.yaml").read_text()
    except FileNotFoundError:
        return ""


def render_config():
    lines = ["# mnemobrain stack defaults. Process env overrides these values."]
    for name in FILE_KEYS:
        lines.append(f"{file_key(name)}: {os.environ.get(name) or default_value(name)}")
    return "\n".join(lines) + "\n"


def write_atomic(path, data, executable=False):
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o755 if executable else 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return True


def init_dirs():
    created = []
    for d in dirs().values():
        if not d.exists():
            d.mkdir(parents=True)
            created.append(d)
    return created


def write_config():
    return write_atomic(dirs()["config"] / "mnemobrain.yaml", render_config().encode())


def write_gbrain_config():
    """Write <home>/.gbrain/config.json (create-if-absent) so gbrain picks up
    the configured embedder; gbrain reads it from $HOME, which the launcher
    isolates to MNEMOBRAIN_HOME. Existing files are left untouched."""
    path = home() / ".gbrain" / "config.json"
    if path.exists():
        return False
    payload = {
        "engine": "pglite",
        "database_path": str(home() / ".gbrain" / "brain.pglite"),
        "embedding_model": get_env("MNEMOBRAIN_EMBED_MODEL"),
        "embedding_dimensions": int(get_env("MNEMOBRAIN_EMBED_DIMS")),
    }
    return write_atomic(path, json.dumps(payload, indent=2).encode() + b"\n")


def env_lines():
    h = home()
    lines = [f'export MNEMOBRAIN_HOME="{h}"']
    for name in FILE_KEYS:
        lines.append(f'export {name}="{get_env(name)}"')
    lines.append(f'export MNEMOSYNE_DATA_DIR="{h}/data/mnemosyne"')
    lines.append('# optional: export PATH="$MNEMOBRAIN_HOME/bin:$PATH"  # mnemobrain shim')
    return lines
