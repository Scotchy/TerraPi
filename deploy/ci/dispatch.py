"""Send a trusted build to the fixed SSH deployment entry point without logging private inputs."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


def required(name):
    value = os.environ[name]
    if not value:
        raise ValueError("Missing " + name)
    return value


def encode(data):
    return base64.b64encode(data).decode("ascii")


def monitoring_settings(settings, password_file):
    config = {key: settings[key] for key in ("mqtt_user", "mqtt_password", "dashboard_user")}
    if not all(isinstance(value, str) and value for value in config.values()):
        raise ValueError("Incomplete monitoring configuration")
    if config["mqtt_user"] == config["dashboard_user"]:
        raise ValueError("Collector and dashboard require separate identities")
    hashes = [digest for user, separator, digest in (line.partition(":") for line in password_file.splitlines())
              if separator and user == config["dashboard_user"]]
    if len(hashes) != 1 or not hashes[0].startswith("$7$"):
        raise ValueError("Expected one Mosquitto PBKDF2 hash for the selected dashboard user")
    if "history_days" in settings:
        days = settings["history_days"]
        if type(days) is not int or not 1 <= days <= 1825:
            raise ValueError("history_days must be between 1 and 1825")
        config["history_days"] = days
    return dict(config, dashboard_hash=hashes[0])


def controller_files(work, bundle, sequence, revision):
    key = work / "signing.pem"
    key.write_text(required("RELEASE_SIGNING_KEY"))
    cert = work / "recipient.pem"
    cert.write_text(required("PI_RECIPIENT_CERT"))
    settings = required("PI_SETTINGS")
    json.loads(settings)
    encrypted = subprocess.run(
        ["openssl", "cms", "-encrypt", "-binary", "-aes256", "-outform", "DER", str(cert)],
        input=settings.encode(), check=True, stdout=subprocess.PIPE).stdout
    manifest = json.dumps({
        "sequence": sequence, "revision": revision, "expires": int(time.time()) + 86400,
        "platform": "linux-armv7l", "device": "controller",
        "bundle": hashlib.sha256(bundle).hexdigest(),
        "settings": hashlib.sha256(encrypted).hexdigest(),
    }, sort_keys=True).encode()
    signature = subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key)],
                               input=manifest, check=True, stdout=subprocess.PIPE).stdout
    envelope = {"body": encode(manifest), "signature": encode(signature)}
    return {"envelope": envelope, "bundle": encode(bundle), "settings": encode(encrypted)}


def main():
    os.umask(0o077)
    component = sys.argv[1]
    release = Path(sys.argv[2])
    metadata = json.loads((release / "release.json").read_text())
    package = {"component": component, "release": metadata, "sequence": int(required("DEPLOY_SEQUENCE"))}
    package["registry"] = {"username": required("GITHUB_ACTOR"), "token": required("REGISTRY_TOKEN")}
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        if component == "controller":
            bundle = (release / "controller.tgz").read_bytes()
            if hashlib.sha256(bundle).hexdigest() != metadata["controller_sha256"]:
                raise ValueError("Controller checksum mismatch")
            package.update(controller_files(work, bundle, package["sequence"], metadata["revision"]))
        if component == "frontend":
            package["web_port"] = int(required("WEB_PORT"))
            package["dashboard_url"] = os.environ.get("DASHBOARD_URL", "")
        elif component in ("broker", "controller"):
            package["monitor"] = json.loads(required("BROKER_MONITOR"))
        elif component == "monitoring":
            package["settings"] = monitoring_settings(json.loads(required("MONITORING_SETTINGS")),
                                                      required("BROKER_PASSWORD_FILE"))
        if component == "broker":
            package["volumes"] = json.loads(required("BROKER_VOLUMES"))
            package["files"] = {filename: required(secret) for filename, secret in {
                "passwords": "BROKER_PASSWORD_FILE", "acl": "BROKER_ACL",
                "chain.pem": "BROKER_CERT", "key.pem": "BROKER_KEY"}.items()}
        key = work / "identity"
        key.write_text(required("DEPLOY_KEY").strip() + "\n")
        known = work / "known_hosts"
        known.write_text(required("VPS_KNOWN_HOSTS").strip() + "\n")
        host, user = required("VPS_HOST"), required("VPS_USER")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.:-]*", host) or not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
            raise ValueError("Invalid SSH destination")
        command = ["ssh", "-F", "/dev/null", "-T", "-i", str(key), "-l", user, "-o", "BatchMode=yes",
                   "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes",
                   "-o", "UserKnownHostsFile=" + str(known), "-o", "ConnectTimeout=12",
                   "--", host, "terrapi-deploy"]
        # A forced SSH command is the only supported server entry point.
        job = subprocess.run(command, input=json.dumps(package).encode(),
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=660)
        if job.returncode == 75:
            sys.exit("Release published. Pi acknowledgment is pending. Retry this run to check again.")
        if job.returncode:
            raise RuntimeError("Deployment did not verify. Check the private VPS deployment journal.")
    print("Deployment verified.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Tool errors can contain endpoints or credentials. Keep public CI output generic.
        sys.exit("Deployment failed (" + type(error).__name__ + "). See the private deployment journal.")
