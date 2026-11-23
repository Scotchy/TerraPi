import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tarfile
import tempfile
import time
import unittest

import yaml
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


updater = load("updater", BASE / "pi/updater.py")
dispatch = load("dispatch", BASE / "ci/dispatch.py")
vps = load("vps", BASE / "vps/apply.py")


class VPSDeployment(unittest.TestCase):
    def test_registry_auth_is_private_and_discarded_after_a_failed_pull(self):
        job = {"component": "frontend", "registry": {"username": "runner", "token": "fixture"}}
        config_files = []

        def fail_pull(_job):
            config = Path(os.environ["DOCKER_CONFIG"]) / "config.json"
            config_files.append(config)
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            auth = json.loads(config.read_bytes())["auths"]
            self.assertEqual(list(auth), ["ghcr.io"])
            self.assertEqual(base64.b64decode(auth["ghcr.io"]["auth"]), b"runner:fixture")
            raise RuntimeError("simulated pull failure")

        self.addCleanup(os.umask, os.umask(0o077))
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ), \
             patch.object(vps, "ROOT", Path(root)), patch.object(vps.sys, "stdin") as stdin, \
             patch.object(vps.subprocess, "run") as network, patch.object(vps, "docker") as docker, \
             patch.object(vps, "frontend", side_effect=fail_pull):
            stdin.buffer = io.BytesIO(json.dumps(job).encode())
            network.return_value.returncode = 0
            with self.assertRaisesRegex(RuntimeError, "simulated pull failure"):
                vps.main()
            docker.assert_not_called()
        self.assertFalse(config_files[0].parent.exists())


