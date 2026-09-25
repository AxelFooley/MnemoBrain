# Reference hooks — wiring Mnemosyne without flooding it

Two stdlib-only Python hooks that wire the Mnemosyne reflex loop. Reference
implementations of the capture policy, not magic.

- `mnemosyne_session_start.py` — recall + inject **only**. Reads the incoming
  user text, calls `recall(query, top_k=5)`, prints a plain-text context block
  to stdout. Stores nothing, ever.
- `mnemosyne_end_of_turn.py` — selective capture. Stores the user's message
  **only if** it looks durable (>= 40 chars, matches durable cues like
  "prefer"/"decided"/"don't use", or is a >= 200-char complete statement, and
  matches no chatter cue). Chatter/status lines ("will finish", "the job",
  "here is the list", …) are dropped so short-lived noise can't harden into
  memories.

## Why assistant replies are never stored

Raw turns are self-reinforcing recall poison (mnemosyne-oss issue #12): a 14
memories-in-35-minutes flood of session chatter scored ~0.55 in `recall()` —
above curated facts (0.25–0.47) — so even after escape, recency-weighted
recall kept re-injecting chatter learned from stored replies. Hence the hard
default here: neither hook stores the assistant reply.
`MNEMOSYNE_STORE_TURNS=1` restores store-the-turn behavior (source suffix
`-turn`) — discouraged, documented, your foot.

## Divergence from upstream (deliberate)

Upstream's autosave (`sync_turn`) stores **all user turns** unfiltered — its
default (`sync_roles=["user"]`) exists to keep assistant transcript noise out,
not to judge user content; consolidation is left to sort signal from noise.
These hooks keep that assistant exclusion and add one more layer: user text
must also pass the durable-content filter above. That filter is MnemoBrain's
design choice (#12 showed why we prefer not to store the noise at all), not a
correction of upstream. If you prefer upstream's simpler policy, wire
`sync_turn` directly instead of these hooks.

## Wiring

| Hook event | Your client | Script |
|---|---|---|
| Claude Code `Stop` (stdin JSON) | Claude Code | `hooks/mnemosyne_end_of_turn.py` |
| Cursor `afterAgentResponse` | Cursor | `hooks/mnemosyne_end_of_turn.py` |
| Claude Code `UserPromptSubmit` (stdin JSON) | Claude Code | `hooks/mnemosyne_session_start.py` |
| Cursor `beforeChat` | Cursor | `hooks/mnemosyne_session_start.py` |

Payload keys are probed defensively; check the two marked ADAPT lines in each
script against your client's actual payload. Run with any interpreter that has
mnemosyne-memory installed — the same one where
`python3 -c "import mnemosyne"` works.

## Cleaning an already-flooded bank

`recall()` is query-driven and can't enumerate a bank, and `get_all_memories()`
is scoped to the calling session — for a sweep you want direct SQL over the
store, then the module-level `forget()`:

```python
import sqlite3
from mnemosyne.core.memory import forget

DB = "<MNEMOSYNE_DATA_DIR>/mnemosyne.db"  # print via: mnemobrain env
con = sqlite3.connect(DB)
ids = con.execute(
    "SELECT id FROM working_memory WHERE source LIKE '%-turn' OR source = 'your-turn-storer'"
).fetchall()
for (mem_id,) in ids:
    forget(mem_id)
```

If consolidation already ran, sweep `episodic_memory` the same way. Then run
`mnemosyne sleep` so recency scores settle (docs/OPERATIONS.md Job 3).

## Retention

Auto-stored memories are importance `0.5`, scope `session` — consolidation
fodder, not curated facts. Weekly
`mnemosyne sleep --all-sessions` (docs/OPERATIONS.md Job 3) keeps them from
compounding.
