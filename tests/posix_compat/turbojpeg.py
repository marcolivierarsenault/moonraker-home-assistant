"""Test-only shim for the optional ``turbojpeg`` dependency.

The real ``turbojpeg`` package needs the native libturbojpeg library, which
has no Windows wheel for Python 3.14. Home Assistant's ``img_util`` only
requires the ``TurboJPEG`` symbol; constructing it must fail so HA's
singleton falls back to ``False`` and skips the accelerated path.
"""


class TurboJPEG:
    """Placeholder that always fails construction like a missing library."""

    def __init__(self, *args, **kwargs) -> None:
        """Raise OSError to mirror a missing libturbojpeg installation."""
        raise OSError("libturbojpeg not available in test environment")
