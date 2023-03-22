[![codecov](https://codecov.io/github/marcolivierarsenault/moonraker-home-assistant/branch/main/graph/badge.svg?token=OT5PZG1QZE)](https://codecov.io/github/marcolivierarsenault/moonraker-home-assistant)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/custom-components/hacs)
![install_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.moonraker.total)

# Moonraker Home Assistant

Non official integration for Moonraker in Home Assistant.

This allows you home assistant to connect to your 3D printer and display:

- key information about the printer (sensors)
- show the camera (if installed)
- thumbnail of what is being printed at the moment.

# Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marcolivierarsenault&repository=moonraker-home-assistant&category=integration)

## Current way to install via HACS

- The installation is done inside [HACS](https://hacs.xyz/) (Home Assistant Community Store). If you don't have HACS, you must install it before adding this integration. [Installation instructions here.](https://hacs.xyz/docs/setup/download)
- Once HACS is installed, search for `moonraker`
  - Navigate to the 'Integrations' tab in HACS, click `explore & Download` and search for the 'Moonraker' integration there. On the next screen, select "Download". Once fully downloaded, restart HomeAssistant.
- In the sidebar, click 'Configuration', then 'Devices & Services'. Click the + icon to add "Moonraker" to your Home Assistant installation. An URL (or IP) of your Moonraker and start printing

# Screenshot

|                                                 Sensors                                                  |                                                 Camera                                                  |
| :------------------------------------------------------------------------------------------------------: | :-----------------------------------------------------------------------------------------------------: |
| ![sensor](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/main/assets/sensors.png) | ![camera](https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/main/assets/camera.png) |

# Slack Workspace

Join our [Slack Workspace](https://join.slack.com/t/moonraker-ha/shared_invite/zt-1q7rqkttj-SQ5N7qm9d1h6HqIONpDhZA) for more Sync conversations
