# Release

This directory contains the official release assets for AI Router.

| File | Purpose |
| --- | --- |
| `RELEASE_CHECKLIST.md` | Pre-flight checklist executed before every public release |
| `RELEASE_NOTES_v1.0.0.md` | Draft release notes for the v1.0.0 public release |
| `VERSION_MATRIX.md` | Version references across the repository |
| `KNOWN_LIMITATIONS.md` | Documented, honest limitations of the current release |

## Usage

1. Read `VERSION_MATRIX.md` and confirm all version references agree.
2. Execute `RELEASE_CHECKLIST.md` from top to bottom.
3. Copy the contents of `RELEASE_NOTES_v1.0.0.md` into the GitHub Release body.
4. Record any deviations in the release discussion thread.

Release creation itself requires a maintainer with write access to the
repository and container registry — see the checklist for the manual steps.
