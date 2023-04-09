Calculated values
=====================================

.. _percentage:

Calculated Percentage of Completion
-------------------------------------

We have our own calculation of % of completeness (to mimic Mainsail UI). We assume the current job % completion rate is the midpoint between the % completed from the gcode file and the % of filament used (based on total filament prediction for the print)


.. _layer:

Calculated Current Layer
-------------------------------------

We have our own calculation for the current layer being printed. We use the toolhead Z position and information about layer heights to determine the current layer.

.. code-block:: python

    round(
        (data["status"]["toolhead"]["position"][2] - data["first_layer_height"])
        / data["layer_height"],
        0,
    )