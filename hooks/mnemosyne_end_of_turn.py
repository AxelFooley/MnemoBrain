"""End-of-turn hook: selective capture of user-side durable content.

DEFAULT POLICY: assistant replies are NEVER stored — they are self-reinforcing
recall poison (issue #12: storing raw turns flooded working memory until
chatter scored above curated facts). Only user-side text that passes a
durable-content filter is stored.

Escape hatch: MNEMOSYNE_STORE_TURNS=1 restores store-the-turn behavior
(source suffix "-turn"). Discouraged.

Runs at turn end. Payload keys are probed defensively; check the ADAPT line
below against your client's actual payload.

Stdlib only; safe to run with any interpreter that has mnemosyne-memory:
python3 -c "import mnemosyne" must work there.
"""

import json
import os
import sys

# ADAPT: keys your client may use for the turn's user text.
USER_KEYS = ("user_message", "prompt", "text", "message", "content")
# ADAPT: keys for the assistant reply (policy: never stored).
ASSISTANT_KEYS = ("last_assistant_message", "assistant_message")

CHATTER_CUES = (
    "will finish",
    "still running",
    "the job",
    "here is the list",
    "you can close",
    "progress:",
    "attempt ",
    "retried",
    "pinging",
    "waiting for",
)

DURABLE_CUES = (
    "prefer",
    "always",
    "never",
    "instead of",
    "decided",
    "decision",
    "correct",
    "wrong",
    "it's actually",
    "remember that",
    "my name",
    "i am",
    "we use",
    "don't use",
)

MIN_LENGTH = 40
SUBSTANTIVE_LENGTH = 200

TERMINALS = (".", "?", "!")


def read_payload(argv):
    """Return (user_text, assistant_text): stdin JSON, else argv, else ("","")."""
    data = None
    try:
        if not sys.stdin.isatty():
            data = json.load(sys.stdin)
    except Exception:  # noqa: BLE001 - broken hook must never break the turn
        data = None
    if isinstance(data, dict):
        user = next(
            (
                data.get(k)
                for k in USER_KEYS
                if isinstance(data.get(k), str) and data.get(k).strip()
            ),
            None,
        )
        assistant = next(
            (
                data.get(k)
                for k in ASSISTANT_KEYS
                if isinstance(data.get(k), str) and data.get(k).strip()
            ),
            None,
        )
        return (user or ""), (assistant or "")
    if len(argv) > 1:
        text = " ".join(argv[1:])
        if not text.startswith("-"):
            return text, ""
    return "", ""


def qualifies(text):
    """True only for clearly durable user-side content; drop the rest.

    False negatives are cheap; false positives poisoned the memory bank
    (issue #12).
    """
    if not text or len(text) < MIN_LENGTH:
        return False
    lowered = text.lower()
    if any(cue in lowered for cue in CHATTER_CUES):
        return False
    if any(cue in lowered for cue in DURABLE_CUES):
        return True
    return len(text) >= SUBSTANTIVE_LENGTH and text.rstrip().endswith(TERMINALS)


def decide(user_text, assistant_text):
    """Return the text to store, or None to store nothing.

    Assistant-only turns always come back None (default policy).
    MNEMOSYNE_STORE_TURNS=1 overrides to store the raw assistant reply.
    """
    if environ_is_turn_storage_enabled():
        return assistant_text or user_text or None
    if user_text and qualifies(user_text):
        return user_text
    return None


def environ_is_turn_storage_enabled():
    """True when MNEMOSYNE_STORE_TURNS=1 (escape hatch; discouraged)."""
    return os.environ.get("MNEMOSYNE_STORE_TURNS") == "1"


def get_remember():
    """Late import so the module imports without mnemosyne installed."""
    from mnemosyne import remember

    return remember


def store(text, source, turn=False):
    """remember() with conservative defaults; returns memory id or None."""
    if turn:
        source = f"{source}-turn"
    return get_remember()(
        text,
        source=source,
        importance=0.5,
        scope="session",
        metadata={"auto": True, "via": "mnemobrain-hook"},
    )


def main(argv):
    """Store qualifying user text; assistant replies never stored.

    Any exception exits 0 silently — a broken memory hook must never break
    the agent's turn.
    """
    try:
        user_text, assistant_text = read_payload(argv)
        flags = [a for a in argv[1:] if a.startswith("-")]
        positional = [a for a in argv[1:] if not a.startswith("-")]
        source = positional[0] if positional else "agent-hook"
        dry_run = "--dry-run" in flags

        text = decide(user_text, assistant_text)
        if text is None:
            if dry_run and (user_text or assistant_text):
                print("skip")
            return
        turn = environ_is_turn_storage_enabled() and bool(assistant_text)
        stored_source = source + ("-turn" if turn else "")
        if dry_run:
            print(f"[dry-run] would store: {text!r} importance=0.5 source={stored_source}")
            return
        store(text, source, turn=turn)
    except Exception:  # noqa: BLE001 - broken hook must never break the turn
        return


if __name__ == "__main__":
    main(sys.argv)
