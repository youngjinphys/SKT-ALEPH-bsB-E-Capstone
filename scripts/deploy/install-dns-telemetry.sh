#!/usr/bin/env bash
# Opt-in DNS-side telemetry; does not modify resolver, DHCP or policy sync.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
APPLY=0; DEVICE=''; IP=''; URL=''; PRIV=''; PUB=''; CA=''; PROBE_UPSTREAM=''; METRICS_INTERFACE=''; QUALITY_PROBES=0; CACHE_METRICS=''
usage(){ echo "Usage: $0 --device-id edge-69 --listen-ip 192.168.7.69 --report-url https://ops.example.org/v1/nodes/report --private-key /secure/status.pem --public-key /secure/status.pub [--cache-metrics] [--probe-upstream 9.9.9.9] [--metrics-interface eth0] [--quality-probes] [--ca-file /secure/root-ca.pem] [--apply]" >&2; }
while (($#)); do
 case "$1" in
  --device-id) DEVICE="$2"; shift 2;;
  --listen-ip) IP="$2"; shift 2;;
  --report-url) URL="$2"; shift 2;;
  --private-key) PRIV="$2"; shift 2;;
  --public-key) PUB="$2"; shift 2;;
  --probe-upstream) PROBE_UPSTREAM="$2"; shift 2;;
  --metrics-interface) METRICS_INTERFACE="$2"; shift 2;;
  --quality-probes) QUALITY_PROBES=1; shift;;
  --cache-metrics) CACHE_METRICS=" --cache-metrics"; shift;;
  --ca-file) CA="$2"; shift 2;;
  --apply) APPLY=1; shift;;
  --help|-h) usage; exit 0;;
  *) usage; exit 2;;
 esac
