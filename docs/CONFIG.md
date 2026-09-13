# Configuration

Every knob is an environment variable. All env reads go through one function
(`config.get_env`) with precedence: **process env > config file > built-in
default**.

`mnemobrain init` writes the resolved values to
`$MNEMOBRAIN_HOME/config/mnemobrain.yaml` (atomic, idempotent). That file is
the persistence layer: export an env var to override it for one run, or change
the pin/port/model and re-run `mnemobrain init` to persist new values.
`mnemobrain env` prints the resolved stack as `export` lines for sourcing.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `MNEMOBRAIN_HOME` | `~/.mnemobrain` | root for all state: bins, services, config, data, logs |
| `MNEMOBRAIN_GBRAIN_REF` | `v0.50.0.0` | git ref of `github:garrytan/gbrain` installed by `bun add` |
| `MNEMOBRAIN_MNEMOSYNE_VERSION` | `3.15.1` | PyPI pin for `mnemosyne-memory` |
| `MNEMOBRAIN_GBRAIN_PORT` | `3131` | port the GBrain HTTP service binds |
| `MNEMOBRAIN_GBRAIN_URL` | `http://127.0.0.1:$MNEMOBRAIN_GBRAIN_PORT/health` | health endpoint checked by `doctor`/`status` |
| `MNEMOBRAIN_OLLAMA_URL` | `http://localhost:11434/v1` | OpenAI-compatible embeddings base URL |
| `MNEMOBRAIN_EMBED_MODEL` | `ollama:bge-m3` | embedding model id |
| `MNEMOBRAIN_EMBED_DIMS` | `1024` | embedding dimensionality |
| `MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS` | `168` | Hours until a memory's recency boost halves in SDK/CLI recall (temporal decay) |

Derived exports from `mnemobrain env` (not separately configurable):

| Variable | Value | Meaning |
|---|---|---|
| `MNEMOSYNE_DATA_DIR` | `$MNEMOBRAIN_HOME/data/mnemosyne` | where mnemosyne stores live |

The wiring story: `mnemobrain env` exports `MNEMOSYNE_DATA_DIR` plus the
`MNEMOBRAIN_*` knobs. The launcher (`services/run_gbrain.sh`) isolates
`HOME=$MNEMOBRAIN_HOME` for the gbrain process and maps
`MNEMOBRAIN_OLLAMA_URL` to `OLLAMA_BASE_URL` (the variable gbrain actually
reads), so gbrain's state — including `$HOME/.gbrain/config.json` and its
`brain.pglite` database — lands predictably under the MnemoBrain root.

## gbrain config.json

gbrain reads its embedding model and dimensions from
`$HOME/.gbrain/config.json`. `mnemobrain install` and `mnemobrain init` write
that file (atomically) with the resolved `MNEMOBRAIN_EMBED_MODEL` /
`MNEMOBRAIN_EMBED_DIMS`, using create-if-absent semantics: an existing file is
never overwritten (it may be hand-customized; `doctor` reports if its
`embedding_model` has drifted from the resolved value).

## config file format

Plain `key: value` lines, parsed by a 15-line stdlib parser (no yaml
dependency). Keys are the variable names minus the `MNEMOBRAIN_` prefix, lowercased:

```yaml
# mnemobrain stack defaults. Process env overrides these values.
gbrain_ref: v0.50.0.0
mnemosyne_version: 3.15.1
gbrain_port: 3131
gbrain_url: http://127.0.0.1:3131/health
ollama_url: http://localhost:11434/v1
embed_model: ollama:bge-m3
embed_dims: 1024
```

Notes:

- `MNEMOBRAIN_HOME` itself never comes from the file (chicken-and-egg); env or
  default only.

- `MNEMOBRAIN_GBRAIN_URL` defaults to a value derived from
  `MNEMOBRAIN_GBRAIN_PORT`; set the URL explicitly only if health lives on a
  different path.
- Re-run `mnemobrain init` after changing pins/ports so the file and the
  running stack agree.

## Temporal decay

Mnemosyne applies engine-native recency weighting in recall:
`boost = exp(-hours_delta / halflife)`. MnemoBrain ships a 168h halflife (a
week) — agent memory should outlive a news cycle — while upstream defaults to
24h. Set `MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS` to taste; it governs the SDK and
CLI recall paths. Caveat: if your framework wires Mnemosyne through a hook provider, that
provider may carry its own in-code halflife and
`MNEMOSYNE_TEMPORAL_HALFLIFE_HOURS` will not override that path — check the
provider's source.
