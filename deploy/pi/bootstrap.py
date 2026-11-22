#!/usr/bin/python3
"""Prepare a rollback baseline and install system services without starting the controller."""
import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile

import yaml


def install(src, dst, mode, group=0):
    shutil.copyfile(src, dst)
    os.chown(dst, 0, group)
    dst.chmod(mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", type=Path, help="Working backend directory with run.py")
    parser.add_argument("config", type=Path, help="Working live YAML; the source is read only")
    parser.add_argument("private", type=Path, help="Private bootstrap directory, outside the checkout")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Root required to prepare service accounts and unit files")
    os.umask(0o077)
    root = Path("/var/lib/terrapi")
    tools = Path("/usr/local/lib/terrapi")
    keys = Path("/etc/terrapi")
    if (root / "current").exists():
        parser.error("An installed controller already owns this location")
    private = args.private.resolve(strict=True)
    for name in ("updater.json", "settings.json", "recipient.pem", "recipient.key", "signing.pub"):
        if not (private / name).is_file():
            parser.error("Missing bootstrap file: " + name)
    settings = json.loads((private / "settings.json").read_bytes())
    config = yaml.safe_load(args.config.read_bytes())
    config["mqtt"].update(host="${MQTT_HOST}", port=int(settings["port"]), use_ssl=True,
                         user="${MQTT_USER}", password="${MQTT_PASSWORD}")
    try:
        user = pwd.getpwnam("terrapi")
    except KeyError:
        subprocess.run(["useradd", "--system", "--user-group", "--no-create-home",
                        "--shell", "/usr/sbin/nologin", "terrapi"], check=True)
        user = pwd.getpwnam("terrapi")
    grp.getgrnam("gpio")
    try:
        pwd.getpwnam("terrapi-build")
    except KeyError:
        subprocess.run(["useradd", "--system", "--no-create-home", "--shell",
                        "/usr/sbin/nologin", "terrapi-build"], check=True)
    for folder, mode in ((tools, 0o755), (root, 0o711), (keys, 0o700),
                         (root / "releases", 0o711), (root / "config", 0o700)):
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(mode)
    # Keep the original live controller and config available for the initial handoff.
    os.chown(root / "config", user.pw_uid, user.pw_gid)
    conf = root / "config/config.yaml"
    if not conf.exists():
        conf.write_text(yaml.safe_dump(config, sort_keys=False))
        os.chown(conf, user.pw_uid, user.pw_gid)
    for name in ("updater.json", "recipient.pem", "recipient.key", "signing.pub"):
        install(private / name, keys / name, 0o600)
    source = Path(__file__).resolve().parent
    for name in ("updater.py", "start_controller.py"):
        install(source / name, tools / name, 0o755)
    for name in ("terrapi-updater.service", "terrapi-controller.service"):
        install(source / name, Path("/etc/systemd/system") / name, 0o644)
    with tempfile.TemporaryDirectory(dir=root / "releases") as staging:
        release = Path(staging) / "baseline"
        release.mkdir(mode=0o750)
        os.chown(release, 0, user.pw_gid)
        release.chmod(0o750)
        install(args.backend / "run.py", release / "run.py", 0o640, user.pw_gid)
        package = release / "terrapi"
        package.mkdir()
        package.chmod(0o755)
        for module in (args.backend / "terrapi").glob("*.py"):
            install(module, package / module.name, 0o640, user.pw_gid)
        install(private / "settings.json", release / "settings.json", 0o640, user.pw_gid)
        # Use the already provisioned system Python and native GPIO stack for baseline.
        (release / "venv").symlink_to("/usr")
        final = root / "releases/0"
        release.rename(final)
    (root / "current").symlink_to(final)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("Baseline prepared. Start the services during the coordinated broker and controller handoff.")


if __name__ == "__main__":
    main()
