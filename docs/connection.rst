Connection properties
======================

The connection properties dialog can be used to connect to the Moonraker API.
The integration is capable of connecting to most Moonraker deployments.

.. image:: _static/connection-dialog.png
    :align: center

Connection properties can be defined as follows:

.. list-table:: Connection properties
  :header-rows: 1

  * - name
    - default
    - description
  * - Host
    - None, **(required)**
    - IP address or hostname of Moonraker
  * - Port
    - 7125
    - Moonraker port
  * - Uses TLS
    -
    - use encrypted connections
  * - API Key
    -
    - Moonraker API key
  * - Username
    -
    - Moonraker user, only used to fetch the API key
  * - Password
    -
    - Password of the Moonraker user
  * - Printer's Name
    - Host address
    - Device name in Home Assistant

Note: Encrypted connections must be configured in Moonraker API or by using a
reverse proxy to connect to Moonraker API.


Authentication
-------------------------------------

If Moonraker requires authorization (for example when logins are required in
Fluidd or Mainsail), the integration needs the Moonraker API key.

You can either enter the API key directly, or leave it empty and enter a
Moonraker username and password instead. The integration then logs in once,
fetches the API key and stores only the key. The username and password are not
saved.

If the API key is regenerated in Moonraker, remove the integration and add it
again.


Polling Rate Configuration
-------------------------------------

It is possible to change the default polling rate value (30 sec) of the integration.

In the integration configuration, you can set the polling rate manually.

*Too small value may overload your Home Assisant setup and your Moonraker setup.*

*This will setting affects the polling frequency whether or not the printer is printing.*

Camera Manual Configuration
-------------------------------------

Camera URL can be manually defined more details in the :ref:`camera_config`


Unreachable Printer
-------------------------------------

If you have your printer turned off by a smart switch or the printer is not reachable, the integration will periodically try to reconnect.
This is not problematic for Home Assistant, but it may create repetitive connection messages in the Home Assistant log file.

In the integration options for the affected printer, enable
``Log unreachable printer connection messages only at DEBUG level``.
When enabled, the integration first checks whether the Moonraker host and port are reachable and avoids starting the websocket client while the endpoint is offline.
This suppresses the normal warning/error noise for intentionally powered-off printers, while DEBUG logging still retains diagnostic information.
If a request fails while the connection still looks open, the endpoint is checked again, so a printer that was just switched off is also handled quietly.
Failures unrelated to reachability are still logged as errors.

Klipper Not Ready
-------------------------------------

Moonraker can be reachable while Klipper is not running, for example when the Moonraker host stays on but the printer board is powered off.
In that case, entities whose data Klipper no longer reports are shown as unavailable until the data comes back.

If Home Assistant starts while Klipper is not ready, Moonraker cannot list the printer objects.
The integration still loads, but entities for those objects (heaters, fans, sensors, output pins, lights, filament sensors) are not created.
Reload the integration once Klipper is ready to add them.

Change IP/Hostname of your printer
-------------------------------------

If you want to change the IP/Hostname of your printer, you can do it by either deleting the integration and adding it again or by changing the IP/Hostname in the integration configuration or by manually changing the value in your Home Assistant configuration file.

Go in `whateverConfigFolderYouHave/.storage/core.config_entries` and you should see a JSON entry with the printer IP/Hostname.

.. code-block:: JSON

  {"created_at":"2024-08-10T11:58:41.082494+00:00",
  "data":{"api_key":"","port":"7125","printer_name":"","tls":false,"url":"192.168.x.xx"},
  "disabled_by":null,
  "discovery_keys":{},
  "domain":"moonraker",
  "entry_id":"01J4Y2FDDTP0TKYYJX3RWYG79F",
  "minor_version":1,
  "modified_at":"2024-08-10T11:58:41.093068+00:00",
  "options":{},
  "pref_disable_new_entities":false,
  "pref_disable_polling":false,
  "source":"user",
  "title":"mainsail",
  "unique_id":null,
  "version":1
  },

Change the IP/Hostname in the `url` field and restart Home Assistant.
