---
name: mnemobrain
description: Install and operate the MnemoBrain memory stack (Mnemosyne reflex memory + GBrain knowledge brain) for any AI agent.
---

# MnemoBrain install skill

MnemoBrain wires two engines into an agent: Mnemosyne (reflex memory: automatic
recall/injection per conversation turn) and GBrain (deliberate knowledge:
searchable pages served over HTTP + MCP). Follow the steps in order.

**IDEMPOTENCE:** every step is safe to re-run on an installed system —
`install` repairs/validates, `init` never clobbers data or config, `doctor` is
read-only. If a step fails, run `mnemobrain doctor`, follow its printed fix
lines, then re-run the failed step.

## 1. Preflight

Run:

```sh
python3 --version
bun --version
```

Verification: python3 prints 3.11 or newer; bun prints 1.3.11 or newer.
If either is missing, print the official install command, stop, and report:

```sh
python3:  apt install python3 python3-venv    # Debian/Ubuntu; brew install python on macOS
bun:      curl -fsSL https://bun.sh/install | bash
```

## 2. Bootstrap the CLI

```sh
git clone https://github.com/AxelFooley/MnemoBrain
cd MnemoBrain
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
```

Verification: `./.venv/bin/mnemobrain -h` prints usage and exits 0.

## 3. Install the engines

```sh
./.venv/bin/mnemobrain install
```

What it does: verifies bun >= 1.3.11; pip-installs `mnemosyne-memory==3.15.1`
into the venv; `bun add github:garrytan/gbrain#v0.50.0.0 --ignore-scripts`
into `$MNEMOBRAIN_HOME`; creates the data layout; writes the defaults config
and gbrain's `.gbrain/config.json` (create-if-absent).
Pins are env-overridable (`MNEMOBRAIN_MNEMOSYNE_VERSION`,
`MNEMOBRAIN_GBRAIN_REF`) — never hardcode a different ref anywhere else.

Expected output shape: `install:` progress lines on stderr, one final
`install: ok (...)` line on stdout, exit code 0.

Verification: exit 0, and this file exists:
`$MNEMOBRAIN_HOME/node_modules/.bin/gbrain`.

## 4. Initialize state

```sh
./.venv/bin/mnemobrain init
```

Creates the directory layout and `$MNEMOBRAIN_HOME/config/mnemobrain.yaml`, plus
`$MNEMOBRAIN_HOME/.gbrain/config.json` with the resolved embedder (gbrain reads
this file; it is written create-if-absent, never overwritten).
Idempotent: re-running prints `init: config unchanged` and
`init: gbrain config.json kept (already present)` when nothing changed and
never touches existing data.

Verification: `cat "$MNEMOBRAIN_HOME/config/mnemobrain.yaml"` shows `key: value`
lines including `mnemosyne_version` and `gbrain_ref`; run the command a second
time — it must exit 0 and leave the file bytes identical.

## 5. Choose the embedding path

Default (Ollama, local):

```sh
ollama pull bge-m3
```

or any OpenAI-compatible endpoint:

```sh
export MNEMOBRAIN_OLLAMA_URL="https://your-endpoint.example/v1"
export MNEMOBRAIN_EMBED_MODEL="text-embedding-3-small"
export MNEMOBRAIN_EMBED_DIMS="1536"
./.venv/bin/mnemobrain init   # persists the values into the config file; also
                              # writes .gbrain/config.json (create-if-absent)
```

If `.gbrain/config.json` already exists with a different `embedding_model`,
edit it to match (or remove it and re-run `init`) — gbrain reads the model from
that file, not from `MNEMOBRAIN_EMBED_MODEL`.

Verification: `./.venv/bin/mnemobrain doctor` prints PASS or WARN on the
`ollama` line. WARN is acceptable only here and for the pidfile line: the
embedding engine is optional at install time. If you skipped it intentionally,
note that reflex recall stays degraded until it is reachable.

## 6. Start GBrain and verify the stack

```sh
./.venv/bin/mnemobrain start gbrain
./.venv/bin/mnemobrain doctor
```

Verification: `doctor` exits 0 and its summary line ends in `0 fail`. Every
FAIL must be resolved via its printed fix line before continuing.

## 7. Smoke test the knowledge brain

```sh
eval "$(./.venv/bin/mnemobrain env)"
GBRAIN="$MNEMOBRAIN_HOME/node_modules/.bin/gbrain"
HOME="$MNEMOBRAIN_HOME" "$GBRAIN" put mnemobrain-smoke --content "# smoke

mnemobrain smoke test"
HOME="$MNEMOBRAIN_HOME" "$GBRAIN" get mnemobrain-smoke   # must contain: mnemobrain smoke test
HOME="$MNEMOBRAIN_HOME" "$GBRAIN" delete mnemobrain-smoke   # cleanup, exit 0
```

Verification: `get` prints the body, `delete` exits 0, and `mnemobrain doctor`
still reports the gbrain service healthy afterwards.

## 8. Wire into the agent framework

In the agent's environment (profile, launcher, or supervisor unit):

```sh
eval "$(mnemobrain env)"
```

That exports `MNEMOSYNE_DATA_DIR` plus the `MNEMOBRAIN_*` knobs. The gbrain
launcher (`services/run_gbrain.sh`) separately isolates `HOME=$MNEMOBRAIN_HOME`
and maps `MNEMOBRAIN_OLLAMA_URL` to `OLLAMA_BASE_URL` for the service process.
Then point the two memory surfaces at the engines:

- **reflex memory**: the in-process `mnemosyne-memory` package; stores live at
  `$MNEMOSYNE_DATA_DIR`.
- **deliberate knowledge**: GBrain HTTP + MCP at
  `http://127.0.0.1:$MNEMOBRAIN_GBRAIN_PORT` (health URL:
  `$MNEMOBRAIN_GBRAIN_URL`).

### OPTIONAL: Hermes appendix

- symlink this repo into Hermes' skills directory so the install steps travel
  with the agent: `ln -s <this repo> <hermes-skills-dir>/mnemobrain`
- set `memory.provider: mnemosyne` in Hermes' `config.yaml`
- register Hermes' gbrain MCP client against
  `http://127.0.0.1:$MNEMOBRAIN_GBRAIN_PORT`

## Failure protocol

Re-run `mnemobrain doctor` and follow its fix lines. Never delete
`$MNEMOBRAIN_HOME/data` to "fix" a problem — back it up first (see
[docs/UPGRADING.md](docs/UPGRADING.md)).
