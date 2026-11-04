"""No-op ``resource`` stand-in for running the test suite on Windows.

``homeassistant.util.resource`` provides ``set_open_file_descriptor_limit``
which is only invoked when Home Assistant actually starts — never under
pytest. This stub exists purely so the import chain resolves on Windows;
it is only placed on ``PYTHONPATH`` when the real module is unavailable.
"""

RLIMIT_NOFILE = 7
RLIMIT_CORE = 4
RLIMIT_AS = 9
RLIMIT_NPROC = 6
RLIM_INFINITY = -1


def getrlimit(*args, **kwargs):
    """Return an inert soft/hard limit pair."""
    return (RLIM_INFINITY, RLIM_INFINITY)


def setrlimit(*args, **kwargs):
    """No-op resource limit setter."""


def getrusage(*args, **kwargs):
    """Return a zero-valued usage stub."""

    class _Usage:
        ru_maxrss = 0

        def __getattr__(self, name):
            return 0

    return _Usage()
