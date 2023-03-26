[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]
[![hacs][hacsbadge]][hacs]
![install_badge](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.moonraker.total)

_Component to integrate with [Moonraker][integration_blueprint]._

Non official integration for Moonraker and Klipper in Home Assistant.

This allows you home assistant to connect to your Klipper 3D printer and display:

- Key information about the printer (sensors)
- Show the camera image (if installed)
- Thumbnail of what is being printed at the moment.
- Emergency stop button
- Button to trigger macros

### Entities details

[List of all sensors and details](https://github.com/marcolivierarsenault/moonraker-home-assistant/wiki/Entities)

## Platform

**This component will set up the following platforms.**

| Platform | Description                                                                         |
| -------- | ----------------------------------------------------------------------------------- |
| `sensor` | Show various info printer info from Moonraker.                                      |
| `camera` | Show camera livestream and thumbnail of current print.                              |
| `button` | Allow to use simple macro (cannot change variables) and trigger emergency shutdown. |

## Screenshots

![sensor](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/sensors.png)
![button](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/button.png)
![camera](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/camera.png)
![thumbnial](https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/thumbnail.png)

<!---->

---

[integration_blueprint]: https://github.com/marcolivierarsenault/moonraker-home-assistant
[commits-shield]: https://img.shields.io/github/commit-activity/y/marcolivierarsenault/moonraker-home-assistant.svg?style=for-the-badge
[commits]: https://github.com/marcolivierarsenault/moonraker-home-assistant/commits/master
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license]: https://github.com/marcolivierarsenault/moonraker-home-assistant/blob/main/LICENSE
[license-shield]: https://img.shields.io/github/license/marcolivierarsenault/moonraker-home-assistant.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/marcolivierarsenault/moonraker-home-assistant.svg?style=for-the-badge
[releases]: https://github.com/marcolivierarsenault/moonraker-home-assistant/releases
