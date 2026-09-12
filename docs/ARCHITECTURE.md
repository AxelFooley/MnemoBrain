# Architecture

MnemoBrain installs, configures, launches, and verifies two independent memory
engines. It contains no memory logic itself.

## The two engines

**Mnemosyne** (PyPI `mnemosyne-memory`) is reflex memory. It runs in-process
inside the agent runtime: every conversation turn it recalls relevant memories
and injects them into context, and stores new turns automatically. The agent
does not call it explicitly. Its stores live at
`$MNEMOBRAIN_HOME/data/mnemosyne` (exported as `MNEMOSYNE_HOME`). Embeddings
come from the configured OpenAI-compatible endpoint (default: local Ollama,
model `ollama:bge-m3`, 1024 dims).

**GBrain** (GitHub `garrytan/gbrain`) is deliberate knowledge. It is a
searchable page brain with entity, take, and graph layers; the agent or user
explicitly writes pages and queries them. It runs as an HTTP service
(`gbrain serve`) on `$MNEMOBRAIN_GBRAIN_PORT` (default 3131) and doubles as an
MCP endpoint. Its pages live at `$MNEMOBRAIN_HOME/data/gbrain` (exported as
`GBRAIN_HOME`); the launcher also sets `HOME=$MNEMOBRAIN_HOME`, so gbrain's
dotfile state lands predictably under the MnemoBrain root.

## Wiring

```
agent ──▶ mnemosyne  (reflex: auto recall + inject per turn, in-process)
     └──▶ gbrain     (deliberate: pages/graph over HTTP + MCP)
```

MnemoBrain does four things:

1. **install** — pins and installs both engines:
   `pip install mnemosyne-memory==$MNEMOBRAIN_MNEMOSYNE_VERSION` into the repo
   venv; `bun add --ignore-scripts github:garrytan/gbrain#$MNEMOBRAIN_GBRAIN_REF`
   into `$MNEMOBRAIN_HOME` (which gets a minimal `package.json` if absent).
2. **config** — writes one `KEY: value` file at
   `$MNEMOBRAIN_HOME/config/mnemobrain.yaml` from a single defaults table in
   `src/mnemobrain/config.py` (parsed by a 15-line stdlib loader, no yaml lib).
   Precedence: process env > config file > built-in default. All writes are
   atomic (`os.replace`) and idempotent (skip when bytes are unchanged).
3. **launch** — `mnemobrain start gbrain` renders
   `$MNEMOBRAIN_HOME/services/run_gbrain.sh` (fixed env, fixed port, exec of
   the pinned binary) and starts it via `subprocess.Popen` in a new session,
   recording the pid in `services/gbrain.pid`. Logs go to `logs/gbrain.log`.
   The same script works under systemd, pm2, or any supervisor.
4. **verify** — `mnemobrain doctor` runs read-only checks (toolchain, engine
   versions, service health, dirs, disk, pidfile) and prints a fix line for
   every non-PASS result.

## Data layout

```
$MNEMOBRAIN_HOME/
  bin/                     venv shims (mnemobrain)
  services/                run_gbrain.sh, gbrain.pid
  config/mnemobrain.yaml   stack defaults (env overrides them)
  data/gbrain/             gbrain pages
  data/mnemosyne/          mnemosyne stores
  logs/gbrain.log          service output
  node_modules/            installed gbrain (bun-managed)
  package.json             bun bookkeeping
```

## Service model

`mnemobrain start|stop|status gbrain` own the pidfile lifecycle; there is no
shell-level backgrounding anywhere in the codebase. Users who prefer their own
supervisor point it at `services/run_gbrain.sh` (README has optional systemd
and pm2 snippets).
