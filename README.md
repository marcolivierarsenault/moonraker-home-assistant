# Advance_Moonraker_Control

[![HACS custom integration](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://www.hacs.xyz/)
[![GitHub release](https://img.shields.io/github/v/release/thaliamontreux/HACS_Moonraker_Advanced)](https://github.com/thaliamontreux/HACS_Moonraker_Advanced/releases)

A Home Assistant integration and authenticated printer control panel for
Klipper printers running Moonraker. Install and update it through HACS from
[this repository](https://github.com/thaliamontreux/HACS_Moonraker_Advanced).
It is an independent project, not an official Klipper or Home Assistant product.

## Features

- **Live dashboard:** status, progress, temperatures, motion, layers, filament,
  thumbnails and webcams, with WebSocket updates and polling fallback.
  Multiple printers can be configured.
- **Controls:** start, pause, resume, cancel, emergency stop, movement, heaters,
  fans, lights, speed/flow, macros and G-code console. Available controls depend
  on the printer configuration and Moonraker permissions.
- **Files and queues:** browse/select G-code, browser uploads, queue management,
  metadata and interactive toolpath preview.
- **Analysis:** bed-mesh visualization and baseline comparison, heater and
  extrusion monitoring, print history, energy/cost estimates and repair alerts.
- **Printcast:** printability forecasts, contributing factors, recommendations,
  spool moisture estimates and extrusion trends. Missing measurements limit
  forecasts; they do not guarantee a successful or safe print.
- **Optional services:** Spoolman inventory through Moonraker, Home Assistant
  power/temperature/humidity sensors, notifications and AI camera checks.
  Automatic power-off is enabled only when you select a power switch.
- **Automation:** sensor, binary sensor, camera, button, switch, number, light,
  select, update and event entities; printer services and Assist intents.
  Voice phrases, TTS and announcement automations require separate setup.
- **Panel:** Home Assistant authentication, administrator controls and an
  optional operator role for live adjustments. All panel assets are included;
  no separate dashboard card or frontend download is needed.

## Installation

### Review requirements before downloading

| Requirement | How it is provided |
| --- | --- |
| Home Assistant 2026.9.0 or newer | Install/update Home Assistant first; HAOS is recommended. |
| HACS 2.0 or newer and GitHub access | [Install HACS](https://www.hacs.xyz/docs/use/download/download/), then add this repository as an Integration. |
| Working Klipper/Moonraker printer | Set up the printer separately. Home Assistant must reach its host and API port, normally 7125. |
| Host, port, TLS choice and optional API key | The wizard asks for them. Obtain them from your printer administrator. |
| Writable Home Assistant configuration storage | Home Assistant manages entries and data here. Include it in backups. |
| Python client | Home Assistant installs `moonraker-api==2.0.6` from the manifest. Package-index access is needed when not cached. |
| Built-in panel and WebSocket components | Declared dependencies; Home Assistant loads them and their requirements automatically. |

**No separate database server is required.** Baselines, print history, energy
totals and Printcast use Home Assistant's storage helper. Files are created
as data is generated and saved. No database user, password or SQL schema is needed.

HACS downloads files; Home Assistant installs declared Python dependencies.
Dependencies may be installed **before** the wizard opens. Downloading is
your consent to that package installation. The wizard separately requires
explicit acceptance before connecting to your printer. HACS integrations cannot
run a host-wide installer or install arbitrary HAOS add-ons, printer firmware
or operating-system packages.

### Install and configure

1. Back up Home Assistant. If the upstream Moonraker integration is installed,
   read the migration section below first.
2. Open **HACS → menu → Custom repositories**, add
   `https://github.com/thaliamontreux/HACS_Moonraker_Advanced`, and select
   **Integration**. This is a custom repository, not a default HACS listing.
3. Download **Advance_Moonraker_Control** and restart Home Assistant when ready.
4. In **Settings → Devices & services → Add integration**, search for
   **Advance_Moonraker_Control**.
5. Read and accept the requirements, or close the dialog to cancel.
   No printer connection is made before acceptance.
6. Enter the host (without `http://`, `https://` or a path), port, TLS setting,
   API key if required and optional printer name. Setup reads `printer.info`
   and closes its temporary connection. Failed connections stay on the form
   so you can correct the details.
7. Choose optional entities/preferences or submit defaults for a basic
   installation. Home Assistant sets up discovered entities and the
   **Advance_Moonraker_Control** sidebar panel.
8. Check that the device is available and shows current data. Add additional
   printers with **Add integration**; change options later through **Configure**.

### Optional requirements

The core dashboard works without these. Configure each service first, then
choose its entity or settings in the wizard or Configure screen.

| Feature | Additional setup |
| --- | --- |
| Video/snapshots | Reachable webcam configured in Moonraker, or camera URL overrides. |
| Spool inventory | Separate [Spoolman](https://github.com/Donkie/Spoolman) installation connected to Moonraker. Its own installer manages its database. |
| Energy/cost | Home Assistant power sensor and your energy price per kWh. |
| Environmental/moisture estimates | Temperature and humidity sensor entities; estimates depend on measurements and history. |
| Notifications | Configured `notify` service, without the `notify.` prefix (e.g. `mobile_app_myphone`). |
| Automatic power-off | Select the correct power switch, cooling threshold and delay. **Selecting the switch enables this automation.** Leave it empty for manual power control. |
| AI vision | Both a camera entity and a configured `ai_task` entity. Your provider may receive images and charge for requests. |
| Assist/voice | Configure Assist and custom sentences for the registered intents. Add TTS, media players and automations for spoken announcements. |

`TTS_Playback/` is an optional development audio collection outside the HACS
runtime package. It is not automatically installed or played. AppDaemon and
voice-generation scripts are not runtime requirements. FFmpeg is included in
HAOS/HA Container if your chosen audio/video pipeline needs it; regenerating
or combining external audio clips is a separate task.

## Updates and migration

HACS obtains versions and files from **GitHub releases in this repository**.
Review release notes, back up, install the update in HACS and restart when
convenient. Until releases are published, HACS can offer the default branch
as a development snapshot. Printer component update entities refer to printer
software, not updates to this Home Assistant integration.

The integration domain is `advance_moonraker_control`. This is an independent
product: **do not run it alongside the original `moonraker` integration or the
earlier `haos_hacs_moonraker_console` HACS entry** — remove those first, then
add this repository. Configuration does not migrate automatically because
entity IDs, storage keys, services and panel routes are namespaced by the new
domain; re-add each printer and re-select optional features after installing.

Releases use calendar versions `YYYY.MM.DD` (for example `2026.10.23`), one
per day. Dated versions sort above the old `999.0.0` development builds, so
HACS offers the first dated release as a normal upgrade. For rollback, select
a previous release in HACS and restart; restore a backup if a release changed
data formats.

## Troubleshooting

- **Dependency installation fails:** check package-index connectivity, disk
  space and Home Assistant logs. Retry after correcting the problem. Do not
  install the development `requirements.txt` into a running Home Assistant.
- **Cannot connect:** check host, port, firewall, TLS and Moonraker authentication.
  Do not publish API keys or raw connection logs.
- **Unavailable printer:** check Moonraker/Klipper. Home Assistant retries
  unavailable entries; reinstalling should not be necessary.
- **Missing panel:** complete the restart and integration setup, refresh the
  browser and inspect logs for setup failures.
- **Missing optional features:** configure the corresponding service and select
  its available entities.
- **Storage errors:** ensure the configuration volume is writable with free
  space. Preserve `.storage` during upgrades and backups.

Hardware variants may differ from standard Moonraker. Upstream reports issues
with FLSUN Speeder Pad and Sonic Pad; compatibility is not established.
Report problems through [GitHub issues](https://github.com/thaliamontreux/HACS_Moonraker_Advanced/issues).

## Development and attribution

See [the release procedure](docs/development/releases.md) for versioning and
GitHub releases, and `AGENTS.md` for checks. The release workflow validates
the version/tag, HACS metadata, Hassfest, tests and docs before publishing.

Credit for the original work goes to the author of the original
`moonraker-home-assistant` integration, whose MIT-licensed codebase this
project began from. Original authorship is preserved in [LICENSE](LICENSE).
This project is an independent development maintained by
[Thalia Montreux](https://github.com/thaliamontreux) — it is not affiliated
with, endorsed by, or linked to the original project.
Thanks to Clifford Roche for the `moonraker-api` Python library.
