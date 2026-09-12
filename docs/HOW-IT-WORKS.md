# How it works

MnemoBrain is glue around two memory engines that answer two different
questions. **Mnemosyne** is the reflex: it remembers what happens in
conversations and injects the relevant parts back, automatically, every turn.
**GBrain** is the deliberate brain: the agent (or you) explicitly write down
durable knowledge — entities, takes, research, runbooks — and query it later.
MnemoBrain installs, configures, launches, and health-checks both; it contains
no memory logic of its own.

## The two engines

| | Mnemosyne (reflex) | GBrain (deliberate) |
|---|---|---|
| What it remembers | conversation turns, facts, preferences — written automatically | curated pages: entities, takes, research, runbooks |
| How it's accessed | in-process Python (SQLite, no server) | CLI + HTTP service (port 3131) that doubles as an MCP endpoint |
| When the agent touches it | every turn, implicitly (recall + inject) | explicitly, when it decides to write or look something up |
| Where data lives | `$MNEMOSYNE_DATA_DIR` (`$MNEMOBRAIN_HOME/data/mnemosyne`) | `$MNEMOBRAIN_HOME/.gbrain/` (follows the service's HOME) |
| Latency profile | sub-millisecond, local | local service, searchable index + embeddings |

The split mirrors how people use memory: most of what an agent needs this turn
is "what has already been said", which should cost nothing and require no
decision. A smaller set of knowledge is worth writing down deliberately,
structuring, and searching semantically. Two engines, two access patterns.

## The reflex loop (how Mnemosyne hooks into an agent)

There are three ways to wire Mnemosyne in:

1. **Framework hook.** Agent frameworks with a pre-LLM hook call Mnemosyne
   before every model call: the hook passes the user's message, Mnemosyne
   recalls relevant memories and returns a context block the framework injects
   into the prompt; the same cycle stores the turn afterwards. In Hermes this
   is the `pre_llm_call` hook plus the bundled `hermes_memory_provider`, whose
   `prefetch(query, session_id)` returns the rendered context. Other
   frameworks: Mnemosyne upstream ships integration docs (claude-code, codex,
   cursor, windsurf) via its `mnemosyne-install` entry point — see
   `mnemosyne-install --help` and the upstream docs.
2. **Direct SDK.** For your own code:

   ```python
   from mnemosyne import remember, recall
   remember("User prefers dark mode", importance=0.9)
   recall("user preferences")
   ```

   Zero servers, zero API keys.
3. **CLI/inspection.** The `mnemosyne` CLI and `mnemosyne-browser` for looking
   at what actually got stored.

Mnemosyne runs **in-process** — MnemoBrain starts no
service for it; only GBrain gets a daemon.

## The deliberate loop (how GBrain is used)

Writes and reads go through the CLI (`gbrain put/get/capture`), or
programmatically by any MCP client against `http://127.0.0.1:3131` (health at
`/health`). The agent decides when — "remember this project decision", "what
do we know about X". Nothing is written or read implicitly.

Pages get chunked and embedded at write time (the embedder comes from
`.gbrain/config.json`, which `mnemobrain` seeds from `MNEMOBRAIN_EMBED_MODEL`
/ `MNEMOBRAIN_EMBED_DIMS`), so queries are semantic, not just keyword.

Single writer: the CLI refuses writes while `gbrain serve` holds the store —
that is why the skill smoke-tests before starting the service.

## What MnemoBrain itself wires (the glue)

```
agent framework ──hook──▶ mnemosyne (in-process, MNEMOSYNE_DATA_DIR)
      │
      └─MCP/CLI──▶ gbrain serve :3131 ──▶ $MNEMOBRAIN_HOME/.gbrain
                        │
                        └──▶ embeddings via MNEMOBRAIN_OLLAMA_URL (OpenAI-compatible)
```

- `mnemobrain env` exports the contract: `MNEMOSYNE_DATA_DIR`,
  `MNEMOBRAIN_GBRAIN_URL`, plus the embed model/dims — source these in the
  agent's environment and both surfaces resolve.
- The launcher (`services/run_gbrain.sh`) isolates `HOME=$MNEMOBRAIN_HOME` so
  gbrain state lands under the MnemoBrain root, and maps
  `MNEMOBRAIN_OLLAMA_URL` to `OLLAMA_BASE_URL` for the service process.
- `doctor` verifies both loops: service health and embedder reachability,
  read-only, with a fix line per problem.

What MnemoBrain does **not** do: no memory logic, no background indexer, no
schema of its own. Both engines are pristine upstream pins; everything
MnemoBrain adds is install, config, launch, and health checks.

## Data flow of one conversation

User message arrives → the pre-LLM hook recalls matching Mnemosyne memories →
the returned context block is injected into the prompt → the agent answers,
and may query gbrain for deliberate knowledge ("what do we know about this
repo's release process?") → the turn is stored to Mnemosyne automatically →
anything durable the agent explicitly writes down lands as a gbrain page. The
reflex loop carries the conversation; the deliberate loop accumulates what is
worth keeping.
