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

## License

MIT — see [LICENSE](LICENSE).
