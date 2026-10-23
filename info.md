# Advance_Moonraker_Control

Monitor and control Klipper/Moonraker printers from Home Assistant: live data,
cameras, files and queues, macros, console, toolpath and bed-mesh views, print
history, energy estimates, Printcast forecasts, alerts and Assist intents.

Install this repository as a HACS **custom integration**. Home Assistant
installs the declared Python dependency and loads built-in panel components.
No separate SQL database or AppDaemon installation is needed.

After downloading and restarting, add **Advance_Moonraker_Control** in
Devices & services. The wizard explains requirements, asks for acceptance,
checks the printer connection and collects optional settings.

Read the [requirements, migration notes and installation guide](https://github.com/thaliamontreux/haos_hacs_moonraker_console#installation)
before downloading. Camera, Spoolman, AI and voice services are optional and
require their own configuration. HACS updates come from this repository's
[GitHub releases](https://github.com/thaliamontreux/haos_hacs_moonraker_console/releases).
