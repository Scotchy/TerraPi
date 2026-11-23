#!/usr/bin/env bash
# Uses the separately approved VPS admin identity to maintain the fixed deploy entry point.
set -euo pipefail
umask 077

operation=$1
[[ "$operation" == check || "$operation" == install ]]
for name in VPS_HOST VPS_KNOWN_HOSTS VPS_ADMIN_USER VPS_ADMIN_KEY; do
    if [[ -z ${!name:-} ]]; then
        echo "Missing production-vps-provisioning secret: $name" >&2
        exit 1
    fi
done
if [[ ! $VPS_HOST =~ ^[a-zA-Z0-9][a-zA-Z0-9.:-]*$ || ! $VPS_ADMIN_USER =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo 'Invalid VPS provisioning SSH destination.' >&2
    exit 1
fi

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
printf '%s\n' "$VPS_ADMIN_KEY" > "$scratch/identity"
printf '%s\n' "$VPS_KNOWN_HOSTS" > "$scratch/known_hosts"
ssh_options=(-F /dev/null -T -i "$scratch/identity" -l "$VPS_ADMIN_USER"
    -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes
    -o "UserKnownHostsFile=$scratch/known_hosts" -o ConnectTimeout=12)

remote='sudo -n /bin/bash -c '\''
set -euo pipefail
umask 077
tools=/usr/local/lib/terrapi-vps
state=/var/lib/terrapi-deploy
test -x "$tools/apply.py"
test -f "$tools/image-namespace"
test -f "$tools/allowed-volumes.json"
test -d "$state"

if [[ "$1" == check ]]; then
    if ! test -r "$tools/monitoring.yaml" || ! grep -q "^def monitoring(" "$tools/apply.py"; then
        echo "The installed VPS helper is missing monitoring support."
        exit 3
    fi
    echo "The installed VPS helper supports monitoring."
    exit 0
fi

exec 9>>"$state/deploy.lock"
flock -x 9
stage=$(mktemp -d "$tools/.incoming.XXXXXXXX")
trap "rm -rf -- \"\$stage\"" EXIT
tar --no-same-owner --no-same-permissions -xf - -C "$stage" -- apply.py monitoring.yaml
test -s "$stage/monitoring.yaml"
python3 -m py_compile "$stage/apply.py"
chmod 644 "$stage/monitoring.yaml"
chmod 755 "$stage/apply.py"
mv -fT "$stage/monitoring.yaml" "$tools/monitoring.yaml"
mv -fT "$stage/apply.py" "$tools/apply.py"
echo "Installed the VPS deploy helper and monitoring Compose file."
'\'' provision-vps'

status=0
if [[ "$operation" == check ]]; then
    ssh "${ssh_options[@]}" -- "$VPS_HOST" "$remote check" 2>/dev/null || status=$?
else
    tar -cf - -C deploy/vps apply.py monitoring.yaml |
        ssh "${ssh_options[@]}" -- "$VPS_HOST" "$remote install" 2>/dev/null || status=$?
fi
case $status in
    0|3) ;;
    255) echo 'Could not connect to the VPS with the provisioning SSH identity and pinned host key.' >&2 ;;
    *) echo 'The VPS provisioning command failed. Check non-interactive sudo and the existing TerraPi installation.' >&2 ;;
esac
exit "$status"