done
[[ "$DEVICE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || { usage; exit 2; }
[[ "$URL" =~ ^https://[a-zA-Z0-9.-]+(:[0-9]{1,5})?/v1/nodes/report$ ]] || { echo "status URL must be fixed HTTPS report endpoint" >&2; exit 2; }
[[ -f "$PRIV" && ! -L "$PRIV" && -f "$PUB" && ! -L "$PUB" ]] || { echo "existing non-symlink device private and public key required" >&2; exit 2; }
if [[ -n "$CA" ]];then
 [[ -f "$CA" && ! -L "$CA" ]] || { echo "invalid custom CA file" >&2; exit 2; }
fi
export PYTHONPATH="$ROOT/apps/dns-agent/src:$ROOT/apps/policy-sync/src"
python3 -B - "$DEVICE" "$IP" "$URL" "$PRIV" "$PUB" "$PROBE_UPSTREAM" "$METRICS_INTERFACE" <<'PY'
import sys
from urllib.parse import urlsplit
from pathlib import Path
from aleph_policy_sync.telemetry import private_ipv4, probe_upstream_ipv4
from aleph_policy_sync.snapshot import device_id, load_private_key, load_public_key, public_key_id
d,ip,url,priv,pub,upstream,interface=sys.argv[1:]
from aleph_policy_sync.system_metrics import interface_name
interface_name(interface or None)
device_id(d); private_ipv4(ip)
probe_upstream_ipv4(upstream or None, ip)
p=urlsplit(url)
if p.scheme!="https" or not p.hostname or p.path!="/v1/nodes/report" or p.query or p.fragment or p.username or p.password:
    raise SystemExit("invalid report URL")
key=load_private_key(Path(priv))
public=load_public_key(Path(pub))
if public_key_id(public) != public_key_id(key.public_key()):
    raise SystemExit("device private and public key mismatch")
print("Device status key ID:",public_key_id(public))
PY
echo "Status plan: device=$DEVICE dns=$IP:53 report=$URL positive-reference=${PROBE_UPSTREAM:-UNCONFIGURED}"
if [[ -z "$PROBE_UPSTREAM" ]]; then
  echo "CAUTION: local NXDOMAIN probes will remain UNCORROBORATED until --probe-upstream is configured."
fi
echo "Separate telemetry key only. No policy signer keys or inbound DNS API."
((APPLY)) || { echo "Preview only; --apply creates separate systemd telemetry services."; exit 0; }
((EUID == 0)) || { echo "--apply requires root" >&2; exit 2; }
command -v systemctl >/dev/null || { echo "systemd required" >&2; exit 2; }
[[ -f /opt/aleph-policy-code/apps/policy-sync/src/aleph_policy_sync/telemetry.py ]] || { echo "Deploy reviewed current policy-sync source to DNS node first" >&2; exit 2; }
[[ -f /opt/aleph-policy-code/infra/edge/system_dns.py ]] || { echo "Managed DNS admin missing" >&2; exit 2; }
/usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" verify-runtime "$ROOT" /opt/aleph-policy-code --role dns ||
  { echo "Deployed DNS code differs from this checkout; run the code-only upgrade before enabling telemetry." >&2; exit 2; }
for target in /etc/aleph-ops/status.pem /etc/aleph-ops/trust /var/lib/aleph-ops-root /var/lib/aleph-ops-outbox /etc/systemd/system/aleph-ops-collect.service /etc/systemd/system/aleph-ops-send.service /etc/systemd/system/aleph-ops-collect.timer /etc/systemd/system/aleph-ops-send.timer; do
 [[ ! -e "$target" && ! -L "$target" ]] || { echo "Existing status installation; refuse overwrite: $target" >&2; exit 2; }
done
[[ $(stat -c '%u:%a' "$PRIV") == "0:600" ]] || { echo "Device status private key must be root-owned 0600" >&2; exit 2; }
if ! id aleph-ops-sender >/dev/null 2>&1;then
 useradd --system --user-group --no-create-home --home-dir /var/lib/aleph-ops-outbox --shell /usr/sbin/nologin aleph-ops-sender
fi
GID="$(id -g aleph-ops-sender)"
# aleph-ops-sender must traverse this directory to read the public trust key
# and optional report CA. The device private key file remains root-only 0600.
install -d -o root -g root -m 0755 /etc/aleph-ops
install -o root -g root -m 0600 "$PRIV" /etc/aleph-ops/status.pem
install -d -o root -g root -m 0755 /etc/aleph-ops/trust
KEY_ID="$(PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src /usr/bin/python3 -B -m aleph_policy_sync key-id --public-key "$PUB")"
install -o root -g root -m 0644 "$PUB" "/etc/aleph-ops/trust/$KEY_ID.pem"
install -d -o root -g root -m 0700 /var/lib/aleph-ops-root
install -d -o root -g "$GID" -m 0750 /var/lib/aleph-ops-outbox
if [[ -n "$CA" ]];then
 install -o root -g root -m 0644 "$CA" /etc/aleph-ops/report-ca.pem
fi
CA_ARG=''
[[ -z "$CA" ]] || CA_ARG=' --ca-file /etc/aleph-ops/report-ca.pem'
METRICS_ARG=''
[[ -z "$METRICS_INTERFACE" ]] || METRICS_ARG=" --metrics-interface $METRICS_INTERFACE"
((QUALITY_PROBES == 0)) || METRICS_ARG+=" --quality-probes"
PROBE_ARG=''
[[ -z "$PROBE_UPSTREAM" ]] || PROBE_ARG=" --probe-upstream $PROBE_UPSTREAM"
cat >/etc/systemd/system/aleph-ops-collect.service <<UNIT
[Unit]
Description=ALEPH root-only local DNS policy attestation
After=aleph-dns.service
[Service]
Type=oneshot
User=root
UMask=0077
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m aleph_policy_sync.telemetry collect --device-id $DEVICE --listen-ip $IP$METRICS_ARG$PROBE_ARG$CACHE_METRICS --private-key /etc/aleph-ops/status.pem --state-dir /var/lib/aleph-ops-root --outbox-dir /var/lib/aleph-ops-outbox --sender-group aleph-ops-sender
TimeoutStartSec=45s
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/aleph-ops-root /var/lib/aleph-ops-outbox
UNIT
cat >/etc/systemd/system/aleph-ops-send.service <<UNIT
[Unit]
Description=ALEPH unprivileged HTTPS DNS status sender
After=network-online.target
Wants=network-online.target
ConditionPathExists=/var/lib/aleph-ops-outbox/report.json
[Service]
Type=oneshot
User=aleph-ops-sender
Group=aleph-ops-sender
UMask=0077
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m aleph_policy_sync.telemetry send --url $URL --device-id $DEVICE --key-id $KEY_ID --trust-dir /etc/aleph-ops/trust --report-file /var/lib/aleph-ops-outbox/report.json$CA_ARG
TimeoutStartSec=20s
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
RestrictSUIDSGID=yes
UNIT
cat >/etc/systemd/system/aleph-ops-collect.timer <<'UNIT'
[Unit]
Description=Periodically check actual local ALEPH DNS policy
[Timer]
OnBootSec=20s
OnUnitActiveSec=60s
RandomizedDelaySec=5s
Unit=aleph-ops-collect.service
[Install]
WantedBy=timers.target
UNIT
cat >/etc/systemd/system/aleph-ops-send.timer <<'UNIT'
[Unit]
Description=Report signed ALEPH DNS health over HTTPS
[Timer]
OnBootSec=45s
OnUnitActiveSec=60s
RandomizedDelaySec=5s
Unit=aleph-ops-send.service
[Install]
WantedBy=timers.target
UNIT
chmod 0644 /etc/systemd/system/aleph-ops-{collect,send}.{service,timer}
systemctl daemon-reload
systemctl enable --now aleph-ops-collect.timer aleph-ops-send.timer
printf "Telemetry installed, pin this device public key on console (ID): %s\n" "$KEY_ID"
echo "This install does not modify the resolver or enable remote DNS administration."
