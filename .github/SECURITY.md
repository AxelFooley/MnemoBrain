# Security Policy

## Reporting a vulnerability

Please report security issues privately via [GitHub Security Advisories](https://github.com/Axelfooley/MnemoBrain/security/advisories/new) rather than opening a public issue.

## Prompt-injection defenses (layered)

MnemoBrain powers an AI agent's memory, so text in this repository is an attack surface:
an external contributor could plant instructions aimed at AI agents (Claude Code, Codex,
Cursor, etc.) in docs or comments. We defend in two layers:

- **Layer 1 — deterministic (required, merge-blocking).** `scripts/check_prompt_injection.py`
  runs on every PR and every push to dev/main over all files. Catches hidden Unicode/BIDI,
  homoglyphs, LLM delimiter tokens, known injection phrasings, and base64 blobs. Auditable,
  stdlib-only, self-tested (`--self-test`). Runs as required check "Prompt injection (all files)".
- **Layer 2 — semantic (advisory, non-blocking).** `promptfoo/code-scan-action` (pinned by
  commit SHA, provenance-attested) runs on PRs to dev/main. An AI scanner reads the diff for
  paraphrased/indirect agent-directed instructions that deterministic rules miss. It posts
  PR review comments + Code Scanning alerts. NOT a required check; cannot block merges.
  Findings are reviewed by maintainers; false positives are expected while we calibrate.
