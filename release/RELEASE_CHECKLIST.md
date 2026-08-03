# Release Checklist — v1.0.0

Pre-flight checklist for the public v1.0.0 release. Work through each item
top to bottom before announcing the release.

## Pre-flight (repository, automatable — already validated)

- [ ] Branch is clean: `git status` shows only intended changes
- [ ] Full test suite green: `PYTHONPATH=. pytest tests/ -q`
- [ ] Coverage floor enforced in CI (per-subsystem >= 95%)
- [ ] Lint (ruff, black, flake8, mypy) passes in CI
- [ ] Bandit security scan passes in CI
- [ ] README version badges match the release version
- [ ] CHANGELOG contains a `[1.0.0]` section with accurate content
- [ ] `docs/INDEX.md` links every documentation page
- [ ] Release notes drafted in `release/RELEASE_NOTES_v1.0.0.md`
- [ ] `release/VERSION_MATRIX.md` matches the current repository state
- [ ] No placeholder ownership references remain (previous placeholder owner fully removed)
- [ ] Examples run from a clean checkout
- [ ] Internal and relative links verified

## Publishing (manual — requires GitHub owner access)

- [ ] Push the release commit and tag `v1.0.0`
- [ ] Verify the build-and-sign workflow produces the image
  `ghcr.io/salmansaidibrohim267-prog/AI-Router:v1.0.0`
- [ ] Confirm SBOM attestation and cosign signature are attached
- [ ] Create the GitHub Release using `release/RELEASE_NOTES_v1.0.0.md`
- [ ] Attach `dist/release/` artifacts (signed manifest, checksums) to the release
- [ ] Verify the release link resolves: `/releases/tag/v1.0.0`

## Post-release

- [ ] Deploy the demo instance from `demo/`
- [ ] Verify a fresh `docker pull` of the published image
- [ ] Re-import Grafana dashboards from provisioning
- [ ] Announce on channels per the manual checklist (`release/README.md`)

## Rollback

If the release is broken, tag `v1.0.1` or roll back the image tag
(document the decision in the release thread).
