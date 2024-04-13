Connection Issues
====================================================

If you are trying to configure the integration and have a problem with it connecting to the moonraker API, and see something similar in your Home Assistant logs....

.. code-block:: yaml

    Logger: moonraker_api.websockets.websocketclient
    Source: runner.py:186
    First occurred: 11:52:47 AM (1 occurrences)
    Last logged: 11:52:47 AM
    Websocket connection error: Cannot connect to host 192.168.1.111:7125 ssl:default [Connect call failed ('192.168.1.111', 7125)]

Edit your `moonraker.conf` file (on your printer)
If `localhost` is specified,

.. code-block:: yaml

    [server]
    host: localhost
    port: 7125
    enable_debug_logging: False

replace localhost with 0.0.0.0 and restart the printer

.. code-block:: yaml

    [server]
    host: 0.0.0.0
    port: 7125
    enable_debug_logging: False
