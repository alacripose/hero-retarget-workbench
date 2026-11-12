# TICKET-0005 — CI and release archives

**Status:** active.
**Owner:** ala
**Authority:** `logs/authority/2026-11-12-ci-releases.jsonl`
**Opened:** 2026-11-12

## Requirement

The owner asked for continuous integration and for the GitHub releases page to
carry the addon zip:

> can you also make sure ci is working and that the releases page always has the zip releases?

The repository currently has no workflow file, no workflow runs, no tags, and
no releases.

## Contract

1. A GitHub Actions workflow runs on every push to `main` and every pull
   request. It runs the existing tests, builds the addon zip, and uploads the
   zip as a workflow artifact.
2. A version tag matching `v*` runs the same test and build job first, then
   publishes a GitHub release with the built `deadlock_model_forge-<version>.zip`
   attached.
3. The release job fails if the zip version does not match the tag. It creates a
   missing release and replaces the asset on a rerun, so a release is not left
   without the archive.
4. The workflow uses the repository's existing build script and tests. It does
   not add a second packaging format or a second version source.
5. The workflow runs on Windows with Python 3.13 because the addon vendors the
   Windows `cp313` BLAKE3 extension.

## Non-goals

- A package registry, PyPI publication, or a second release carrier.
- Automatically creating a release from every non-tag commit.
- Changing the addon's version or behavior.

## Acceptance

- `.github/workflows/ci.yml` is present and parses as YAML.
- `python -m unittest discover -s tests -v` passes locally.
- `python tools/build_addon.py` produces the expected zip locally.
- A push of the workflow and a `v<version>` tag produce a successful Actions run.
- The GitHub release for that tag has the named zip asset, and the downloaded
  asset hash matches the build.
- `README.md` documents the CI and tag-release path.

## Evidence

- `artifacts/receipts/ci-local.txt`
- `artifacts/receipts/github-actions-run.json`
- `artifacts/receipts/github-release.json`
- `ledger/ledger.jsonl`
