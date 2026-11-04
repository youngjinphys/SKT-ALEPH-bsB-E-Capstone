#!/usr/bin/env bash
# Opt-in, capability-limited OpenPhish + GSB GUI refresh channel.
# Does not grant the web account access to the Google API key or DNS publisher.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
APPLY=0
usage(){ echo "Usage: $0 [--apply]  # run on the policy server after both base installers" >&2; }
while (($#));do
  case "$1" in
    --apply) APPLY=1;shift;;
    --help|-h) usage;exit 0;;
    *) usage;exit 2;;
  esac
done
echo "Collector control plan: /run/aleph-intel-refresh.sock (Unix only, mode 0660)"
echo "Permissions: console account may request fixed OpenPhish + GSB refresh; collector alone reads the API key."
echo "Policy signing, publication, DNS apply and arbitrary URL collection stay outside the GUI."
((APPLY)) || { echo "Preview only; rerun with --apply after inspecting the units."; exit 0; }
((EUID==0)) || { echo "Installation requires root" >&2;exit 2; }
command -v systemctl >/dev/null || { echo "systemd required" >&2;exit 2; }
for user in aleph-policy-server aleph-ops-console;do
  id "$user" >/dev/null 2>&1 || { echo "Install base policy server and operations console first: $user" >&2; exit 2; }
done
[[ -f /etc/systemd/system/aleph-ops-console.service &&
   -f /etc/systemd/system/aleph-policy-refresh.service &&
   -f /var/lib/aleph-policy-server/google-api-key &&
   -d /var/lib/aleph-ops-console ]] || { echo "Required policy and console services are missing" >&2; exit 2; }
[[ $(stat -c '%U:%a' /var/lib/aleph-policy-server/google-api-key) == 'aleph-policy-server:600' ]] ||
  { echo "Collector API key must remain owned by aleph-policy-server mode 0600" >&2;exit 2; }
/usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" verify-runtime \
  "$ROOT" /opt/aleph-policy-code --role policy ||
  { echo "Installed runtime does not match this checkout: run approved code upgrade first" >&2;exit 2; }
for path in /etc/systemd/system/aleph-intel-refresh.socket \
            /etc/systemd/system/aleph-intel-refresh.service \
            /etc/systemd/system/aleph-ops-console.service.d/aleph-intel-refresh.conf;do
  [[ ! -e "$path" && ! -L "$path" ]] || {
    echo "Existing bridge component; refuse to overwrite: $path" >&2;exit 2; }
done
install -d -o root -g root -m 0755 /etc/systemd/system/aleph-ops-console.service.d
cat >/etc/systemd/system/aleph-intel-refresh.socket <<'UNIT'
[Unit]
Description=ALEPH non-root signed-policy evidence refresh request socket
[Socket]
ListenStream=/run/aleph-intel-refresh.sock
SocketUser=aleph-policy-server
SocketGroup=aleph-ops-console
SocketMode=0660
RemoveOnStop=yes
Service=aleph-intel-refresh.service
[Install]
WantedBy=sockets.target
UNIT
cat >/etc/systemd/system/aleph-intel-refresh.service <<'UNIT'
[Unit]
Description=ALEPH OpenPhish and GSB restricted local refresh worker
Requires=aleph-intel-refresh.socket
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=aleph-policy-server
Group=aleph-policy-server
UMask=0077
StateDirectory=aleph-policy-server
StateDirectoryMode=0700
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/policy-server/src:/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m policy_server.refresh_bridge serve --state-dir /var/lib/aleph-policy-server --api-key-file /var/lib/aleph-policy-server/google-api-key --console-user aleph-ops-console
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/aleph-policy-server
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
RestrictSUIDSGID=yes
CapabilityBoundingSet=
[Install]
WantedBy=multi-user.target
UNIT
cat >/etc/systemd/system/aleph-ops-console.service.d/aleph-intel-refresh.conf <<'UNIT'
[Service]
# The only capability delegated to the GUI is access to one local Unix socket.
Environment=ALEPH_INTEL_REFRESH_SOCKET=/run/aleph-intel-refresh.sock
UNIT
chmod 0644 /etc/systemd/system/aleph-intel-refresh.{service,socket} \
            /etc/systemd/system/aleph-ops-console.service.d/aleph-intel-refresh.conf
systemctl daemon-reload
systemctl enable --now aleph-intel-refresh.socket
systemctl try-restart aleph-ops-console.service
echo "Collector socket enabled. Review systemctl status aleph-intel-refresh.socket."
echo "Confirm GUI /api/intel status, then request a preview; existing reviews are never automatically overwritten."
