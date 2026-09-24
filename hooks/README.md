# Reference hooks — wiring Mnemosyne without flooding it

Two stdlib-only Python hooks that wire the Mnemosyne reflex loop. Reference
implementations of the capture policy, not magic.

- `mnemosyne_session_start.py` — recall + inject **only**. Reads the incoming
  user text, calls `recall(query, limit=5)`, prints a plain-text context block
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

Concretely, list memories whose source matches your turn-storer
(`mnemosyne-browser` or `mnemosyne list`), then forget each:

```python
from mnemosyne.core.memory import forget
from mnemosyne import recall

for mem in recall("", limit=200):
    if mem.get("source", "").endswith("-turn") or mem.get("source") == "your-turn-storer":
        forget(mem["id"])
```

Run `mnemosyne sleep` consolidation afterwards so recency scores settle
(docs/OPERATIONS.md Job 3).

## Retention

Auto-stored memories are importance `0.5`, scope `session` — consolidation
fodder, not curated facts. Weekly
`mnemosyne sleep --all-sessions` (docs/OPERATIONS.md Job 3) keeps them from
compounding.
