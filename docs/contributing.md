# Contributing

Guidelines for contributing to AI Router.

## Development setup

```bash
git clone https://github.com/salmansaidibrohim267-prog/AI-Router
cd ai-router
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -q
```

## Conventions

- **Tests**: pytest, plain classes (`class TestX:` with `setup_method`),
  one module per subsystem (`tests/test_<subsystem>.py`). Async paths use
  `asyncio_mode = "auto"`.
- **Config classes**: constructor kwargs with `_reject_unknown` (typos raise
  `TypeError`), `from_env()` with a subsystem env prefix (`REL_`, `MIG_`,
  `OBS_`, `DEP_`), and `as_dict()`.
- **DI**: subsystem `create_*` factories accept overrides; heavy side effects
  (HTTP, filesystem, crypto) are injectable and mocked in tests.
- **Subsystem boundaries**: each `app/<subsystem>/` package has its own
  exceptions module deriving from a package base exception.
- **Coverage floor**: 95% per subsystem (CI enforces it). The full suite must
  stay green (`4475 passed, 21 skipped` at time of writing).

## Code style

- Ruff (E/F/W/I/B, line length 120), Black (120), mypy (strict-ish,
  `ignore_missing_imports`), flake8 — config in `pyproject.toml`.
- Run locally: `ruff check app/`, `black --check app/`, `mypy app/`.

## Commits

Conventional Commits (`type(scope): subject`). Types map to changelog
sections: `feat` → Added, `fix` → Fixed, `deprecate` → Deprecated, `remove` →
Removed, `security` → Security, everything else → Changed. `!` marks breaking
changes (rendered under **BREAKING CHANGES**).

## Releases

- Version bumps go through `app.release` (SemVer + RCs).
- The `ReleaseManager` generates `CHANGELOG.md` from commits — keep messages
  conventional.
- Artifact manifests must stay signed; changing a release after
  `finalise()` is rejected by design.

## CI

Push/PR runs: lint (ruff/black/flake8/mypy), tests + coverage, benchmarks on
benchmark-affecting paths, security scans (bandit, pip-audit, Trivy, syft).
Tagged `v*` triggers build/sign and release pipelines.
