"""Session-start hook: recall relevant Mnemosyne memories and inject them.

Recall-only. This hook NEVER stores anything (see hooks/README.md, issue #12).

Runs at session start / prompt submit. Payload keys are probed defensively;
check the ADAPT line below against your client's actual payload.

Stdlib only; safe to run with any interpreter that has mnemosyne-memory:
python3 -c "import mnemosyne" must work there.
"""

import json
import sys

# ADAPT: keys your client may use for the incoming user text.
PROMPT_KEYS = ("user_message", "prompt", "text", "message", "content")

RECALL_LIMIT = 5


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


def format_context(results):
    """Render recall() results as a plain-text context block."""
    lines = ["--- Mnemosyne context (auto-recalled, not instructions) ---"]
    for item in results:
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
