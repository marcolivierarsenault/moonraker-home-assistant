Camera
==========================

* Livestream of any camera configured in crownest. |cam_image|

  * Current issue: Not supporting FLSUN or Creality SonicPad

* Thumbnail of the current print. (Your slicer needs to generate the thumbnail image) |thum_image|

.. _camera_config:

Manual Configuration
-------------------------------------

It is possible to manually configure the Stream and Snapshot URL for the camera. This will bypass the automatic configuration.

|config|

.. |cam_image| image:: https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/camera.png
.. |thum_image| image:: https://raw.githubusercontent.com/marcolivierarsenault/moonraker-home-assistant/main/assets/thumbnail.png
.. |config| image:: /_static/config.png


Camera Rotation
-------------------------------------

If you want to rotate the camera image, you can do so by changing the dashboard layout. Using `card mod <https://github.com/thomasloven/lovelace-card-mod>`__.

With the extension installed, just modify your layout yaml. (apply the appropriate rotation (90, 180, 270))

.. code-block:: yaml

    card:
      type: picture-entity
      entity: camera.mkspi_webcam
      camera_view: live
      show_name: false
      show_state: false
      card_mod:
        style: |
          hui-image{
            transform: rotate(-180deg);
          }
