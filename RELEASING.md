# Releasing

Zett is published to PyPI from this repository by
`.github/workflows/release.yml`. Three distributions ship from here, each with
its own tag, so one can move without the other two:

| Distribution | Source | Tag | Depends on |
| --- | --- | --- | --- |
| `agim` | `backend/agim` | `agim-vX.Y.Z` | — |
| `zett-weixin` | `backend/zett-weixin` | `zett-weixin-vX.Y.Z` | `agim` |
| `zettelekasten` | `backend` | `zettelekasten-vX.Y.Z` | `agim`, `zett-weixin`, `zett-agent` |

The command `zettelekasten` installs is `zett`; the distribution name and the
command name are allowed to differ, and `zettelekasten` matches the project.
`zett-agent` comes from its own repository and only its version pin is set here.

## One-time setup

The workflow publishes with `pypa/gh-action-pypi-publish`. Either:

- **Trusted Publishing (no secret).** On PyPI, add a *pending publisher* for
  each of `agim`, `zett-weixin`, and `zettelekasten`: owner `Chang-LeHung`,
  repository `zettelekasten`, workflow `release.yml`, environment `pypi`.
  Publishing then uses the run's OIDC token.
- **An API token.** Create a repository secret named `PYPI_API_TOKEN` under
  **Settings → Secrets and variables → Actions**. It has to be scoped to an
  account (or to all three projects): the `zett-agent` token that already
  exists in the other repository is scoped to `zett-agent` alone, and
  repository secrets do not travel between repositories.

## Cutting a release

1. Set the version in the project you are releasing — `backend/agim/pyproject.toml`,
   `backend/zett-weixin/pyproject.toml`, or `backend/pyproject.toml` — and, if it
   depends on a new version of a package published here, update that pin too.

2. Refresh the lock of every project you touched:

   ```bash
   uv lock --directory backend/agim
   uv lock --directory backend/zett-weixin
   uv lock --directory backend
   ```

3. Commit, then tag and push that one package:

   ```bash
   git tag agim-v0.0.2
   git push origin main
   git push origin agim-v0.0.2
   ```

4. The workflow refuses a tag that disagrees with that project's version,
   builds it (the compiled interface is built only for `zettelekasten`, which
   embeds it), verifies that every exact pin on `agim` and `zett-weixin`
   already exists on PyPI, runs `twine check`, publishes, and opens a GitHub
   release for the tag.

To rehearse without publishing, run `make package`, or start the workflow from
the Actions tab with `workflow_dispatch` — a manual run only builds and uploads
the artifacts.

## Bumping one package

The packages pin each other exactly, and PyPI never accepts the same version
twice, so the rule is:

- **A package on its own.** Bump it and tag it. `agim` can release `0.0.2`
  while `zett-weixin` and `zettelekasten` keep `agim==0.0.1`; they still
  install the `0.0.1` they pin.
- **Making the others use it.** A dependent only follows when its pin changes,
  which means a new version of the dependent as well. Release them in
  dependency order — `agim`, then `zett-weixin`, then `zettelekasten` — because
  the workflow stops a release whose pinned dependency is not on PyPI yet.
