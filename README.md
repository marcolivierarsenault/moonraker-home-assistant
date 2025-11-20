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

To access the list of all entities and their documentations, look at our [documentation](https://moonraker-home-assistant.readthedocs.io/en/latest/). The list of entities keeps growing on each versions :rocket: . Keep an eye on the releases.

## Hardware Limits

This software seems to have issues working on **FLSUN Speeder Pad** and **Sonic Pad**, so those are unsuported.

# Install

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=marcolivierarsenault&repository=moonraker-home-assistant&category=integration)

## Install via HACS

- The installation is done inside [HACS](https://hacs.xyz/) (Home Assistant Community Store). If you don't have HACS, you must install it before adding this integration. [Installation instructions here.](https://hacs.xyz/docs/use/#getting-started-with-hacs)
- Once HACS is installed, search for `moonraker`
  - Navigate to the 'Integrations' tab in HACS, click `explore & Download` and search for the 'Moonraker' integration there. On the next screen, select "Download". Once fully downloaded, restart HomeAssistant.
- In the sidebar, click 'Configuration', then 'Devices & Services'. Click the + icon to add "Moonraker" to your Home Assistant installation.
  - Enter the host or IP of your Moonraker installation.
  - Change your printer's port if you don't use the default of 7125.
  - Optionally enter your API key if you have required one in Moonraker.
  - Optionally specify your printer's name if you don't want to use the hostname of your moonraker installation.

# Support

You have issue with the integration, you want new sensors? Please open an Issue.

# Screenshot

![sensor](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/sensors.png)
![button](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/button.png)
![camera](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/camera.png)
![thumbnial](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/thumbnail.png)

# Special thanks

Special thanks to [Clifford Roche](https://github.com/cmroche) who built [moonraker-api](https://github.com/cmroche/moonraker-api) which it the conector library we are using for this integration. 🚀
