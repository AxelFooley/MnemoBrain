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

What it does: verifies bun >= 1.3.11; pip-installs the configured
`MNEMOBRAIN_MNEMOSYNE_VERSION` pin of `mnemosyne-memory` into the venv;
`bun add`s the configured `MNEMOBRAIN_GBRAIN_REF` of
`github:garrytan/gbrain --ignore-scripts` into `$MNEMOBRAIN_HOME`; creates
the data layout; writes the defaults config and gbrain's
`.gbrain/config.json` (create-if-absent). The pins in effect are the
resolved `MNEMOBRAIN_MNEMOSYNE_VERSION` / `MNEMOBRAIN_GBRAIN_REF` values
(run `mnemobrain env` to print them); they are env-overridable — never
hardcode a different ref anywhere else.

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

## 6. Smoke test the knowledge brain

```sh
eval "$(./.venv/bin/mnemobrain env)"
HOME="$MNEMOBRAIN_HOME" "$MNEMOBRAIN_HOME/node_modules/.bin/gbrain" put mnemobrain-smoke --content "# smoke

mnemobrain smoke test"
HOME="$MNEMOBRAIN_HOME" "$MNEMOBRAIN_HOME/node_modules/.bin/gbrain" get mnemobrain-smoke   # must contain: mnemobrain smoke test
HOME="$MNEMOBRAIN_HOME" "$MNEMOBRAIN_HOME/node_modules/.bin/gbrain" delete mnemobrain-smoke   # cleanup, exit 0
```

Run the smoke test while the service is stopped — gbrain is a single-writer
store and its CLI refuses writes while `gbrain serve` holds the database.

Verification: `get` prints the body and `delete` exits 0. Note: on some
gbrain versions `delete` can lose a revision race after `put` and leave the
page in place despite exiting 0; confirm with a final `get`. A lingering
smoke page is harmless, and the conflict can be reported upstream.

## 7. Start GBrain and verify the stack

```sh
./.venv/bin/mnemobrain start gbrain
./.venv/bin/mnemobrain doctor
```

Verification: `doctor` exits 0 and its summary line ends in `0 fail`. Every
FAIL must be resolved via its printed fix line before continuing.

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

GBrain requires a bearer credential on its HTTP MCP surface. Provision one
per agent (works with the service stopped) and hand it over — see the README
section "Connect an agent over MCP (credentials)":
`gbrain mcp grant <name> --harness <adapter> --url <mcp-url> --credentials-out <file>`,
then `gbrain connect <mcp-url> --harness <adapter> --credentials-file <file>`.
`gbrain mcp adapters` lists harness ids; use `generic` for clients without
an adapter and add the MCP URL plus bearer header to the client's own MCP
configuration.

For the full wiring explanation (hooks, SDK, MCP, env contract), see
[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

### OPTIONAL: skills-directory integration

If your agent supports the portable `SKILL.md` convention, symlink this repo
into its skills directory so the install steps travel with the agent:
`ln -s <this repo> <skills-dir>/mnemobrain`

## 9. Make it behavioral (recommended)

Paste [templates/AGENT-SYSTEM-PROMPT.md](templates/AGENT-SYSTEM-PROMPT.md) into
your agent's system prompt so it actually uses the stack, and schedule the two
jobs in [docs/OPERATIONS.md](docs/OPERATIONS.md) that keep memory healthy.

## Failure protocol

Re-run `mnemobrain doctor` and follow its fix lines. Never delete
`$MNEMOBRAIN_HOME/data` to "fix" a problem — back it up first (see
[docs/UPGRADING.md](docs/UPGRADING.md)).
