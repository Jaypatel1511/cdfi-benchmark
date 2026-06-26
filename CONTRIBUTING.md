# Contributing & Release Runbook — cdfi-benchmark

This document covers how releases are cut and published. The short version:
**releases are built, audited, tagged, and published ONLY by CI from an annotated
git tag. Never run `twine`/`python -m build` + upload from a laptop.**

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

- Matrix Python **3.9 / 3.10 / 3.11 / 3.12** (matches `requires-python = ">=3.9"`).
- `pip install -e . pytest build`, then `pytest --import-mode=importlib`.
- The suite is fully mocked — no live FDIC calls hit `banks.data.fdic.gov`.

CI has **no publish step and no `id-token` permission**. It only reads the repo.

## Release pipeline

`.github/workflows/release.yml` runs **only on a pushed tag matching `v*`**, with
four jobs gated in order:

1. **verify-version** — parses `pyproject.toml` with `tomllib` (never sed/grep) and
   fails if the tag (minus leading `v`) does not equal `project.version`.
2. **build** — `python -m build` produces the wheel + sdist, uploaded as the `dist`
   artifact (the single source of truth for the rest of the pipeline).
3. **test-wheel** — matrix 3.9–3.12: installs the **wheel** (not `-e`, not the source
   tree) into a fresh venv and runs the suite against the installed artifact. The
   wheel — not source — is what gets tested.
4. **publish** — needs all three gates; `environment: pypi`; the **only** job with
   `id-token: write`; publishes via `pypa/gh-action-pypi-publish` using the PyPI
   **Trusted Publisher (OIDC)** handshake. No API token is stored anywhere.

## The release sequence

> build → audit → fix → tag → CI-publish → smoke → settle

1. **build** the candidate locally to confirm it builds (`python -m build`), but do
   not upload from local — local builds are for inspection only.
2. **audit** the diff: correctness fix in its own branch/cycle, infra in its own
   (don't mix a dangerous-bug fix and pipeline changes in one branch — it muddies
   both audits).
3. **fix** anything the audit surfaces; re-run CI green on `main`.
4. **tag**: bump `project.version` in `pyproject.toml`, merge to `main`, then create
   an **annotated** tag on that commit:
   `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`.
5. **CI-publish**: the tag push triggers `release.yml`. Publishing happens there and
   only there. Never `twine upload` locally.
6. **smoke**: after publish, `pip install cdfi-benchmark==X.Y.Z` into a clean venv
   and import / run a trivial check.
7. **settle**: confirm PyPI shows the new version and the drift guard (below) holds.

## Action pinning (supply-chain)

Every `uses:` in both workflows is pinned to a **full 40-character commit SHA** with
the human-readable version in a trailing comment. No floating tags (`@v4`, `@main`).
Any workflow that can request `id-token: write` is a supply-chain surface — pin
**every** action in it, not just the publish action. When bumping a version, resolve
the new commit SHA (`git ls-remote <repo> refs/tags/<tag>`; for annotated tags use
the peeled `^{}` commit) and update the trailing comment.

## Drift guard (three checks)

Before and after any release, these three must all hold:

1. **PyPI latest == `pyproject@HEAD`** — the published version matches `main`.
2. **Every PyPI release has a git tag** — nothing was published off-tag/locally.
3. **`pyproject@tag` == tag name** — the version committed at each tag equals that
   tag (this is exactly what `verify-version` enforces in CI).

## One-time setup before the first tag push

The PyPI Trusted Publisher and the GitHub environment must exist **before** the
first tag is pushed, or the publish job fails at the OIDC handshake:

- On PyPI: cdfi-benchmark → Manage → Publishing → add a publisher with owner
  `Jaypatel1511`, repo `cdfi-benchmark`, workflow `release.yml`, environment `pypi`.
- On GitHub: create the `pypi` environment in repo settings.
