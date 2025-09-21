# Repository Guidelines

## Project Structure & Module Organization

Core integration code sits in `custom_components/moonraker/`: Home Assistant boots through `__init__.py`, entity platforms like `sensor.py`, `camera.py`, and `switch.py` expose printer features, while `entity.py` and `const.py` hold shared helpers and constants. User strings live in `translations/`, with assets such as screenshots under `assets/`. Update diagrams and docs in `docs/`, and mirror any new feature with tests under `tests/` using the same folder layout. Scripts for local tooling reside in `scripts/`; review them before adding new automation.

## Build, Test, and Development Commands

- `python3 -m pip install -r requirements.txt` — install dev dependencies and HA tooling.
- `scripts/develop` — launch a local Home Assistant instance with this integration (requires `hass` on PATH).
- `scripts/lint` — run Ruff with autofix; prefer `pre-commit run --all-files` before pushing.
- `pytest --durations=10 --cov-report term-missing --cov=custom_components.moonraker tests` or `pytest tests/test_config_flow.py` — execute unit test suites.
- `sphinx-build -b html docs docs/_build/html` — rebuild documentation after content changes.

## Coding Style & Naming Conventions

Target Python 3.13 with four-space indentation. Follow Home Assistant norms: modules and entities in snake_case, user-facing strings sentence case, constants upper snake in `const.py`, and translation keys lower_snake_case. Let Ruff enforce formatting and import sorting (`scripts/lint` or `ruff format`). Keep docstrings concise and update type hints when behaviour shifts.

## Testing Guidelines

Place tests beside their feature under `tests/` and name files `test_<feature>.py`. Reuse fixtures in `tests/conftest.py` for mocked Moonraker clients; assert on Home Assistant states rather than raw dictionaries. Aim to cover new logic and regressions, and record troubleshooting notes in `docs/support/` when behaviour needs guidance. We always want to have 100% coverage for our test. so we need to make sure any new feature reaches 100% completion.

## Commit & Pull Request Guidelines

Write short, imperative commit titles (`Add camera snapshot support`). PRs should explain user impact, list validation like `pytest`, `scripts/lint`, and manual HA runs, and link issues (`Fixes #123`) where relevant. Include updated screenshots or docs links for UI changes, and squash noisy work-in-progress commits before review.

## Security & Configuration Tips

Do not commit printer tokens or sensitive logs; scrub `configuration.yaml` snippets before sharing. Use `.gitignore`d files for local secrets and confirm Home Assistant can authenticate before submitting configuration updates.
