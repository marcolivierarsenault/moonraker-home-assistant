# Repository Guidelines

## Project Structure & Module Organization

Core integration code sits in `custom_components/moonraker/`: Home Assistant boots through `__init__.py`, entity platforms like `sensor.py`, `camera.py`, and `switch.py` expose printer features, while `entity.py` and `const.py` hold shared helpers and constants. User strings live in `translations/`, with assets such as screenshots under `assets/`. Update diagrams and docs in `docs/`, and mirror any new feature with tests under `tests/` using the same folder layout. Scripts for local tooling reside in `scripts/`; review them before adding new automation.

## Build, Test, and Development Commands

- `scripts/setup` — install Python dependencies; rerun whenever dependencies change.
- `scripts/setup_system` — install full local/devcontainer system dependencies (includes `go2rtc`, apt packages, and `scripts/setup`).
- `scripts/develop` — launch a local Home Assistant instance with this integration (requires `hass` on PATH).
- `scripts/test_strict` — run the full test suite with strict 100% coverage enforcement.
- `scripts/docs_build` — rebuild docs with warnings treated as errors.
- `pre-commit run --all-files` — run formatting and quality hooks before pushing.
- `scripts/prepush` — run pre-push checks (`pre-commit`, strict tests, and docs build when `docs/**` changed).
- `scripts/version_bump major|minor|patch` — perform release version bumps through `bump2version`.

## Coding Style & Naming Conventions

Target Python 3.13 with four-space indentation. Follow Home Assistant norms: modules and entities in snake_case, user-facing strings sentence case, constants upper snake in `const.py`, and translation keys lower_snake_case. Let Ruff enforce formatting and import sorting (`scripts/lint` or `ruff format`). Keep docstrings concise and update type hints when behaviour shifts.

## Testing Guidelines

Place tests beside their feature under `tests/` and name files `test_<feature>.py`. Reuse fixtures in `tests/conftest.py` for mocked Moonraker clients; assert on Home Assistant states rather than raw dictionaries. Aim to cover new logic and regressions, and record troubleshooting notes in `docs/support/` when behaviour needs guidance. Run `scripts/test_strict` before pushing; new work must keep coverage at 100%.

## Commit & Pull Request Guidelines

Write short, imperative commit titles (`Add camera snapshot support`). Before pushing, run `scripts/prepush` (or at minimum `pre-commit run --all-files` and `scripts/test_strict`, plus `scripts/docs_build` for docs changes). PRs should explain user impact, list validation commands run, and link issues (`Fixes #123`) where relevant. Include updated screenshots or docs links for UI changes, and squash noisy work-in-progress commits before review. For version bumps, use `bump2version major|minor|patch` (or `scripts/version_bump ...`), which handles the commit automatically.

## Security & Configuration Tips

Do not commit printer tokens or sensitive logs; scrub `configuration.yaml` snippets before sharing. Use `.gitignore`d files for local secrets and confirm Home Assistant can authenticate before submitting configuration updates.
