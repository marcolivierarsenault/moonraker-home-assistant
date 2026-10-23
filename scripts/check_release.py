"""Validate the HACS runtime package and matching release versions."""

import argparse
import ast
import configparser
import datetime
import json
from pathlib import Path
import re


def validate(root: Path, tag: str | None = None) -> str:
    """Reject incomplete packages or mismatched version metadata."""
    integration = root / "custom_components" / "moonraker"
    manifest = json.loads((integration / "manifest.json").read_text(encoding="utf-8"))
    hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(
            (integration / "const.py").read_text(encoding="utf-8")
        ).body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"NAME", "VERSION", "DOMAIN"}
    }
    config = configparser.ConfigParser()
    config.read(root / "setup.cfg", encoding="utf-8")
    version = manifest["version"]
    if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", version):
        raise ValueError("Release version must use YYYY.MM.DD format")
    try:
        datetime.date.fromisoformat(version.replace(".", "-"))
    except ValueError as exc:
        raise ValueError(f"Not a real calendar date: {version}") from exc
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Release tag must be v{version}")
    if (
        version != constants["VERSION"]
        or version != config["bumpversion"]["current_version"]
    ):
        raise ValueError("Manifest, constants and bumpversion versions must match")
    if manifest["name"] != constants["NAME"] or hacs["name"] != constants["NAME"]:
        raise ValueError("HACS and integration names must match")
    if manifest["domain"] != constants["DOMAIN"] or manifest["domain"] != "moonraker":
        raise ValueError("Preserve the moonraker domain for existing installations")
    if hacs.get("zip_release") or hacs.get("content_in_root"):
        raise ValueError("This package uses the custom_components source tree")
    directories = [
        path.name
        for path in (root / "custom_components").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    ]
    if directories != ["moonraker"]:
        raise ValueError("HACS requires exactly one integration")
    for filename in (
        "__init__.py",
        "config_flow.py",
        "services.yaml",
        "analyzer.py",
        "printcast.py",
        "panel.py",
        "panel.html",
        "panel_module.js",
        "panel_client.js",
        "panel_i18n.js",
        "toolpath_parse.js",
        "toolpath_worker.js",
        "translations/en.json",
        "translations/es.json",
        "translations/fr.json",
    ):
        if not (integration / filename).is_file():
            raise ValueError(f"Missing runtime file: {filename}")
    for path in (integration / "translations").glob("*.json"):
        translation = json.loads(path.read_text(encoding="utf-8"))
        for step in ("requirements", "user", "features"):
            if step not in translation["config"]["step"]:
                raise ValueError(f"{path.name} is missing installation step {step}")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Expected GitHub release tag, e.g. v2026.10.23")
    args = parser.parse_args()
    validate(Path(__file__).resolve().parents[1], args.tag)
