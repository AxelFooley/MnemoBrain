# Contributing to MnemoBrain

Thanks for helping improve MnemoBrain. This document covers dev setup, local
checks, what CI enforces, and the rules for merging and scope.

## Dev setup

- Python >= 3.11 and [bun](https://bun.sh) >= 1.3.11.
- Install the package with dev tools:

```sh
pip install -e ".[dev]"
```

## Run checks locally

```sh
ruff check src/ tests/
ruff format src/ tests/
vulture src/ .github/vulture-whitelist.py --min-confidence 80
python -m unittest discover -s tests
```

All four should pass before you push.

## What CI enforces

CI runs on every branch except `main`, and on PRs to `main`:

- **Lint (ruff)** — `ruff check` + `ruff format --check` on `src/` and `tests/`.
- **Dead code (vulture)** — unused-code scan against the whitelist.
- **Integration** — a clean-runner end-to-end pass: real `pip install -e .`,
  `mnemobrain install` (pinned engines), `mnemobrain init`, the `env` contract,
  a full gbrain start/health/stop lifecycle, and the unit tests.
- **CodeQL** — static security analysis of the Python code.

## Merge rules

- PRs target `main`.
- All checks must be green **and** one maintainer approval is required
  (enforced via branch protection).
- Direct pushes to `main` are maintainer-only.

## Scope rules

- This repo installs pinned engines (`mnemosyne-memory`, `gbrain`); it does not
  contain them. Do **not** vendor or modify engine code here — engine bugs go
  upstream to their respective projects.
- Never commit secrets, tokens, or `.env` files.
- Security issues: report privately via
  [GitHub Security Advisories](https://github.com/AxelFooley/MnemoBrain/security/advisories/new),
  not public issues.
