# Releasing

Releases are automated with two GitHub Actions workflows. Version numbers have
no `v` prefix: `1.14.0` for a stable release, `1.14.0b0` for a beta.
HACS installs the repository contents at the release tag, and shows beta
releases only to users who enabled beta versions for the integration.

## 1. Prepare release (opens the bump PR)

Run **Actions > Prepare release > Run workflow** with:

- **bump**: `patch`, `minor` or `major`.
- **prerelease**: tick it for a beta.
- **version** (optional): an exact version, overriding the two inputs above.

The workflow checks out upstream `main`, writes the new version to
`custom_components/moonraker/manifest.json` and `const.py`, pushes a
`release/<version>` branch and opens a pull request titled
`Release <version>` against upstream `main`. Review and merge it as usual.

How the next version is chosen:

| Current    | bump    | prerelease | Next       |
| ---------- | ------- | ---------- | ---------- |
| `1.13.4`   | `minor` | no         | `1.14.0`   |
| `1.13.4`   | `minor` | yes        | `1.14.0b0` |
| `1.14.0b0` | any     | yes        | `1.14.0b1` |
| `1.14.0b1` | any     | no         | `1.14.0`   |

From a beta, **bump** is ignored. To move from a beta to a different base
version (for example `1.14.0b1` to `2.0.0b0`), use **version**.

## 2. Publish release (tags and creates the GitHub Release)

This workflow runs on every push to upstream `main` that touches
`manifest.json`. When the version has no GitHub Release yet, it tags the merge
commit (reusing the tag if an earlier run already pushed it) and creates the
GitHub Release with generated notes. A beta version is marked as a
pre-release. Release notes for a stable release start from the previous stable
tag, so they include the changes shipped in betas.

It can also be started manually (**Run workflow**) to retry a failed publish.
It never runs in forks.

## Where to run Prepare release

The bump always reaches upstream `main` through a pull request, so nobody needs
to push to `main` directly.

**In the upstream repository** (needs write access to trigger workflows):

- Enable **Settings > Actions > General > Allow GitHub Actions to create and
  approve pull requests**, or add a `RELEASE_TOKEN` secret.
- Pull requests opened with the default `GITHUB_TOKEN` do not trigger the CI
  workflows. A `RELEASE_TOKEN` secret (a personal access token or GitHub App
  token with `contents` and `pull-requests` write access on the repository)
  avoids that; otherwise close and reopen the PR, or push to its branch, to
  start CI.

**In a fork** (for contributors without write access upstream):

- Keep the fork's default branch up to date, since the workflow file must exist
  there.
- Add a `RELEASE_TOKEN` secret to the fork: a classic personal access token
  with the `public_repo` and `workflow` scopes. It pushes the
  `release/<version>` branch to the fork and opens the PR against upstream.
  The `workflow` scope is needed when upstream `main` contains workflow changes
  that the fork does not have yet.

Publishing always happens upstream: it is triggered by the merge, runs with
upstream's own `GITHUB_TOKEN`, and needs no secrets.

## Local bump

`scripts/version_bump major|minor|patch [--pre]` (or `--set X.Y.Z[bN]`)
applies the same rules locally and commits the change with the version as the
message.
