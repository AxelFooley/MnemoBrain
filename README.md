[![CI](https://github.com/AxelFooley/MnemoBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/AxelFooley/MnemoBrain/actions/workflows/ci.yml)
[![CodeQL](https://github.com/AxelFooley/MnemoBrain/actions/workflows/codeql.yml/badge.svg)](https://github.com/AxelFooley/MnemoBrain/actions/workflows/codeql.yml)

# MnemoBrain

MnemoBrain gives any AI agent a two-engine memory system: **Mnemosyne** (reflex
memory: automatic recall and injection every conversation turn) and **GBrain**
(deliberate knowledge: a searchable page brain with entity/take/graph layers).
MnemoBrain implements neither engine. It is the installer, launcher, and
doctor: it installs both engines as pinned dependencies, writes one defaults
config, manages the GBrain HTTP service, and verifies the whole stack.

```
agent ──▶ mnemosyne  (reflex: auto recall + inject per turn)
     └──▶ gbrain     (deliberate: searchable pages over HTTP/MCP)
```

## How it works

The reflex loop is hooked per turn: before every model call, a pre-LLM hook
recalls matching Mnemosyne memories, injects them into the prompt, and the
turn is stored afterwards. The deliberate loop is explicit: the agent reads
and writes GBrain pages over MCP/CLI when it decides to. Full wiring:
[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).
[templates/AGENT-SYSTEM-PROMPT.md](templates/AGENT-SYSTEM-PROMPT.md) makes the
agent actually use it; [docs/OPERATIONS.md](docs/OPERATIONS.md) ships the
watchdog jobs that keep memory healthy.

## Quick start

```sh
git clone https://github.com/AxelFooley/MnemoBrain && cd MnemoBrain
./scripts/install.sh
export PATH="$HOME/.mnemobrain/bin:$PATH"   # shim created by install
mnemobrain init
mnemobrain start gbrain
mnemobrain doctor
```

## Commands

| Command | Does |
|---|---|
| `mnemobrain install` | installs pinned engines (mnemosyne via pip, gbrain via bun) and the defaults config |
| `mnemobrain init` | creates the `$MNEMOBRAIN_HOME` layout + `config/mnemobrain.yaml` (idempotent) |
| `mnemobrain start gbrain` | starts the GBrain HTTP service, pidfile-managed |
| `mnemobrain stop gbrain` | stops it |
| `mnemobrain status` | one-line service + health status |
| `mnemobrain doctor` | read-only health check, prints a fix line per problem |
| `mnemobrain env` | prints `export` lines to wire the stack into any environment |

## Requirements

- Linux (primary target) or macOS (best-effort)
- python3 >= 3.11
- bun >= 1.3.11
- optional: Ollama with an embedding model (`ollama pull bge-m3`), or any
  OpenAI-compatible embeddings endpoint

## Configuration

All knobs are env vars with defaults; the full table lives in
[docs/CONFIG.md](docs/CONFIG.md). The three most common overrides:

```sh
export MNEMOBRAIN_HOME="$HOME/.mnemobrain"     # where all state lives
export MNEMOBRAIN_GBRAIN_PORT="3131"           # GBrain HTTP port
export MNEMOBRAIN_EMBED_MODEL="ollama:bge-m3"  # embedding model id
```

## Using with an AI agent

Point your agent at [SKILL.md](SKILL.md). It is written as operational
instructions an installing agent can follow end to end, with a verification
step after each command.

## Connect an agent over MCP (credentials)

GBrain's HTTP MCP surface requires a bearer credential; a client that
connects without one gets `invalid_token`. Provision one credential per
agent with `gbrain mcp grant`, then hand it to that agent with
`gbrain connect`:

```sh
GB="$MNEMOBRAIN_HOME/node_modules/.bin/gbrain"
URL="http://127.0.0.1:${MNEMOBRAIN_GBRAIN_PORT:-3131}"

# 1. Mint a credential (works with the service stopped; against a running
#    service pass --admin-token-file, or set GBRAIN_ADMIN_BOOTSTRAP_TOKEN).
HOME="$MNEMOBRAIN_HOME" "$GB" mcp grant my-agent --harness generic \
  --profile memory-writer --url "$URL" --credentials-out "$HOME/my-agent-cred.json"

# 2. Install the handoff. --install wires supported harnesses directly
#    (claude-code, codex, opencode); without it, connect prints a
#    copy-paste block for any other client.
"$GB" connect "$URL" --harness generic --credentials-file "$HOME/my-agent-cred.json"

# 3. Once the client is configured, verify the wiring (the client id is in
#    the credential file).
"$GB" mcp verify --client <client-id> --harness generic --url "$URL" \
  --credentials-file "$HOME/my-agent-cred.json"
```

`gbrain mcp adapters` lists the harness ids with built-in wiring. For a
client without an adapter (including Hermes), use `generic` and add the MCP
URL plus an `Authorization: Bearer <access_token>` header from the
credential file to that client's MCP configuration. Keep the credential
file private.

## Running GBrain under your own supervisor (optional)

`$MNEMOBRAIN_HOME/services/run_gbrain.sh` is a plain script; any supervisor
works.

systemd user unit:

```ini
[Unit]
Description=MnemoBrain GBrain

[Service]
ExecStart=%h/.mnemobrain/services/run_gbrain.sh
Restart=on-failure

[Install]
WantedBy=default.target
```

pm2:

```sh
pm2 start "$HOME/.mnemobrain/services/run_gbrain.sh" --name gbrain
```

If a supervisor owns the service instead of `mnemobrain start`, `mnemobrain
status` shows stopped (no pidfile) — check health with `mnemobrain doctor`
instead.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, local checks, and the
CI/merge rules.

## License

MIT — see [LICENSE](LICENSE).
