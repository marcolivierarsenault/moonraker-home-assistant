Controls
=================================

Different controls are available to send command to the printer.

Default Buttons
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
    - From Moonraker API (*machine.restart*)
  * - Host Shutdown
    - Shutdown the device running Klipper (Rpi).
    - From Moonraker API (*machine.shutdown*)
  * - Firmware Restart
    - Restart the printer onboard controller.
    - From Moonraker API (*printer.firmware_restart*)
  * - Printer Switch
    - Power On/Off the printer.
    - From Moonraker API (*machine.device_power.devices*)

Macros
---------------------------------

Each macro configured in Klipper is available as a button.

If the Macro description is `G-Code macro` it will be enabled by default, otherwise it will be disabled.
You can enable a specific macro by enabling it's entity in HomeAssistant configuration. (Like any other disabled entity.)

.. note::

   Current limitation, we cannot change any parameters for those macros.


Default Switches
---------------------------------

A series of switches are available by default. They are:

.. list-table:: Default Switches
  :header-rows: 1

  * - Switch Name
    - Description
    - Definition
  * - Printer Switch
    - Power On/Off the printer.
    - From Moonraker API (*machine.device_power.devices*)
  * - Output pin digital
    - Set a digital output pin to on or off.
    - From Moonraker API (*printer.gcode.script*)

Default Numbers
---------------------------------

A series of Numbers are available by default as slidder. They are:

.. list-table:: Default Numbers
  :header-rows: 1

  * - Number Name
    - Description
    - Definition
  * - Output pin pwm
    - Set a pwm output pin to a value.
    - From Moonraker API (*printer.gcode.script*)
