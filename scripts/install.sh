#!/bin/sh
# MnemoBrain bootstrap: verify prerequisites, create the venv, install the engines.
set -eu
cd "$(dirname "$0")/.."

need() {
    echo "mnemobrain: missing $1" >&2
    echo "install it with: $2" >&2
    exit 1
}

command -v python3 >/dev/null 2>&1 || \
    need "python3" "apt install python3 python3-venv  # Debian/Ubuntu; brew install python on macOS"

python3 - <<'EOF' || need "python >= 3.11" "apt install python3.11  # or newer; brew install python on macOS"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
EOF

command -v bun >/dev/null 2>&1 || \
    need "bun (>= 1.3.11)" "curl -fsSL https://bun.sh/install | bash"

[ -d .venv ] || python3 -m venv .venv || \
    need "python venv module" "apt install python3-venv  # Debian/Ubuntu"

./.venv/bin/python -m pip install -e .

echo "mnemobrain: bootstrap done, installing engines" >&2
exec ./.venv/bin/mnemobrain install
