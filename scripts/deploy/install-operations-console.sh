#!/usr/bin/env bash
# Opt-in remote policy-side operations UI. Root installs systemd + NGINX snippet;
# it does not alter an existing TLS vhost, import policy data or start DNS control.
set -euo pipefail
umask 077
APPLY=0; ORIGIN=''; PORT=8765; DEVICE=''; USER=aleph-ops-console; ADMIN_CIDR='127.0.0.1/32'
usage(){ echo "Usage: $0 --origin https://ops.example.org --device-id edge-69 [--port 8765] [--admin-cidr 10.10.20.0/24] [--apply]" >&2; }
while (($#));do
 case "$1" in
 --origin) ORIGIN="$2";shift 2;;
 --port) PORT="$2";shift 2;;
 --admin-cidr) ADMIN_CIDR="$2";shift 2;;
 --device-id) DEVICE="$2";shift 2;;
 --apply) APPLY=1;shift;;
 --help|-h) usage;exit 0;;
 *) usage;exit 2;;
 esac
done
[[ "$ORIGIN" =~ ^https://[a-zA-Z0-9.-]+(:[0-9]{1,5})?$ ]] || { usage;exit 2; }
[[ "$DEVICE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || { usage;exit 2; }
[[ "$PORT" =~ ^[0-9]{4,5}$ ]] && ((PORT>=1024 && PORT<=65535)) || { usage;exit 2; }
python3 -B - "$ADMIN_CIDR" <<'PY'
import ipaddress, sys
try:
    subnet=ipaddress.ip_network(sys.argv[1], strict=True)
    allowed=(ipaddress.ip_network("10.0.0.0/8"),
             ipaddress.ip_network("172.16.0.0/12"),
             ipaddress.ip_network("192.168.0.0/16"),
             ipaddress.ip_network("127.0.0.0/8"))
    if subnet.version!=4 or subnet.prefixlen<24 or not any(subnet.subnet_of(net) for net in allowed):
        raise ValueError("admin CIDR must be an explicit private/loopback IPv4 /24 or narrower")
except ValueError as exc:
    raise SystemExit("Invalid --admin-cidr: "+str(exc))
PY
echo "Console plan: $ORIGIN -> 127.0.0.1:$PORT; publisher device=$DEVICE; allowed management source=$ADMIN_CIDR"
echo "No Internet-facing console without your reviewed TLS vhost and access rules."
((APPLY)) || { echo "Preview only; --apply installs a new dedicated user, local service and include-only NGINX snippet.";exit 0; }
((EUID==0)) || { echo "--apply requires root" >&2;exit 2; }
for component in policy-server dns-agent policy-sync;do
 [[ -d /opt/aleph-policy-code/apps/$component/src ]] || { echo "Deploy current reviewed runtime source first: $component" >&2;exit 2; }
done
[[ -f /opt/aleph-policy-code/apps/policy-server/src/policy_server/nodes.py &&
   -f /opt/aleph-policy-code/apps/policy-sync/src/aleph_policy_sync/telemetry.py ]] || {
 echo "Current console and signed report source must be deployed before installing." >&2; exit 2;
}
command -v nginx >/dev/null && command -v systemctl >/dev/null && command -v openssl >/dev/null || { echo "NGINX, systemd and OpenSSL required" >&2;exit 2; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
/usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" verify-runtime "$ROOT" /opt/aleph-policy-code --role policy ||
  { echo "Deployed policy code differs from this checkout; run the code-only upgrade before installing the console." >&2; exit 2; }
for target in /var/lib/aleph-ops-console /etc/systemd/system/aleph-ops-console.service /etc/nginx/snippets/aleph-ops-console.conf /etc/nginx/conf.d/aleph-ops-limits.conf;do
 [[ ! -e "$target" && ! -L "$target" ]] || { echo "Refusing to overwrite existing operator service: $target" >&2;exit 2; }
done
if ! id "$USER" >/dev/null 2>&1;then
 useradd --system --user-group --no-create-home --home-dir /var/lib/aleph-ops-console --shell /usr/sbin/nologin "$USER"
fi
install -d -o "$USER" -g "$USER" -m 0700 /var/lib/aleph-ops-console
openssl rand -hex 48 | install -m 0600 /dev/stdin /var/lib/aleph-ops-console/token
chown "$USER:$USER" /var/lib/aleph-ops-console/token
install -d -o root -g root -m 0755 /etc/aleph-ops-nodes /etc/aleph-ops-nodes/trust
install -d -o root -g root -m 0755 /etc/nginx/snippets /etc/nginx/conf.d
cat >/etc/nginx/conf.d/aleph-ops-limits.conf <<'LIMITS'
# HTTP-context rate/connection zones for the separately included HTTPS vhost.
limit_req_zone $binary_remote_addr zone=aleph_ops_reports:10m rate=120r/m;
limit_conn_zone $binary_remote_addr zone=aleph_ops_connections:10m;
LIMITS
cat >/etc/systemd/system/aleph-ops-console.service <<UNIT
[Unit]
Description=ALEPH authenticated loopback DNS operations dashboard
After=network.target
[Service]
Type=simple
User=$USER
Group=$USER
UMask=0077
WorkingDirectory=/var/lib/aleph-ops-console
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/policy-server/src:/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m policy_server.console --workspace /var/lib/aleph-ops-console --token-file /var/lib/aleph-ops-console/token --port $PORT --origin $ORIGIN --feed-root /srv/aleph-policy-feed --device-id $DEVICE --trust-dir /etc/aleph-policy-sync/trust --node-trust-dir /etc/aleph-ops-nodes/trust
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/aleph-ops-console
RestrictSUIDSGID=yes
[Install]
WantedBy=multi-user.target
UNIT
cat >/etc/nginx/snippets/aleph-ops-console.conf <<UNIT
# Include only inside an existing reviewed HTTPS (443/TLS) vhost for $ORIGIN.
# Do NOT include in a public HTTP server block.
location = /v1/nodes/report {
    client_max_body_size 8k;
    limit_req zone=aleph_ops_reports burst=40 nodelay;
    limit_conn aleph_ops_connections 8;
    limit_except POST { deny all; }
    proxy_set_header Host \$http_host;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_pass http://127.0.0.1:$PORT;
    proxy_read_timeout 12s;
}
# Management UI must be available only through authenticated/approved networks.
location / {
    # Explicitly scoped management address; never trust every private client.
    allow $ADMIN_CIDR;
    deny all;
    proxy_set_header Host \$http_host;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_pass http://127.0.0.1:$PORT;
    proxy_read_timeout 12s;
}
UNIT
chmod 0644 /etc/systemd/system/aleph-ops-console.service /etc/nginx/snippets/aleph-ops-console.conf /etc/nginx/conf.d/aleph-ops-limits.conf
systemctl daemon-reload
systemctl enable --now aleph-ops-console.service
echo "Console service registered. Manually review/include the HTTPS-only NGINX snippet and test nginx -t before reload."
echo "Read the fresh operator token in a secure terminal with: sudo cat /var/lib/aleph-ops-console/token"
echo "Register each separate DNS telemetry public key under /etc/aleph-ops-nodes/trust/<sha256>.pem, owned by root and mode 0644."
