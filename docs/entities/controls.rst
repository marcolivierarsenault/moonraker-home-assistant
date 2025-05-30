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
    - Complete and immediate stop of the printer.
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
  * - Start Print from Queue
    - Start the next print job in the queue.
    - From Moonraker API (*server.job_queue.start*)
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
  * - Reset Totals
    - Reset moonraker statistics. Button is disabled by default.
    - From Moonraker API (*server.history.reset_totals*)

Macros
---------------------------------

Each macro configured in Klipper is available as a button.

If the Macro description is `G-Code macro` it will be enabled by default, otherwise it will be disabled.
You can enable a specific macro by enabling it's entity in HomeAssistant configuration. (Like any other disabled entity.)

.. note::

   Current limitation, we cannot change any parameters for those macros.

Services
---------------------------------

Each service listed in Moonraker's ``available_services`` is exposed as a set of control buttons in Home Assistant:
**Start**, **Stop**, and **Restart**.

These buttons allow you to manage services such as ``klipper``, ``moonraker``, ``crowsnest``, and others directly from the Home Assistant interface.

All service control buttons are enabled by default.
You can disable or re-enable them through the Home Assistant entity settings, like any other entity.

.. note::

   The service state (e.g., running, stopped, or failed) is not currently used to filter or disable buttons.
   All services returned by Moonraker will have all three control buttons created regardless of their current status.


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

A series of Numbers are available by default as slider. They are:

.. list-table:: Default Numbers
  :header-rows: 1

  * - Number Name
    - Description
    - Definition
  * - Output pin pwm
    - Set a pwm output pin to a value.
    - From Moonraker API (*printer.gcode.script*)

Default LEDs
---------------------------------

A series of LEDs are available by default as a light control. They are:

.. list-table:: Default LEDs
  :header-rows: 1

  * - LED Name
    - Description
    - Definition
  * - <type> <name> e.g. neopixel strip
    - Set a light to a given brightness or rgb value.
    - From Moonraker API (*printer.gcode.script*)


Action (Serivce Call)
---------------------------------

List of actions available to send command to the printer.


.. list-table:: Actions
  :header-rows: 1

  * - Action
    - Description
    - Parameters
  * - G-code
    - G-code command to send to the printer. *(You can send one command at a time)*
    - | **Target**: (DEVICE) Moonraker device to send the command to.
      | **G-Code**: Select the GCode command you want to send