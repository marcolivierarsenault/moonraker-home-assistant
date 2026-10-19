# Local Home Assistant and printer validation

This is the durable context for an agent asked to validate a pull request with
a local Home Assistant instance and a real Moonraker printer. Keep it current
as the local environment changes. Never infer missing credentials, paths, or
printer details.

Local validation is separate from Codex Cloud. Do not perform it unless a
maintainer explicitly requests it for a specific pull request or commit.

## Safety boundary

- Work from the exact PR head SHA in an isolated Git worktree.
- Confirm the printer is idle before connecting.
- Validation is passive: load the integration, connect, subscribe, poll, and
  observe logs.
- Do not activate button, switch, light, or number entities.
- Do not send G-code or invoke restart, update, power, emergency-stop, pause,
  resume, or cancel operations.
- Do not edit the printer's Moonraker or Klipper configuration.
- Never publish raw logs. Remove tokens, API keys, URLs, IP addresses, serial
  numbers, and unrelated household information first.
- Stop if the requested validation would cross these boundaries.

## Prepare the exact pull request head

From a clean primary checkout:

```bash
git fetch origin pull/PR_NUMBER/head:refs/remotes/origin/pr/PR_NUMBER
validation_root=$(mktemp -d)
validation_worktree="$validation_root/pr-PR_NUMBER"
git worktree add --detach "$validation_worktree" refs/remotes/origin/pr/PR_NUMBER
cd "$validation_worktree"
git rev-parse HEAD
```

Compare the printed SHA with the current GitHub PR head SHA before testing.
Never test a moving branch name and describe it as the current PR head.

## Python and deterministic checks

This project targets Python 3.14:

```bash
python3.14 -m venv .venv
PATH="$PWD/.venv/bin:$PATH" scripts/setup
PATH="$PWD/.venv/bin:$PATH" pre-commit run --all-files
PATH="$PWD/.venv/bin:$PATH" scripts/test_strict
```

Run `PATH="$PWD/.venv/bin:$PATH" scripts/docs_build` when documentation changed.
After format or lint hooks, inspect `git status --short` and `git diff`. A
validator must not silently modify the PR and still report the original SHA as
tested.

## Local Home Assistant configuration

The runtime harness needs a private, ignored Home Assistant configuration with
an existing Moonraker config entry. Do not commit or copy its credentials into
the worktree, logs, issue, or PR.

Use scoped logging:

```yaml
logger:
  default: info
  logs:
    custom_components.moonraker: debug
    moonraker_api: debug
```

Before this procedure can be considered fully reproducible, maintainers must
record the following local-only values in a private operator note:

- the safe Home Assistant configuration directory or preparation command;
- how the PR worktree's integration is exposed to that configuration;
- how to confirm the intended test printer is idle;
- known benign warnings in the local Home Assistant environment;
- whether FFmpeg or go2rtc is required for the changed code path.

An agent must stop and ask for this information when it is not available.

## Run and observe

With the private runtime configuration prepared, launch Home Assistant while
preserving continuous output:

```bash
log_file="/tmp/moonraker-ha-pr-PR_NUMBER.log"
PATH="$PWD/.venv/bin:$PATH" scripts/develop 2>&1 | tee "$log_file"
```

Keep the terminal output visible. In a second terminal, confirm Home Assistant
answers on the configured port, then observe the integration for 5–10 minutes.
The exact success evidence is:

1. Home Assistant starts and answers HTTP requests.
2. The Moonraker config entry finishes setup.
3. The client connects to the expected printer.
4. Multiple coordinator refreshes or subscription updates complete.
5. The changed behaviour is exercised passively when possible.
6. No new `WARNING`, `ERROR`, or `CRITICAL` record is emitted by
   `custom_components.moonraker` or `moonraker_api`.

Separate unrelated Home Assistant, certificate, FFmpeg, camera, and optional
dependency warnings from integration defects, but report them explicitly.

## Pull request report

Add a comment or update the PR body with:

```text
Local validation
- Commit SHA:
- Date and duration:
- Python / Home Assistant version:
- Printer state before and after:
- Deterministic checks:
- Integration loaded:
- Moonraker connected:
- Successful refreshes observed:
- Moonraker-scoped warnings or errors:
- Changed behaviour exercised:
- Unrelated environment warnings:
- Not tested / remaining risk:
```

Do not write “tested locally” without this evidence. If validation fails,
include the first relevant sanitized error and distinguish a code failure from
an unavailable or misconfigured local environment.
