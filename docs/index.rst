Welcome to Moonraker Home Assistant's documentation!
====================================================

.. note::

   This is the non-official custom integration of Moonraker and Klipper for Home Assistant.

This is a custom integration for Home Assistant to control your 3D printer powered by Moonraker and Klipper. The integration prodvides entities for the following:

* Key informations about the printer (sensors)

* Show the camera image (if installed)

* Thumbnail of what is being printed at the moment.

* Emergency stop button

* Button to trigger macros

Special thanks
-------------------------------------
Special thanks to `Clifford Roche <https://github.com/cmroche>`__ who built `moonraker-api <https://github.com/cmroche/moonraker-api>`__ which it the conector library we are using for this integration. 🚀


.. toctree::
   :caption: Installation
   :hidden:

   install
   dashboard

.. toctree::
   :caption: Usage
   :hidden:

   entities/sensors
   entities/camera
   entities/controls
   entities/calculated_pct

.. toctree::
   :caption: Support
   :hidden:

   support/logs
   support/latest
   support/reload