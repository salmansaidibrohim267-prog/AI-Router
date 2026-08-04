# Contributing

Thanks for your interest in AI Router. This guide covers the full
contribution workflow: development setup, branch naming, commit
conventions, pull requests, issue reporting and code style.

## Quick links

- [Full contributing guide](docs/contributing.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Issue templates](.github/ISSUE_TEMPLATE/)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)
- [Documentation index](docs/INDEX.md)

---

## Development workflow

1. **Fork** the repository and clone your fork.
2. **Create a feature branch** (see [Branch naming](#branch-naming)).
3. Make changes; keep them focused and small.
4. **Run the checks locally** (see [Code style](#code-style)).
5. **Push** the branch and open a pull request (see
   [Pull request flow](#pull-request-flow)).

```bash
git clone https://github.com/your-user/AI-Router.git
cd AI-Router
git checkout -b fix/my-bug
# … make changes …
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -q        # full suite must stay green
git push -u origin fix/my-bug
```

## Branch naming

Use `<type>/<short-slug>` where `<type>` mirrors the commit convention:

| Type | Use for |
| --- | --- |
| `feat/` | New features (`feat/plugin-marketplace`) |
| `fix/` | Bug fixes (`fix/hsm-unwrap-flake`) |
| `chore/` | Tooling, CI, docs, housekeeping (`chore/ghcr-publishing`) |
| `docs/` | Documentation-only changes |
| `test/` | Test-only changes |
| `refactor/` | Refactors without behavior change |

Branch names are lowercase, hyphen-separated, and descriptive.
`main` is a protected branch — all changes must land via pull request.

## Commit convention

Conventional Commits: `type(scope): subject`.

```
fix(security): deterministic HSM unwrap parsing
ci(release): publish production Docker image to GHCR
feat(routing): add fallback preference hint
```

- **Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`,
  `ci`, `security`, `perf`, `deprecate`, `remove`.
- Types map to changelog sections (see `docs/contributing.md`); `!` marks
  breaking changes.
- `ReleaseManager` generates `CHANGELOG.md` from commit messages — keep
  every message conventional and imperative.
- One logical change per commit; use `fixup!` commits and rebase before
  merging.

## Pull request flow

1. Push a branch, then open a PR against **`main`**.
2. **PR title** follows the commit convention (same rules).
3. Fill the PR description: what, why, how to test, screenshots if relevant.
4. CI runs on every PR: lint, tests + coverage (95% floor), security
   scans (bandit, pip-audit, Trivy, syft), benchmarks on affected paths.
5. All checks must pass before merge. Maintainers may request changes;
   address them in follow-up commits and squash on merge.
6. After merge, a maintainer may trigger the release pipeline
   (`workflow_dispatch`) to cut a new version.

## Issue reporting

Use the issue templates in `.github/ISSUE_TEMPLATE/`:

- **Bug reports** — include: AI Router version, environment (OS/Docker/K8s),
  provider(s) involved, steps to reproduce, expected vs actual behavior,
  logs (secrets masked).
- **Feature requests** — describe the problem, the proposed behavior, and
  any workarounds.
- **Questions** — best asked in Discussions or via the question template.

For security vulnerabilities, **do not open a public issue** — follow
[SECURITY.md](SECURITY.md).

## Code style

| Tool | Command | Notes |
| --- | --- | --- |
| Ruff | `ruff check app/` | E/F/W/I/B, line length 120 |
| Black | `black --check app/` | Formatting, 120 |
| mypy | `mypy app/` | Strict-ish, `ignore_missing_imports` |
| flake8 | `flake8 app/` | Config in `pyproject.toml` / `.flake8` |

Test conventions (see `docs/contributing.md`): pytest classes, one module
per subsystem, `asyncio_mode = "auto"`, injectable side effects, per
subsystem 95% coverage floor.

Documentation changes: update `docs/INDEX.md` and the README section index
when adding pages; keep internal links relative.

## Code of Conduct

All contributions are subject to the [Code of Conduct](CODE_OF_CONDUCT.md).
Be respectful, constructive and inclusive.
