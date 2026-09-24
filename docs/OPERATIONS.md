# Operations — scheduled jobs that keep memory healthy

The engines mostly run themselves. Two scheduled jobs keep them healthy
long-term: a nightly agent introspection pass, and a WAL watchdog for the
Mnemosyne database. Cron syntax below; adapt to systemd timers or any
scheduler.

## Job 1 — Nightly introspection (agent job)

**What:** once a day the agent reviews the day's conversations and extracts
durable learnings into Mnemosyne: corrections, decisions, preferences,
workflow discoveries, recurring patterns. It reports a compact summary.

**Why:** the reflex loop captures in the moment; a daily pass catches
cross-session patterns that in-the-moment capture misses.

**Prompt** (hand to your agent scheduler, nightly, e.g. `0 22 * * *`):

```text
Run nightly memory introspection.

1. Gather today's conversations/sessions.
2. Scan for: corrections, decisions, boundary settings, preferences,
   workflow discoveries, architecture insights, recurring patterns.
3. For each finding synthesize: what happened / why it matters / action.
4. Store durable learnings in Mnemosyne (importance 0.7+, scope=global),
   skipping anything matching the "never store" rules of your memory policy.
5. Deliver a compact summary (or nothing if there were no findings).
```

## Job 2 — WAL checkpoint watchdog (silent when healthy)

**Why:** long-lived agent processes hold SQLite read snapshots, which can
starve WAL checkpoints and let `-wal` grow unbounded (hundreds of MB in real
incidents). This job checkpoints the WAL and prints a report ONLY if it is
still bloated after checkpointing — empty output means healthy, so wire your
scheduler to deliver stdout only when non-empty.

**Script** — save as `wal_checkpoint.sh` (uses the env contract from
`mnemobrain env`):

```bash
#!/bin/bash
# Flush the Mnemosyne WAL; print ONLY if still bloated (watchdog pattern).
DB="${MNEMOSYNE_DATA_DIR:?set MNEMOSYNE_DATA_DIR (see: mnemobrain env)}/mnemosyne.db"
python3 - "$DB" <<'EOF'
import os, sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(db, timeout=30)
busy, frames, ckpt = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
con.execute("PRAGMA journal_size_limit=67108864")
con.close()
wal = os.path.getsize(db + "-wal") if os.path.exists(db + "-wal") else 0
size = os.path.getsize(db)
ratio = wal / size if size else 99
if wal > 50 * 1024 * 1024 and ratio > 0.5:
    print(f"mn.wal STILL bloated: wal={wal//1024}KB db={size//1048576}MB "
          f"ratio={ratio:.2f} (busy={busy}, {ckpt}/{frames} frames flushed)")
EOF
```

**Schedule:** run at your system's quietest hour, ideally a few minutes after
a nightly agent restart (a restart releases the read snapshots and lets the
checkpoint flush). Example: `50 2 * * *`.

## Job 3 (optional) — Weekly consolidation

`mnemosyne sleep --all-sessions --dry-run` to preview, then without
`--dry-run` if the report looks right. Example: `0 4 * * 0`.

## After engine upgrades

Run `mnemosyne doctor`; for GBrain, see docs/UPGRADING.md (reindex BEFORE
starting `gbrain serve` — the store is single-writer).

## Windows/WSL: when gbrain looks dead (Cursor MCP)

Upstream issue #6: on Windows, Cursor's MCP client can report `mcp_auth`
errors while the process is fine — or `ERR_CONNECTION_REFUSED` while the CLI
claims the service is running. A pidfile only proves a process exists, not
that its listener is alive. Diagnose state before touching anything:

| What you see | Doctor output | Actual state | Fix |
|---|---|---|---|
| Cursor auth errors only | `gbrain-svc` PASS | process fine, admin token stale (1h default TTL) | mint a fresh token: `gbrain agent register` (30d default) |
| Cursor `ERR_CONNECTION_REFUSED` | `gbrain-svc` FAIL | listener dead | `mnemobrain start gbrain` — now stops a wedged live pid and starts fresh, or fails loudly |
| Doctor PASS everywhere, Cursor dead | all PASS | Cursor-side wiring | check config on the Cursor side; check `<home>/logs/gbrain.log` (no per-line timestamps) and restart |

Decision flow:

1. `GET /health` (127.0.0.1:3131): refused → listener dead, fix the process
   first (`mnemobrain start gbrain`).
2. `POST /mcp` an `initialize` JSON-RPC with `Authorization: Bearer <token>`:
   401 → re-auth (mint a fresh admin token / re-run agent register).
   200 → process is healthy; check Cursor-side MCP config.
3. `mnemobrain doctor` reports the two halves separately: `gbrain-svc`
   (liveness) and `mcp-auth` (token). `mcp-auth` is SKIP when the listener is
   unreachable — liveness is the real problem then.

Known gap, closed as of this change: `mnemobrain start gbrain` no longer
trusts a live pid over a dead listener — it health-gates and returns non-zero
if `/health` is still unreachable 15s after spawn.
