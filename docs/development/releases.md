# Releasing Advance_Moonraker_Control

The GitHub repository is
`thaliamontreux/haos_hacs_moonraker_console`. Its public releases are the version
source for HACS. Do not publish this fork's releases to the upstream repository.

All runtime files must be inside `custom_components/moonraker/`, including panel
JavaScript, HTML and translations. HACS downloads that directory from the release
tag. No separate ZIP asset or host installation script is required.
Development utilities, tests and `TTS_Playback/` are not runtime dependencies.

## Prepare a release

1. Develop on a branch and use a reviewed PR. Preserve the `moonraker` domain,
   entity IDs and storage keys for existing installations.
2. For a release, run `scripts/version_bump` (or
   `scripts/version_bump YYYY.MM.DD` to pick a specific date). Versions are
   calendar dates in `YYYY.MM.DD` form — four-digit year, zero-padded month
   and day. The script validates the date, updates `setup.cfg`, `const.py`
   and `manifest.json` together, and commits the change. The initial renamed
   release is `2026.10.23`. One release per calendar day; corrections ship on
   the next date.
3. Run `python scripts/check_release.py --tag vYYYY.MM.DD`, `scripts/prepush`
   and `scripts/docs_build`. Record actual results. Do not describe a mocked
   test suite as a real printer or HAOS installation test.
4. Merge the reviewed change using the repository's normal workflow.
5. From the reviewed commit in the **new repository**, create and push the
   matching tag, for example `v2026.10.23`. Tagging is the maintainer's release
   action; the release workflow then publishes automatically if validation
   passes.

The release workflow verifies the tag matches all version metadata, checks HACS
and Hassfest, runs Ruff, strict Python/UI tests and the documentation build, and
only then creates the GitHub release. It has a repository guard to avoid
publishing from the original project. HACS uses the release's source tree.
The brand check is excluded for custom-repository distribution, as in the
existing CI; this is not approval for the default HACS catalog.

Add useful release notes describing user impact, migrations, optional
requirements and validation. A new dependency must be declared in the manifest
and explained in the README before users download it. Home Assistant may install
Python dependencies before a config flow opens; a wizard cannot gate that stage.

## Verification and recovery

- Confirm the GitHub release exists and refers to the reviewed commit.
- Confirm HACS offers the release and resolves the declared Home Assistant
  minimum version. Restart only with the operator's permission.
- A live HA/printer installation test requires an explicit maintainer request
  for the exact commit; follow `local-validation.md` for that test.
- Keep backups of configuration and `.storage`. Do not create replacement
  entries just because the product name changed.
- Development installations on `999.0.0` upgrade normally: `2026.MM.DD`
  versions sort higher, so HACS offers the dated release without a manual
  downgrade step.
- Do not rewrite released tags. Corrections publish on the next calendar
  date. Users can select a previous release in HACS or restore a backup.
