"""No-op ``fcntl`` stand-in for running the test suite on Windows.

``pytest_homeassistant_custom_component`` imports ``homeassistant.runner``
at plugin load time, and ``runner`` does ``import fcntl`` — a POSIX-only
module. The runner only calls ``fcntl.flock`` when Home Assistant is
actually started, which never happens under pytest, so inert no-ops are
sufficient. This module is only placed on ``PYTHONPATH`` by
``scripts/test_strict`` when the platform lacks a real ``fcntl``.
"""

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8


def flock(*args, **kwargs):
    """No-op advisory lock."""


def lockf(*args, **kwargs):
    """No-op lockf."""


def fcntl(*args, **kwargs):
    """No-op descriptor command."""
    return 0


def ioctl(*args, **kwargs):
    """No-op ioctl."""
    return 0
