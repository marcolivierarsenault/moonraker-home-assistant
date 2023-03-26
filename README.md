[![codecov](https://codecov.io/github/marcolivierarsenault/moonraker-home-assistant/branch/main/graph/badge.svg?token=OT5PZG1QZE)](https://codecov.io/github/marcolivierarsenault/moonraker-home-assistant)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-blue.svg)](https://github.com/custom-components/hacs)
![install_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.moonraker.total)

# Moonraker Home Assistant

Non official integration for Moonraker and Klipper in Home Assistant (via HACS).

# Supported Entities

This allows you home assistant to connect to your 3D printer and display:

- Key informations about the printer (sensors)
- Show the camera image (if installed)
- Thumbnail of what is being printed at the moment.
- Emergency stop button
- Button to trigger macros

To access the list of all entities and their documentations, look at our [WIKI](https://github.com/marcolivierarsenault/moonraker-home-assistant/wiki/Entities). The list of entities keeps growing on each versions :rocket: . Keep an eye on the wiki page.

# Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marcolivierarsenault&repository=moonraker-home-assistant&category=integration)

## Current way to install via HACS

- The installation is done inside [HACS](https://hacs.xyz/) (Home Assistant Community Store). If you don't have HACS, you must install it before adding this integration. [Installation instructions here.](https://hacs.xyz/docs/setup/download)
- Once HACS is installed, search for `moonraker`
  - Navigate to the 'Integrations' tab in HACS, click `explore & Download` and search for the 'Moonraker' integration there. On the next screen, select "Download". Once fully downloaded, restart HomeAssistant.
- In the sidebar, click 'Configuration', then 'Devices & Services'. Click the + icon to add "Moonraker" to your Home Assistant installation. An URL (or IP) of your Moonraker and start printing. If your printer use another port than 7125 or if you use an API key, you can add it in the configuration.

# Support

You have issue with the integration, you want new sensors? Please open an Issue.

# Screenshot

![sensor](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/sensors.png)
![button](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/button.png)
![camera](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/camera.png)
![thumbnial](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/thumbnail.png)

# Slack Workspace

Join our [Slack Workspace](https://join.slack.com/t/moonraker-ha/shared_invite/zt-1q7rqkttj-SQ5N7qm9d1h6HqIONpDhZA) for more Sync conversations
