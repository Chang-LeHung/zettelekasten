# Releasing

Zett is published from this repository to PyPI by
`.github/workflows/release.yml`, together with the two packages it depends on:

| Distribution | Source | Depends on |
| --- | --- | --- |
| `agim` | `backend/agim` | — |
| `zett-weixin` | `backend/zett-weixin` | `agim` |
| `zettelekasten` | `backend` | `agim`, `zett-weixin`, `zett-agent` |

The command the last one installs is `zett`; the distribution name and the
command name are allowed to differ, and `zettelekasten` matches the project.

## One-time setup

The workflow publishes with `pypa/gh-action-pypi-publish`. Either:

- **Trusted Publishing (no secret).** On PyPI, add a *pending publisher* for
  each of `agim`, `zett-weixin`, and `zettelekasten`: owner `Chang-LeHung`,
  repository `zettelekasten`, workflow `release.yml`, environment `pypi`.
  Publishing then uses the run's OIDC token.
- **An API token.** Create a repository secret named `PYPI_API_TOKEN` under
  **Settings → Secrets and variables → Actions**. It has to be scoped to an
  account (or to all three projects), because the `zett-agent` token that
  already exists in the other repository is scoped to `zett-agent` alone and
  repository secrets do not travel between repositories.

## Cutting a release

1. Set the same final version in all three projects — `backend/agim/pyproject.toml`,
   `backend/zett-weixin/pyproject.toml`, and `backend/pyproject.toml` — adjust
   the pins between them (`agim==…`, `zett-weixin==…`), and refresh the locks:

   ```bash
   uv lock --directory backend/agim
   uv lock --directory backend/zett-weixin
   uv lock --directory backend
   ```

2. Commit, then tag and push:

   ```bash
   git tag v0.0.1
   git push origin main
   git push origin v0.0.1
   ```

3. The workflow refuses a tag that disagrees with the three versions, builds
   the interface plus the three distributions, runs `twine check` on them,
   publishes `agim`, then `zett-weixin`, then `zettelekasten`, and finally opens
   a GitHub release with generated notes.

To rehearse without publishing, run `make package` and inspect `dist/`, or
start the workflow from the Actions tab with `workflow_dispatch` — a manual run
only builds and uploads the artifacts.

PyPI never accepts the same version twice, and the packages are published in
dependency order, so a failure after `agim` has gone out means the remaining
packages need a new version rather than a retry.

## Before the first release

`zett-weixin` and `zettelekasten` pin `agim` and `zett-weixin` exactly, so the
three have to be released together; `zett-agent` is released from its own
repository and only its version pin changes here.
