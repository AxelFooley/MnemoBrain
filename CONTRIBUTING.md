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

CI runs on the `dev` branch and on PRs targeting `dev` — that is where all
quality gates live. PRs from `dev` to `main` run no gates: everything has
already passed, and a `main` merge is by definition a release.

- **Lint (ruff)** — `ruff check` + `ruff format --check` on `src/` and `tests/`.
- **Dead code (vulture)** — unused-code scan against the whitelist.
- **Integration** — a clean-runner end-to-end pass: real `pip install -e .`,
  `mnemobrain install` (pinned engines), `mnemobrain init`, the `env` contract,
  a full gbrain start/health/stop lifecycle, and the unit tests.
- **CodeQL** — static security analysis of the Python code.

## Merge rules

- Feature work happens on feature branches; PRs target `dev`.
- All checks must be green on the `dev` PR (branch protection enforces this).
- After merge, `dev` soaks: maintainers validate the fix internally on their
  own stacks first; only then is the reporter invited to test from `dev`.
  There is no rush — a day or two before answering the reporter is fine.
  Soak time scales with risk (docs: hours; service lifecycle or engine pins:
  1–2 days).
- Only then does `dev` merge into `main` via PR — a `main` merge always
  produces a tagged release with published notes.
- Only maintainers merge into `dev` and `main` (branch protection on both).

## Scope rules

- This repo installs pinned engines (`mnemosyne-memory`, `gbrain`); it does not
  contain them. Do **not** vendor or modify engine code here — engine bugs go
  upstream to their respective projects.
- Never commit secrets, tokens, or `.env` files.
- Security issues: report privately via
  [GitHub Security Advisories](https://github.com/AxelFooley/MnemoBrain/security/advisories/new),
  not public issues.
