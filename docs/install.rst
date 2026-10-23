Install Advance_Moonraker_Control
==================================================

The maintained `installation guide
<https://github.com/thaliamontreux/haos_hacs_moonraker_console#installation>`__
includes requirements, optional services, migration and troubleshooting.

You need Home Assistant 2026.9.0+, HACS 2.0+ and an accessible Klipper/Moonraker
printer. Home Assistant installs the declared Python library and panel
dependencies, potentially before the wizard opens. Read the requirements before
downloading. No separate database is needed; integration storage is created
automatically as data is generated.

1. Back up Home Assistant. Add
   ``https://github.com/thaliamontreux/haos_hacs_moonraker_console`` to HACS
   custom repositories with category **Integration**.
2. Download **Advance_Moonraker_Control** and restart when ready.
3. In **Settings → Devices & services → Add integration**, select
   **Advance_Moonraker_Control**.
4. Read and accept the requirements. Closing cancels before any printer connection.
5. Supply the host, port, TLS setting, optional API key and printer name.
   The connection test only reads printer information.
6. Choose optional entities or leave defaults. Selecting a power switch enables
   automatic power-off after printing and cooling. AI vision requires a provider
   and camera, and may transmit images to the provider.

Entities and the sidebar panel are created automatically. Install optional
external services separately; HACS cannot provision printer software or host
packages. Feature settings remain editable through Configure.

Updates and migration
---------------------

HACS checks GitHub releases in this repository. Back up, review release notes,
install the chosen update and restart Home Assistant. Until a release is
published, the default branch is a development download.

The domain remains ``moonraker``. Do not install the original integration
alongside this fork. Keep config entries and storage when switching HACS
repositories. Releases use calendar versions ``YYYY.MM.DD``; these sort above
the old ``999.0.0`` development builds, so they upgrade normally.
