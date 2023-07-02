Sensors
==========================================

Most of the sensor objects come straight from the API. It is available
`here <https://moonraker.readthedocs.io/en/latest/printer_objects/>`__

Default Sensors
----------------------------

Sensors that are added on integration startup.


.. list-table:: Default Sensors
  :header-rows: 1

  * - Sensor Name
    - Description
    - Definition
  * - Printer State
    - State of the Printer
    - From Moonraker API (printer info, state)
  * - Printer Message
    - Printer global message
    - From Moonraker API (printer info, state_message)
  * - Current Print Sate
    - State of the print, available values ["standby", "printing", "paused", "complete", "cancelled", "error"]
    - From Moonraker API (print_stats, state)
  * - Current Print Message
    - Message about current print
    - From Moonraker API (print_stats, message)
  * - Current Display Message
    - Display Message, sent via SET_DISPLAY_TEXT MSG=<message>
    - From Moonraker API (display_status, message)
  * - Extruder Temperature
    - Extruder Temperature
    - From Moonraker API (extruder, temperature)
  * - Extruder Temperature Target
    - Extruder Temperature Target
    - From Moonraker API (extruder, target)
  * - Extruder Power
    - Extruder current power consumption (in %). 100% = Max, 0% = close
    - From Moonraker API (extruder, power)
  * - Bed Temperature
    - Bed Temperature
    - From Moonraker API (heater_bed, temperature)
  * - Bed Temperature Target
    - Bed Temperature Target
    - From Moonraker API (heater_bed, target)
  * - Bed Power
    - Bed current power consumption (in %). 100% = Max, 0% = close
    - From Moonraker API (heater_bed, power)
  * - Filename
    - Filename of the current print
    - From Moonraker API (print_stats, filename)
  * - print Projected Total Duration
    - Total predicted duration of the print
    - Based on our :ref:`percentage`
  * - print time left
    - Total predicted length left for the print
    - Based on our :ref:`percentage`
  * - print ETA
    - Estimated time at which the print will be finished
    - Based on our :ref:`percentage`
  * - print duration
    - Print duration from start to now
    - From Moonraker API (print_stats, print_duration)
  * - Filament Used
    - Filament used since the start of current print
    - From Moonraker API (print_stats, filament_used)
  * - progress
    - Percentage of the current GCode file printed
    - From Moonraker API (display_status, filament_used)
  * - Fan Speed
    - Percentage of fan speed
    - From Moonraker API (fan, speed)
  * - Slicer Print Duration Estimate
    - Total duration of the print as estimated by the slicer
    - From Moonraker API (files_metadata, estimated_time)
  * - Slicer Print Time Left Estimate
    - Remaining time on the print according to the slicer estimate
    - Based on the slicer print duration estimate and the print duration so far
  * - Toolhead position X
    - X position of the toolhead
    - From Moonraker API (toolhead, position, x)
  * - Toolhead position Y
    - Y position of the toolhead
    - From Moonraker API (toolhead, position, y)
  * - Toolhead position Z
    - Z position of the toolhead
    - From Moonraker API (toolhead, position, z)
  * - Current Layer
    - Currenr layer being printed.
    - Based on our :ref:`layer`
  * - Total Layer
    - Total number of layer in the current print.
    - From Moonraker API (print_stats, info, total_layer). Make sure your Slicer include it. `Details <https://github.com/marcolivierarsenault/moonraker-home-assistant/issues/112#issuecomment-1505664692>`__


History Sensors
----------------------------

History info, *if enabled in moonraker config*.

.. list-table:: History Sensors
  :header-rows: 1

  * - Sensor Name
    - Description
    - Definition
  * - Totals jobs
    - Number of jobs ever ran.
    - From Moonraker API (job_totals, total_jobs)
  * - Totals Print Time
    - Cumulative print time
    - From Moonraker API (job_totals, total_print_time)
  * - Totals Filament Used
    - Cumulative filament used.
    - From Moonraker API (job_totals, total_filament_used)
  * - Longest Print
    - Time of the historical longest print.
    - From Moonraker API (job_totals, longest_print)


Binary Sensors
-----------------------------

Binary Sensors are used to represent a single binary value. They can are used for triggers, main use cases is the filament runout sensor.

.. list-table:: Binary Sensors
  :header-rows: 1

  * - Sensor Name
    - Description
    - Definition
  * - Filament Switch Sensor
    - True if filament is missing
    - From Moonraker API

Optional Sensors
-----------------------------

-  For every optional fan object available in [“heater_fan”,
   “controller_fan”, "fan_generic"] we will create a sensor showing fan speed.
-  For every optional temperature object available in
   [“temperature_sensor”, “temperature_fan”, “bme280”, “htu21d”, “lm75”]
   we will create a sensor showing sensor temperature.
