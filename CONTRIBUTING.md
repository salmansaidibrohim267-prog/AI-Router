# Contributing

Thanks for your interest in AI Router. Please read `docs/contributing.md`,
which contains the full contributor guide: development setup, code style
(ruff + mypy + black), the test suite and coverage requirements, benchmark
runs, and how to submit a pull request.

## Quick links

- [Full contributing guide](docs/contributing.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Issue templates](.github/ISSUE_TEMPLATE/)
- [Changelog](CHANGELOG.md)
- [Security policy](SECURITY.md)

## The short version

1. Fork the repository and create a branch from `main`.
2. Follow the project's conventions (mimic surrounding code, no new
   dependencies without discussion).
3. Run the checks: `ruff check .`, `black --check .`, `mypy app/`.
4. Add tests for anything you change; the CI gate enforces a per-subsystem
   coverage floor of **95%**.
5. Open a pull request using the provided template.
