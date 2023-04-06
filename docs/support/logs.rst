Access your logs
====================================================

Couple of ways to access your logs so we can understand what is going on.

Get a copy of your HA logs
--------------------------

We might want a copy of your HA logs to see issue with moonraker.

Here is how to do it:

#. Open your Home Assistant
#. Click **Settings**
#. Click **Device & Services**
#. On the **Moonraker** tile, click **the 3 little dots (…)**
#. Click **Enable debug logging**
#. At this point Home Assistant it run for 5 min
#. (repeat up to step 5 (to go in the moonraker integration settings)
#. Click **reload** (This should download your log file on your computer) If not, Click **Disable debug logging**

Send the log back to us

Go full debug Log
-----------------

We might need advance logs, if so: #. Change your home assistant
configuration file. You have to open ``configuration.yaml`` and find the
section about logger (if it exist, add the detail about moonraker, if it
does not exist, create it. Make sure you set moonraker to ``debug``

.. code:: yaml

   # Example configuration.yaml entry
   logger:
     default: info
     logs:
       custom_components.moonraker: debug

#. Restart Home Assistant.
#. Let it run for 5-10 min
#. Download logs. **Home Assistant** -> **Settings** -> **System** -> **Logs**
#. At the bottom of the page **Download Full Logs**
#. Send them to us
