## Description

<!-- What does this PR do? Link the related issue(s) (Fixes #123). -->

## Changes

<!-- Summarize the changes:
- Subsystem(s) touched (routing, knowledge, mcp, plugins, security, ...)
- New/changed behavior
- Configuration or API surface changes (endpoints, env vars, config keys) -->

## Checklist

- [ ] Code is tested — new/affected behavior covered by unit or integration tests (`PYTHONPATH=. pytest tests/ -q`)
- [ ] Test suite passes locally, including per-subsystem coverage floor (>= 95%)
- [ ] Lint passes — `ruff check app/ benchmarks/` and `ruff format --check app/ benchmarks/`
- [ ] Type checks pass — `mypy app/`
- [ ] Documentation updated (README, docs/) where behavior changed
- [ ] Does not break existing features — routing, API endpoints, and config compatibility preserved
- [ ] No security regressions — secrets never logged, config validated (`_reject_unknown`), no new unsandboxed code paths

## Verification

<!-- How did you verify? Commands run, benchmark results, manual curl checks. -->

## Notes for Reviewers

<!-- Anything reviewers should know: migration steps, deploy implications, follow-up work. -->
