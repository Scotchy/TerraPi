# TerraPi deployments

**Build and test** runs on pull requests and pushes to `main`. Pull requests use disposable credentials. A successful main build publishes the two tested container images to GHCR by digest and saves the controller bundle and release metadata as the `terrapi-release` artifact for 90 days. **Deploy** takes a component and a successful main build run ID. Choose an older retained build to roll back. Production jobs serialize across all three components. Record the last verified build ID when deploying.

## Private production configuration

Create GitHub Actions environments named `production-vps` and `production-pi`. Restrict each environment to the protected `main` branch. Limit who can approve changes to workflows and deployment scripts. Put **every deployment-specific value in Environment Secrets**, including hostnames, ports and account names. Public workflow names, run IDs, artifact names and source files contain only generic identifiers. The browser uses its current origin and the fixed path `/terra/mqtt`. Build images, public artifacts and MQTT wake messages contain no runtime credentials.

Enter real values through GitHub’s secret form or private files outside this checkout. Disable runner debug logging for production jobs. The GitHub package token is short-lived and the VPS uses a temporary registry login. Grant the repository’s Actions token access to its GHCR packages.

| Environment secrets | Contents |
| --- | --- |
| Both environments — `VPS_HOST`, `VPS_USER`, `DEPLOY_KEY`, `VPS_KNOWN_HOSTS` | SSH deployment destination, restricted private key and independently verified host key entry. |
| Both — `BROKER_MONITOR` | JSON object containing `host`, numeric `native_port` and `ws_port`, and the release publisher’s `username` and `password`. The hostname must match the TLS certificate. |
| VPS — `WEB_PORT` | Free loopback port for containerized nginx. |
| VPS — `DASHBOARD_URL` | Full public HTTPS dashboard URL. Omit for the first side-by-side staging, then set after ingress cutover to verify the public asset set matches the candidate. |
| VPS — `BROKER_VOLUMES` | JSON object with `data` and `logs` naming the two existing external Docker volumes. |
| VPS — `BROKER_CERT`, `BROKER_KEY` | Broker’s PEM full chain and matching unencrypted PEM server key. Redeploy the broker when renewed. |
| VPS — `BROKER_PASSWORD_FILE`, `BROKER_ACL` | Mosquitto password-file hashes and the complete topic ACL. Generate the password file interactively with `mosquitto_passwd` in a private directory. Use [acl.example](vps/acl.example) as the role template. |
| Pi — `PI_SETTINGS` | JSON object containing `host`, numeric `port`, `username` and `password` for the controller. The managed controller validates TLS using the system trust store or the CA path in its live YAML. Use a system-trusted CA for the updater and monitor. |
| Pi — `RELEASE_SIGNING_KEY`, `PI_RECIPIENT_CERT` | RSA private signing key in PEM format and the Pi’s public RSA encryption certificate in PEM format. The private device key stays on the Pi. |

Use separate identities for the controller, browser, updater and release publisher. Populate only the designated environments. For credential rotation, introduce a second authorized broker identity, publish the new controller settings, verify its acknowledgment and then retire the old identity. Keep rollback credentials valid through the release window. Bootstrap identity rotation for the updater uses its private configuration on the device.

## Prepare the VPS once

1. Install Docker and the Compose plugin. Reserve the external network name `terrapi-app` and Compose project `terrapi` for this application. Save the original nginx route, broker image, port mappings and restart procedure. Back up the broker's configuration, password database, certificates and actual data and log volumes consistently. Test restoration with separate copies. Rehearse on unused ports with those copies.
2. Install `deploy/vps/apply.py` as root-owned executable `/usr/local/lib/terrapi-vps/apply.py`. Install `frontend.yaml`, `broker.yaml` and `mosquitto.conf` beside it, root-owned. In that directory create a root-owned `image-namespace` file holding `ghcr.io/<lowercase-owner>/<lowercase-repository>`, and `allowed-volumes.json` matching the private volume secret. Only the operator can change these allowlists and helpers.
3. Create a dedicated SSH account without Docker group membership. Give its deployment public key the authorized-keys options `restrict,command="sudo -n /usr/local/lib/terrapi-vps/apply.py"`. Use a sudoers rule scoped to that executable with **no arguments**. Example rule for a dedicated account named `terrapi-deploy`: `terrapi-deploy ALL=(root) NOPASSWD: /usr/local/lib/terrapi-vps/apply.py ""`. Lock down the account to key authentication.
4. Deploy **frontend** and check the loopback URL under `/terra/`. The first frontend can be staged beside the live site. During broker handoff, release its two old port bindings by stopping only the existing TerraPi broker. Deploy **broker** using the existing volumes and ports. The managed native listener requires TLS, even on 1883. A Pi previously using plaintext needs to switch in the same window.
5. Have the shared HTTPS ingress proxy the entire `/terra/` prefix, preserving the path, to the frontend loopback port. Forward HTTP/1.1 WebSocket Upgrade and Connection headers. Redirect HTTP to HTTPS before users sign in. Validate and reload the shared configuration, then exercise the dashboard route, its assets, WebSocket login and fresh sensor data from outside. Keep the prior ingress route and container until the new deployment is verified.

