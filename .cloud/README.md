# Codex Cloud Agent Runbook

Use this runbook when working in Codex Cloud for `HACS_Moonraker_Advanced` (formerly the moonraker-home-assistant development tree).

## Trigger -> Command Matrix

- Fresh environment or dependency updates: `scripts/setup`
- Full local/devcontainer bootstrap (with system packages): `scripts/setup_system`
- Run Home Assistant locally: `scripts/develop`
- Run tests with required 100% coverage gate: `scripts/test_strict`
- Run docs build after docs updates: `scripts/docs_build`
- Run all pre-push checks: `scripts/prepush`
- Version bump request: `scripts/version_bump [YYYY.MM.DD]` (calendar-date releases)

## Pre-Push Checklist

1. Run `pre-commit run --all-files`.
2. Run `scripts/test_strict` and confirm coverage is 100%.
3. If `docs/**` changed, run `scripts/docs_build` (this is automatic in `scripts/prepush`).

## Version Bump Rule

- For version bump asks, run `scripts/version_bump` (defaults to today's `YYYY.MM.DD`).
- The script validates the date, updates all version files, and creates the commit.
- After the bump completes, push the branch/commit.
