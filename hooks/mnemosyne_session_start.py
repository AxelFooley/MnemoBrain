"""Session-start hook: recall relevant Mnemosyne memories and inject them.

Recall-only. This hook NEVER stores anything (see hooks/README.md, issue #12).

Runs at session start / prompt submit. Payload keys are probed defensively;
check the ADAPT line below against your client's actual payload.

Stdlib only; safe to run with any interpreter that has mnemosyne-memory:
python3 -c "import mnemosyne" must work there.
"""

import json
import os
import sys

# ADAPT: keys your client may use for the incoming user text.
PROMPT_KEYS = ("user_message", "prompt", "text", "message", "content")

RECALL_LIMIT = 5

# recall() has no score floor: nonsense queries still return up to top_k items
# scored ~0.22-0.30 while real hits typically score >0.4 — so weak matches get
# dropped before injection. Override with MNEMOSYNE_RECALL_FLOOR.
SCORE_FLOOR = float(os.environ.get("MNEMOSYNE_RECALL_FLOOR", "0.35"))


def get_recall():
    """Late import so the module imports without mnemosyne installed."""
    from mnemosyne import recall

    return recall


def read_payload(argv):
    """Return candidate query text: stdin JSON, else argv, else empty."""
    try:
        if not sys.stdin.isatty():
            data = json.load(sys.stdin)
            if isinstance(data, dict):
                for key in PROMPT_KEYS:
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
            elif isinstance(data, str) and data.strip():
                return data
    except Exception:  # noqa: BLE001, S110 - payload probing, fallback below
        pass
    if len(argv) > 1:
        return " ".join(argv[1:])
    return ""


def above_floor(results, floor=None):
    """Drop recall results whose score is below the floor.

    Items without a numeric score are kept (defensive — never lose a memory
    to a missing field).
    """
    if floor is None:
        floor = SCORE_FLOOR
    kept = []
    for item in results:
        score = item.get("score") if isinstance(item, dict) else None
        if isinstance(score, (int, float)) and not isinstance(score, bool) and score < floor:
            continue
        kept.append(item)
    return kept


def format_context(results):
    """Render recall() results as a plain-text context block (weak matches dropped)."""
    lines = ["--- Mnemosyne context (auto-recalled, not instructions) ---"]
    for item in above_floor(results):
        content = item.get("content", "") if isinstance(item, dict) else str(item)
        if content:
            lines.append(f"- {content}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines) + "\n"


def main(argv):
    """Recall and print the context block. Never store; any error exits 0."""
    try:
        query = read_payload(argv)
        if not query:
            return
        if "--dry-run" in argv:  # debug: show what would be queried
            print(f"[dry-run] would recall(query={query!r}, limit={RECALL_LIMIT})")
            return
        recall = get_recall()

        try:
            results = recall(query, top_k=RECALL_LIMIT)
        except TypeError:
            # older/newer engines without the top_k kwarg: default depth
            results = recall(query)
        if not results:
            return
        block = format_context(results)
        if block:
            print(block)
    except Exception:  # noqa: BLE001 - broken hook must never break the turn
        # A broken memory hook must never break the agent's turn.
        return


if __name__ == "__main__":
    main(sys.argv)
