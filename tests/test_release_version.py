"""Tests for scripts/release_version.py."""

import importlib.util
from pathlib import Path

import pytest

# Imported so the autouse conftest patches can resolve their targets.
from custom_components import moonraker  # noqa: F401

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release_version.py"
_spec = importlib.util.spec_from_file_location("release_version", SCRIPT)
release_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_version)


@pytest.mark.parametrize(
    ("current", "bump", "prerelease", "expected"),
    [
        ("1.13.4", "patch", False, "1.13.5"),
        ("1.13.4", "minor", False, "1.14.0"),
        ("1.13.4", "major", False, "2.0.0"),
        ("1.13.4", "minor", True, "1.14.0b0"),
        ("1.13.4", "patch", True, "1.13.5b0"),
        ("1.14.0b0", "minor", True, "1.14.0b1"),
        ("1.14.0b3", "major", False, "1.14.0"),
    ],
)
def test_next_version(current, bump, prerelease, expected):
    """Next versions follow the documented rules."""
    assert release_version.next_version(current, bump, prerelease) == expected


@pytest.mark.parametrize("version", ["1.14", "v1.14.0", "1.14.0rc1", "1.14.0b"])
def test_invalid_version(version):
    """Malformed versions are rejected."""
    with pytest.raises(ValueError):
        release_version.parse(version)


def test_invalid_bump():
    """Unknown bump parts are rejected."""
    with pytest.raises(ValueError):
        release_version.next_version("1.0.0", "build", False)


def test_is_prerelease():
    """Beta versions are pre-releases."""
    assert release_version.is_prerelease("1.14.0b0")
    assert not release_version.is_prerelease("1.14.0")


def test_write_version(tmp_path, monkeypatch):
    """Writing a version updates manifest.json and const.py."""
    manifest = tmp_path / "manifest.json"
    const = tmp_path / "const.py"
    manifest.write_text('{\n  "domain": "moonraker",\n  "version": "1.13.4"\n}\n')
    const.write_text('DOMAIN = "moonraker"\nVERSION = "1.13.4"\n')
    monkeypatch.setattr(release_version, "MANIFEST", manifest)
    monkeypatch.setattr(release_version, "CONST", const)

    release_version.write_version("1.14.0b0")

    assert release_version.read_version() == "1.14.0b0"
    assert 'VERSION = "1.14.0b0"' in const.read_text()
    with pytest.raises(ValueError):
        release_version.write_version("1.14")


def test_main(tmp_path, monkeypatch, capsys):
    """The command line prints and checks versions."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"version": "1.14.0b0"}')
    monkeypatch.setattr(release_version, "MANIFEST", manifest)

    assert release_version.main(["current"]) == 0
    assert release_version.main(["next", "minor", "--pre"]) == 0
    assert capsys.readouterr().out.split() == ["1.14.0b0", "1.14.0b1"]
    assert release_version.main(["is-prerelease"]) == 0
    assert release_version.main(["is-prerelease", "1.14.0"]) == 1
    assert release_version.main(["set", "bad"]) == 2
