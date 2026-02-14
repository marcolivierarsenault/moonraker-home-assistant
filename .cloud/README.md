# Codex Cloud Agent Runbook

Use this runbook when working in Codex Cloud for `moonraker-home-assistant`.

## Trigger -> Command Matrix

- Fresh environment or dependency updates: `scripts/setup`
- Full local/devcontainer bootstrap (with system packages): `scripts/setup_system`
- Run Home Assistant locally: `scripts/develop`
- Run tests with required 100% coverage gate: `scripts/test_strict`
- Run docs build after docs updates: `scripts/docs_build`
- Run all pre-push checks: `scripts/prepush`
- Version bump request: `scripts/version_bump major|minor|patch` (or `bump2version major|minor|patch`)

## Pre-Push Checklist

1. Run `pre-commit run --all-files`.
2. Run `scripts/test_strict` and confirm coverage is 100%.
3. If `docs/**` changed, run `scripts/docs_build` (this is automatic in `scripts/prepush`).

## Version Bump Rule

- For version bump asks, run `bump2version major|minor|patch`.
- `bump2version` already creates the commit in this repository configuration.
- After the bump completes, push the branch/commit.
