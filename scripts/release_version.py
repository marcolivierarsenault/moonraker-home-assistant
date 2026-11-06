#!/usr/bin/env python3
"""Compute and apply integration release versions.

Versions look like ``1.14.0`` (stable) or ``1.14.0b0`` (pre-release).
``manifest.json`` is the source of truth; ``const.py`` mirrors it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "moonraker" / "manifest.json"
CONST = ROOT / "custom_components" / "moonraker" / "const.py"

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:b(\d+))?$")
CONST_RE = re.compile(r'^VERSION = "[^"]*"$', re.MULTILINE)
MANIFEST_RE = re.compile(r'("version":\s*)"[^"]*"')
BUMPS = ("major", "minor", "patch")


def parse(version: str) -> tuple[int, int, int, int | None]:
    """Split a version into (major, minor, patch, beta)."""
    match = VERSION_RE.match(version)
    if not match:
        raise ValueError(f"Invalid version {version!r}, expected X.Y.Z or X.Y.ZbN")
    major, minor, patch, beta = match.groups()
    return int(major), int(minor), int(patch), None if beta is None else int(beta)


def is_prerelease(version: str) -> bool:
    """Return True for a beta version."""
    return parse(version)[3] is not None


def next_version(current: str, bump: str, prerelease: bool) -> str:
    """Return the version that follows ``current``.

    From a stable version, ``bump`` picks the part to increase and
    ``prerelease`` appends ``b0``. From a beta, ``bump`` is ignored: another
    beta increments the beta number, a stable release drops the suffix.
    """
    if bump not in BUMPS:
        raise ValueError(f"Invalid bump {bump!r}, expected one of {BUMPS}")
    major, minor, patch, beta = parse(current)
    if beta is not None:
        base = f"{major}.{minor}.{patch}"
        return f"{base}b{beta + 1}" if prerelease else base
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    base = f"{major}.{minor}.{patch}"
    return f"{base}b0" if prerelease else base


def read_version() -> str:
    """Return the version in manifest.json."""
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]


def write_version(version: str) -> None:
    """Write ``version`` to manifest.json and const.py."""
    parse(version)
    for path, pattern, replacement in (
        (MANIFEST, MANIFEST_RE, rf'\g<1>"{version}"'),
        (CONST, CONST_RE, f'VERSION = "{version}"'),
    ):
        text = path.read_text(encoding="utf-8")
        new_text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"Version string not found in {path}")
        path.write_text(new_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("current", help="print the current version")
    nxt = sub.add_parser("next", help="print the next version")
    nxt.add_argument("bump", choices=BUMPS)
    nxt.add_argument("--pre", action="store_true", help="make a beta version")
    setter = sub.add_parser("set", help="write a version to the integration")
    setter.add_argument("version")
    check = sub.add_parser("is-prerelease", help="exit 0 if version is a beta")
    check.add_argument("version", nargs="?")
    args = parser.parse_args(argv)

    try:
        if args.command == "current":
            sys.stdout.write(f"{read_version()}\n")
        elif args.command == "next":
            sys.stdout.write(f"{next_version(read_version(), args.bump, args.pre)}\n")
        elif args.command == "set":
            write_version(args.version)
        else:
            return 0 if is_prerelease(args.version or read_version()) else 1
    except (ValueError, RuntimeError) as err:
        sys.stderr.write(f"{err}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
