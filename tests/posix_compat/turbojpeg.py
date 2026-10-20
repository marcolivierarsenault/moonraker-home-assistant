"""No-op ``turbojpeg`` stand-in for running the test suite on Windows.

``homeassistant.components.camera.img_util`` imports ``TurboJPEG`` at
module load time, but the PyTurboJPEG package needs the native
libturbojpeg shared library, which is unavailable on Windows test
hosts. The component tests never exercise actual JPEG transcoding,
so an inert class is sufficient. This module is only placed on
``PYTHONPATH`` by ``scripts/test_strict`` when needed.
"""


class TurboJPEG:
    """Inert TurboJPEG replacement."""

    def __init__(self, *args, **kwargs):
        """Accept and ignore the native library path."""

    def encode(self, *args, **kwargs):
        """Return empty bytes for encoding calls."""
        return b""

    def decode(self, *args, **kwargs):
        """Return an empty frame for decoding calls."""
        return b""
