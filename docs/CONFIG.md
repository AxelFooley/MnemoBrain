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

Derived exports from `mnemobrain env` (not separately configurable):

| Variable | Value | Meaning |
|---|---|---|
| `GBRAIN_HOME` | `$MNEMOBRAIN_HOME/data/gbrain` | where gbrain pages live |
| `MNEMOSYNE_HOME` | `$MNEMOBRAIN_HOME/data/mnemosyne` | where mnemosyne stores live |

The launcher (`services/run_gbrain.sh`) fixes `HOME=$MNEMOBRAIN_HOME` for the
gbrain process, so its dotfile config also lands under the MnemoBrain root.

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
