Buttons
=================================

Buttons are available to send command to the printer.

Default buttons
---------------------------------

A series of buttons are available by default. They are:

.. list-table:: Default Buttons
  :header-rows: 1

  * - Button Name
    - Description
    - Definition
  * - Emergency Stop
    - Complete and imediate stop of the printer.
    - From Moonraker API (*printer.emergency_stop*)
  * - Pause Print
    - Pause the current print.
    - From Moonraker API (*printer.print.pause*)
  * - Resume Print
    - Resume the print (after a pause).
    - From Moonraker API (*printer.print.resume*)
  * - Cancel Print
    - Cancel current print.
    - From Moonraker API (*printer.print.cancel*)
  * - Server Restart
    - Restart Klipper software.
    - From Moonraker API (*server.restart*)
  * - Host Restart
    - Restart the device running Klipper (Rpi).
    - From Moonraker API (*printer.restart*)
  * - Firmware Restart
    - Restart the printer onboard controller.
    - From Moonraker API (*printer.firmware_restart*)


Macros
---------------------------------

Each macro configured in Klipper is available as a button.

.. note::

   Current limitation, we cannot change any parameter for those macros.