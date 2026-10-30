#!/usr/bin/env bash
# Remote server: private URL intel collection + public HTTPS signed snapshot feed.
# This never approves threat intelligence, signs policy, or configures TLS for you.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
APPLY=0; ACCEPT=0; DISCLOSE=0; NONCOMMERCIAL=0; HOST=''; DEVICE=''; KEY=''; PUB=''
usage() {
  echo 'Usage: install-policy-server.sh --server-name policy.example.org --device-id edge-69 --api-key-file /private/google.key --public-key /private/public.pem --accept-openphish-terms --ack-url-disclosure --ack-noncommercial-use [--apply]' >&2
}
while (($#)); do
  case "$1" in
    --server-name) HOST="${2:?}"; shift 2;;
    --device-id) DEVICE="${2:?}"; shift 2;;
    --api-key-file) KEY="${2:?}"; shift 2;;
    --public-key) PUB="${2:?}"; shift 2;;
    --accept-openphish-terms) ACCEPT=1; shift;;
    --ack-url-disclosure) DISCLOSE=1; shift;;
    --ack-noncommercial-use) NONCOMMERCIAL=1; shift;;
    --apply) APPLY=1; shift;;
    --help|-h) usage; exit 0;;
    *) usage; exit 2;;
  esac
done
[[ "$DEVICE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || { usage; exit 2; }
[[ $ACCEPT == 1 && $DISCLOSE == 1 && $NONCOMMERCIAL == 1 ]] || { echo 'Explicit source terms and URL disclosure acknowledgements required' >&2; exit 2; }
[[ -f "$KEY" && ! -L "$KEY" && -f "$PUB" && ! -L "$PUB" ]] || { echo 'Key files must already exist and not be symlinks' >&2; exit 2; }
[[ -f "$ROOT/apps/policy-server/src/policy_server/intel.py" && -f "$ROOT/apps/policy-server/src/policy_server/__main__.py" ]] || { echo 'Run from a complete trusted checkout' >&2; exit 2; }
# Validate hostname and trust-anchor material before any system changes.
PYTHONPATH="$ROOT/apps/dns-agent/src" /usr/bin/python3 -B - "$HOST" <<'PY'
import sys
from dns_agent.policy import PolicyError, domain_name
try:
    domain_name(sys.argv[1])
except PolicyError:
    raise SystemExit('Invalid policy server DNS hostname')
PY
PYTHONPATH="$ROOT/apps/dns-agent/src:$ROOT/apps/policy-sync/src" /usr/bin/python3 -B -m aleph_policy_sync key-id --public-key "$PUB" >/dev/null || {
  echo 'Invalid trusted Ed25519 public key' >&2; exit 2;
}
echo "Remote install plan: host=$HOST device=$DEVICE code=/opt/aleph-policy-code state=/var/lib/aleph-policy-server feed=/srv/aleph-policy-feed/$DEVICE"
echo 'Requires an existing valid HTTPS NGINX server; adds ONLY an include-able location snippet.'
((APPLY)) || { echo 'Preview only; use --apply to provision.'; exit 0; }
((EUID == 0)) || { echo 'Run --apply as root (sudo).' >&2; exit 2; }
/usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" check remote --device-id "$DEVICE"
[[ $(stat -c '%u' "$KEY") == 0 && $(stat -c '%a' "$KEY") == 600 ]] || { echo 'Google API key input must be root-owned mode 0600' >&2; exit 2; }
/usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' || { echo 'Python >=3.11 required' >&2; exit 2; }
/usr/bin/python3 -c 'import cryptography' || { echo 'Install python3-cryptography first' >&2; exit 2; }
command -v nginx >/dev/null && command -v systemctl >/dev/null || { echo 'Install NGINX/systemd and configure TLS first' >&2; exit 2; }
for path in /opt/aleph-policy-code /var/lib/aleph-policy-server /etc/systemd/system/aleph-policy-refresh.service /etc/systemd/system/aleph-policy-refresh.timer /etc/nginx/snippets/aleph-policy-feed.conf; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing installation path; refuse overwrite: $path" >&2; exit 2; }
done
if [[ -n "$(find "$ROOT/apps/dns-agent/src" "$ROOT/apps/policy-sync/src" "$ROOT/apps/policy-server/src" -type l -print -quit)" ]]; then
  echo 'Symlinked source in application tree; refuse root install' >&2; exit 2;
fi
if ! id aleph-policy-server >/dev/null 2>&1; then
  useradd --system --user-group --no-create-home --home-dir /var/lib/aleph-policy-server --shell /usr/sbin/nologin aleph-policy-server
fi
install -d -o aleph-policy-server -g aleph-policy-server -m 0700 /var/lib/aleph-policy-server
install -o aleph-policy-server -g aleph-policy-server -m 0600 "$KEY" /var/lib/aleph-policy-server/google-api-key
# Runtime source only: no repository tests, old script copy, or development docs.
for app in dns-agent policy-sync policy-server; do
  install -d -o root -g root -m 0755 "/opt/aleph-policy-code/apps/$app"
  /usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" copy-source \
    "$ROOT/apps/$app/src" "/opt/aleph-policy-code/apps/$app/src"
done
chown -R root:root /opt/aleph-policy-code
find /opt/aleph-policy-code -type d -exec chmod 0755 {} +
find /opt/aleph-policy-code -type f -exec chmod 0644 {} +
install -d -o root -g root -m 0755 /etc/aleph-policy-sync/trust /srv/aleph-policy-feed "/srv/aleph-policy-feed/$DEVICE"
install -o root -g root -m 0644 "$PUB" /etc/aleph-policy-sync/trust/.incoming.pem
KEY_ID="$(PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src /usr/bin/python3 -B -m aleph_policy_sync key-id --public-key /etc/aleph-policy-sync/trust/.incoming.pem)"
[[ "$KEY_ID" =~ ^[0-9a-f]{64}$ ]] || exit 2
mv -f /etc/aleph-policy-sync/trust/.incoming.pem "/etc/aleph-policy-sync/trust/$KEY_ID.pem"
cat >/etc/systemd/system/aleph-policy-refresh.service <<'UNIT'
[Unit]
Description=ALEPH remote OpenPhish and Google Safe Browsing candidate dataset refresh
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
User=aleph-policy-server
Group=aleph-policy-server
UMask=0077
StateDirectory=aleph-policy-server
StateDirectoryMode=0700
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/policy-server/src:/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m policy_server refresh --state-dir /var/lib/aleph-policy-server --api-key-file /var/lib/aleph-policy-server/google-api-key --source openphish --limit 100 --accept-openphish-terms --ack-url-disclosure --ack-noncommercial-use
TimeoutStartSec=5min
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
RestrictSUIDSGID=yes
UNIT
cat >/etc/systemd/system/aleph-policy-refresh.timer <<'UNIT'
[Unit]
Description=Refresh remote phishing URL candidates from the non-commercial providers
[Timer]
OnBootSec=2min
OnUnitInactiveSec=12h
RandomizedDelaySec=5min
Unit=aleph-policy-refresh.service
[Install]
WantedBy=timers.target
UNIT
install -d -o root -g root -m 0755 /etc/nginx/snippets
cat >/etc/nginx/snippets/aleph-policy-feed.conf <<UNIT
# Include within an existing verified 'listen 443 ssl' server block for $HOST.
# Never include in a plaintext HTTP virtual host.
location = /v1/policies/$DEVICE/current.json {
    alias /srv/aleph-policy-feed/$DEVICE/current.json;
    etag off;
    default_type application/json;
    add_header Cache-Control "no-store" always;
    add_header X-Content-Type-Options "nosniff" always;
    limit_except GET { deny all; }
}
UNIT
chmod 0644 /etc/nginx/snippets/aleph-policy-feed.conf /etc/systemd/system/aleph-policy-refresh.service /etc/systemd/system/aleph-policy-refresh.timer
systemctl daemon-reload
systemctl enable --now aleph-policy-refresh.timer
printf 'Installed dataset-refresh timer; signer public key fingerprint: %s\n' "$KEY_ID"
echo "Manually include /etc/nginx/snippets/aleph-policy-feed.conf inside your trusted HTTPS/TLS vhost for $HOST and run nginx -t."
echo 'The release feed remains empty until an independently reviewed, signed policy is promoted.'