The internal Docker WebSocket listener is reachable only on the application network. The separately published TLS WebSocket listener supports existing clients. The broker release checks authenticated TLS connections over both transports. The frontend release checks HTML and its current JS and CSS, and retains old hashed assets for open browser tabs. Docker changes use a service-specific Compose command. On the first migration, recovery uses the saved legacy container and state. After the first managed release, a failed health check reapplies the previous service definition. Restoring broker data across incompatible formats requires a compatible backup.

## Pair the Pi once

Prepare a trusted LAN maintenance session. Keep the running manual controller, its original config and a way to restart it until the managed baseline is verified. The supported target is a 32-bit ARMv7 Pi with Python 3.9, systemd, OpenSSL, venv support and working GPIO access through the `gpio` group. Install the dependencies in [requirements-pi.txt](../backend/requirements-pi.txt) where the service account’s system Python can import them. The updater uses the system Paho installation independently. Check GPIO device permissions and the configured timezone. Keep signing and bootstrap files outside Git.

1. Generate an RSA signing key outside the checkout, store it in `RELEASE_SIGNING_KEY`, and export its public key as `signing.pub`. Generate the device encryption key `recipient.key` and a matching self-signed RSA certificate `recipient.pem` on the Pi. Store only that certificate in `PI_RECIPIENT_CERT`. Example commands in private directories with `umask 077`:

   ```sh
   openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out signing.key
   openssl pkey -in signing.key -pubout -out signing.pub
   # On the Pi
   openssl req -x509 -newkey rsa:3072 -nodes -days 1825 -subj /CN=controller -keyout recipient.key -out recipient.pem
   ```
2. In a private directory on the Pi, place `signing.pub`, `recipient.key`, `recipient.pem`, and `settings.json` matching the initial private `PI_SETTINGS`. Add `updater.json` with the release directory's HTTPS `origin` (ending in `/terra/releases`), broker `host`, numeric native `port` and dedicated updater `username` and `password`. Optional `health_timeout` is in seconds and should cover several sensor reporting intervals. Use a root-only directory and file mode 0600 for secrets.
3. Run `sudo /usr/bin/python3 deploy/pi/bootstrap.py /path/to/working/backend /path/to/live/config.yaml /path/to/private-pairing`. It prepares the last working code as release 0, copies live modes and schedules, enables TLS in the managed copy, and installs the services without starting them. Pause dashboard edits during handoff and capture the intended manual mode. Dependencies from a personal Python user site need to be made available to the service account before handoff.
4. During the coordinated broker cutover, stop the manual controller, start `terrapi-controller.service` and verify fresh readings, mode and relay state. Once verified, enable it at boot and enable and start `terrapi-updater.service`. Only one process should own GPIO. The first supervised rollback returns to release 0. The original manual startup remains the fallback if the managed baseline itself fails.

## Controller release and recovery

The production workflow signs a manifest covering the release, sequence, target, expiry and SHA-256 hashes. It encrypts the controller's settings to that Pi, then sends only encrypted settings, signed metadata and source to the VPS release directory. The VPS publishes a fixed MQTT wake message. The Pi also checks the same HTTPS origin on startup, reconnect and every minute. It rejects tampered data, unexpected archive paths, incompatible targets and stale requests.

Before switching it checks credentials, creates a release-specific environment using the Pi’s installed native stack and verifies the exact direct dependencies. When a pin changes, an unprivileged build account installs available binary wheels into the candidate environment before activation. Missing ARM wheels or native OS libraries require provisioning during maintenance. The running environment stays available during staging. Live YAML stays outside release directories. Two fresh control-cycle reports with a finite temperature and a configured mode are required from the candidate before success. In manual operation the current selection lives in memory. Supervise the restart and reselect the intended mode, including after rollback. A failed activation switches back locally. A journal records the previous release before activation so recovery can run after power loss even with the network down.

CI waits up to five minutes for a matching Pi acknowledgment. A timeout means the result is unconfirmed. A disconnected Pi can still apply that request within its 24-hour validity. Rerun the same workflow run to check the same request, or submit a new deployment to supersede it. To roll back, choose the earlier build run in a new **Deploy** run. Reusing a previous artifact creates a new signed deployment number. Retain older successful releases and compatible broker backups for the rollback period. Review free space on the VPS and Pi before repeated releases.

For local verification, run the frontend tests and build, `python -m unittest discover -s deploy/tests` in an environment with Paho MQTT 1.6.1 and PyYAML, and the Docker smoke test commands in [.github/workflows/ci.yml](../.github/workflows/ci.yml). All smoke-test credentials and certificates are disposable.
