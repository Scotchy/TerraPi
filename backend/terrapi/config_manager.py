"""Validate, version and atomically persist the operator's live settings."""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

import yaml

from .config_schema import mapping, read_config, validate_config


def revision(config):
    # Period order matters when schedules overlap. Preserve it in the digest.
    editable = [config["modes"], config["planning"]]
    return hashlib.sha256(json.dumps(editable, ensure_ascii=False).encode()).hexdigest()


def public_config(config, current_mode):
    snapshot = {key: config[key] for key in ("modes", "planning", "log_interval")}
    for section in ("controls", "sensors"):
        snapshot[section] = {name: {"type": item["type"]} for name, item in config[section].items()}
    return dict(snapshot, revision=revision(config), current_mode=current_mode)


def save_config(path, config):
    path = Path(path)
    mode = stat.S_IMODE(path.stat().st_mode)
    temp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    staged = Path(temp.name)
    try:
        with temp:
            os.fchmod(temp.fileno(), mode)
            yaml.safe_dump(config, temp, sort_keys=False)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(staged, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        staged.unlink(missing_ok=True)


def update_config(path, changes, current_mode, expected=None):
    """The single controller serializes writers and installs the returned snapshot."""
    config = read_config(path)
    if expected is not None and expected != revision(config):
        raise ValueError("Settings changed. Reload the latest settings and reapply your edits.")
    if "planning" in changes:
        planning = mapping(changes["planning"], "Planning")
        if config["planning"]["active"] and planning.get("active") is False:
            config["manual_mode"] = current_mode
    config.update(changes)
    validate_config(config)
    save_config(path, config)
    return config
