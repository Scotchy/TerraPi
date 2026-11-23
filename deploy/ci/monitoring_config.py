"""Prepare monitoring credentials and broker permissions in the deploy runner."""
import base64
import hashlib
import hmac


SAMPLES = "terrapi/monitor/samples"
ACK = "terrapi/monitor/ack"
COLLECTOR = "terrapi-history"


class MonitoringConfigurationError(ValueError):
    """A configuration error whose message contains no private values."""


def acl_users(lines):
    users = {}
    user = None
    for index, line in enumerate(lines):
        parts = line.split(maxsplit=2)
        if len(parts) >= 2 and parts[0] == "user":
            user = line.split(maxsplit=1)[1].rstrip()
            users.setdefault(user, ([], set()))[0].append(index)
        elif user and len(parts) >= 2 and parts[0] == "topic":
            access, topic = parts[1:] if len(parts) == 3 else ("readwrite", parts[1])
            if access in ("read", "readwrite"):
                users[user][1].add(("read", topic))
            if access in ("write", "readwrite"):
                users[user][1].add(("write", topic))
    return users


def account(users, passwords, explicit, permissions, role):
    matches = [user for user, (_, allowed) in users.items() if permissions <= allowed]
    user = explicit or (matches[0] if len(matches) == 1 else "")
    if user not in users or user not in passwords:
        raise MonitoringConfigurationError(
            f"Cannot identify the {role} MQTT account. Set MONITORING_{role.upper()}_USER in production-vps.")
    return user


def configure(files, deploy_key, dashboard_user="", controller_user=""):
    lines = files["acl"].splitlines()
    users = acl_users(lines)
    passwords = {line.partition(":")[0] for line in files["passwords"].splitlines() if ":" in line}
    dashboard = account(users, passwords, dashboard_user,
                        {("read", "config/full"), ("write", "config/get")}, "dashboard")
    controller = account(users, passwords, controller_user,
                         {("write", "terrapi/deploy/controller/health")}, "controller")
    if dashboard == controller:
        raise MonitoringConfigurationError("The dashboard and controller MQTT accounts must be distinct.")
    if COLLECTOR in users or COLLECTOR in passwords:
        raise MonitoringConfigurationError("The broker configuration already uses the reserved terrapi-history account.")

    # Stable across deploys so an existing collector reconnects when the broker restarts.
    key = deploy_key.strip().encode()
    password = hmac.digest(key, b"TerraPi collector password v1", "sha256").hex()
    salt = hmac.digest(key, b"TerraPi collector salt v1", "sha256")[:12]
    iterations = 101
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, iterations)
    salt64, digest64 = (base64.b64encode(value).decode("ascii") for value in (salt, digest))
    passwords_text = files["passwords"].rstrip("\r\n") + f"\n{COLLECTOR}:$7${iterations}${salt64}${digest64}\n"

    headers, allowed = users[controller]
    additions = [f"topic {access} {topic}" for access, topic in (("write", SAMPLES), ("read", ACK))
                 if (access, topic) not in allowed]
    at = headers[-1] + 1
    lines[at:at] = additions
    lines.extend(("", f"user {COLLECTOR}", f"topic read {SAMPLES}", f"topic write {ACK}"))
    return (dict(files, passwords=passwords_text, acl="\n".join(lines) + "\n"),
            {"mqtt_user": COLLECTOR, "mqtt_password": password, "dashboard_user": dashboard})