class PiDeployment(unittest.TestCase):
    def test_signed_bundle_and_encrypted_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            key, cert, pub = (work / name for name in ("test.key", "test.pem", "test.pub"))
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-subj", "/CN=fixture", "-keyout", key, "-out", cert], check=True,
                           stderr=subprocess.DEVNULL)
            subprocess.run(["openssl", "pkey", "-in", key, "-pubout", "-out", pub], check=True)
            subprocess.run(["bash", BASE / "ci/package.sh", work], cwd=BASE.parent, check=True)
            bundle = (work / "controller.tgz").read_bytes()
            with patch.dict(os.environ, RELEASE_SIGNING_KEY=key.read_text(), PI_RECIPIENT_CERT=cert.read_text(),
                            PI_SETTINGS='{"password":"synthetic-only"}'):
                files = dispatch.controller_files(work, bundle, 7, "0" * 40)
            with patch.object(updater.platform, "machine", return_value="armv7l"):
                manifest = updater.verify(files["envelope"], pub)
            self.assertEqual(manifest["bundle"], hashlib.sha256(bundle).hexdigest())
            self.assertNotIn("synthetic-only", json.dumps(files))
            encrypted = updater.base64.b64decode(files["settings"])
            clear = updater.run("openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                                "-inkey", key, "-recip", cert, data=encrypted)
            self.assertEqual(json.loads(clear)["password"], "synthetic-only")
            with self.assertRaises(subprocess.CalledProcessError):
                updater.verify(dict(files["envelope"], body="e30="), pub)
            dest = work / "extracted"
            dest.mkdir()
            updater.unpack(bundle, dest)
            self.assertTrue((dest / "run.py").is_file())
            self.assertFalse((dest / "conf").exists())

    def test_bundle_rejects_unexpected_member(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            archive.addfile(tarfile.TarInfo("config.yaml"), io.BytesIO())
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            updater.unpack(raw.getvalue(), Path(tmp))

    def test_rollout_retries_and_recovers_after_power_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            releases = root / "releases"
            rollback = releases / "0"
            rollback.mkdir(parents=True)
            (root / "current").symlink_to(rollback)
            desired = {"sequence": 1, "expires": time.time() + 60}
            with patch.object(updater, "ROOT", root), patch.object(updater, "fetch", return_value=b"{}"), \
                 patch.object(updater, "verify", return_value=desired), patch.object(updater, "run") as run, \
                 patch.object(updater, "prepare", side_effect=lambda a, b, path: path.mkdir()) as prepare:
                config = {"origin": "https://example.invalid"}
                self.assertEqual(updater.reconcile(config, lambda _: False)["result"], "failed")
                self.assertEqual((root / "current").resolve(), rollback)
                updater.reconcile(config, lambda _: True)
                self.assertEqual(prepare.call_count, 1)
                desired["sequence"] = 2
                self.assertEqual(updater.reconcile(config, lambda _: True)["result"], "healthy")
                self.assertEqual((root / "current").resolve(), releases / "2")
                record = updater.save(3, "activating", previous=str(releases / "2"))
                updater.select(rollback)
                updater.recover(record)
                self.assertEqual((root / "current").resolve(), releases / "2")
                run.assert_called_with("systemctl", "restart", updater.SERVICE)

    def test_terminal_and_bounded_preflight_failures_keep_old_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "releases/0"
            old.mkdir(parents=True)
            (root / "current").symlink_to(old)
            desired = {"sequence": 1, "expires": time.time() + 60}
            with patch.object(updater, "ROOT", root), patch.object(updater, "fetch", return_value=b"{}"), \
                 patch.object(updater, "verify", return_value=desired), patch.object(updater, "prepare") as prepare:
                prepare.side_effect = ValueError("Invalid schedule")
                def reconcile():
                    return updater.reconcile({"origin": "https://example.invalid"}, lambda _: self.fail("Activated"))

                self.assertEqual(reconcile()["result"], "failed")
                self.assertEqual(reconcile()["sequence"], 1)
                self.assertEqual(prepare.call_count, 1)
                desired["sequence"] = 2
                prepare.side_effect = ConnectionError("Temporary outage")
                self.assertEqual([reconcile()["result"] for _ in range(4)], ["retrying", "retrying", "failed", "failed"])
                self.assertEqual(prepare.call_count, 4)
                self.assertEqual((root / "current").resolve(), old)

    def test_activation_syncs_journal_switch_and_result_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "releases/0"
            old.mkdir(parents=True)
            (root / "current").symlink_to(old)
            boundaries = []

            def inspect(directory):
                self.assertEqual(directory, root)
                boundaries.append((updater.state()["result"], (root / "current").resolve().name))

            with patch.object(updater, "ROOT", root), patch.object(updater, "fetch", return_value=b"{}"), \
                 patch.object(updater, "verify", return_value={"sequence": 1, "expires": time.time() + 60}), \
                 patch.object(updater, "prepare", side_effect=lambda a, b, path: path.mkdir()), \
                 patch.object(updater, "sync_directory", side_effect=inspect), patch.object(updater, "run"):
                updater.reconcile({"origin": "https://example.invalid"}, lambda _: True)
                self.assertEqual(boundaries, [("activating", "0"), ("activating", "1"), ("healthy", "1")])

    def test_candidate_checks_live_schema_and_uses_service_ca_before_activation(self):
        checker = load("checker", BASE / "pi/check_candidate.py")
        with tempfile.TemporaryDirectory() as tmp, patch.object(sys, "path", list(sys.path)), patch.dict(sys.modules):
            release = Path(tmp)
            package = release / "terrapi"
            package.mkdir()
            shutil.copy(BASE.parent / "backend/terrapi/config_schema.py", package)
            settings = {"host": "example.invalid", "port": 1883, "username": "fixture", "password": "fixture"}
            (release / "settings.json").write_text(json.dumps(settings))
            config = yaml.safe_load((BASE.parent / "backend/conf/config.yaml").read_bytes())
            config["mqtt"]["ca_certs"] = "local-ca.pem"
            path = release / "live.yaml"
            path.write_text(yaml.safe_dump(config))
            with patch.object(checker.mqtt, "Client") as factory, patch.object(checker.ssl, "create_default_context") as context:
                client = factory.return_value
                client.loop_start.side_effect = lambda: client.on_connect(client, None, {}, 0)
                checker.check(release, path)
                context.assert_called_with(cafile=release / "local-ca.pem")
                client.username_pw_set.assert_called_once_with("fixture", "fixture")
                client.loop_start.side_effect = lambda: client.on_connect(client, None, {}, 5)
                with self.assertRaises(ValueError):
                    checker.check(release, path)
                config["planning"]["active"] = "yes"
                path.write_text(yaml.safe_dump(config))
                with self.assertRaises(ValueError):
                    checker.check(release, path)
                self.assertEqual(client.connect.call_count, 2)
