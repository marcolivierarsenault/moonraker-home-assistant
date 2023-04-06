Sensors
==========================================

Most of the sensor objects come straight from the API. It is available
`here <https://moonraker.readthedocs.io/en/latest/printer_objects/>`__

Default sensor
--------------

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
    - Based on our Calculated percentage
  * - print time left
    - Total predicted length left for the print
    - Based on our Calculated percentage
  * - print ETA
    - Estimated time at which the print will be finished
    - Based on our Calculated percentage
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



History sensor
--------------

History info, *if enabled in moonraker config*.

.. list-table:: Title
   :widths: 25 25 50
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

Optional sensor
---------------

-  For every optional fan object available in [“heater_fan”,
   “controller_fan”] we will create a sensor showing fan speed.
-  For every optional temperature object available in
   [“temperature_sensor”, “temperature_fan”, “bme280”, “htu21d”, “lm75”]
   we will create a sensor showing sensor temperature.