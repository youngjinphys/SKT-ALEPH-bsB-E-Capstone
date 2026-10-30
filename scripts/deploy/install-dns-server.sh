#!/usr/bin/env bash
# DNS node: existing managed dnsmasq + signed HTTPS snapshot fetch/apply.
# Never changes DHCP, host resolv.conf, or router policies.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
APPLY=0; LISTEN=''; IFACE=''; CLIENTS=''; UPSTREAM=''; POLICY=''; PUB=''; DEVICE=''; URL=''
usage() {
  echo 'Usage: install-dns-server.sh --listen-ip 192.168.7.69 --interface eth0 --client-cidr 192.168.7.0/24 --upstream 9.9.9.9 --bootstrap-policy /private/approved.json --public-key /private/public.pem --device-id edge-69 --policy-url https://policy.example.org/v1/policies/edge-69/current.json [--apply]' >&2
}
while (($#)); do
  case "$1" in
    --listen-ip) LISTEN="${2:?}"; shift 2;;
    --interface) IFACE="${2:?}"; shift 2;;
    --client-cidr) CLIENTS="${2:?}"; shift 2;;
    --upstream) UPSTREAM="${2:?}"; shift 2;;
    --bootstrap-policy) POLICY="${2:?}"; shift 2;;
    --public-key) PUB="${2:?}"; shift 2;;
    --device-id) DEVICE="${2:?}"; shift 2;;
    --policy-url) URL="${2:?}"; shift 2;;
    --apply) APPLY=1; shift;;
    --help|-h) usage; exit 0;;
    *) usage; exit 2;;
  esac
done
[[ "$DEVICE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$ ]] || { usage; exit 2; }
[[ "$URL" =~ ^https://[a-zA-Z0-9][a-zA-Z0-9.-]*(:[0-9]{1,5})?/v1/policies/[a-zA-Z0-9_.-]+/current\.json$ ]] || { echo 'URL must be fixed HTTPS device policy path (no credentials/query/fragment)' >&2; exit 2; }
[[ "$IFACE" =~ ^[A-Za-z0-9_.:-]{1,15}$ ]] || { usage; exit 2; }
[[ -f "$POLICY" && ! -L "$POLICY" && -f "$PUB" && ! -L "$PUB" ]] || { echo 'Bootstrap policy and public key files required' >&2; exit 2; }
[[ -f "$ROOT/infra/edge/system_dns.py" && -f "$ROOT/apps/policy-sync/src/aleph_policy_sync/__main__.py" ]] || { echo 'Run from a complete trusted checkout' >&2; exit 2; }
PYTHONPATH="$ROOT/apps/dns-agent/src:$ROOT/apps/policy-sync/src" /usr/bin/python3 -B -m aleph_policy_sync key-id --public-key "$PUB" >/dev/null || {
  echo 'Invalid trusted Ed25519 public key' >&2; exit 2;
}
PYTHONPATH="$ROOT/apps/dns-agent/src" /usr/bin/python3 -B -m dns_agent validate "$POLICY"
# Explicit checks, not assert: PYTHONOPTIMIZE must never disable a security gate.
/usr/bin/python3 - "$LISTEN" "$IFACE" "$CLIENTS" "$UPSTREAM" "$URL" "$DEVICE" <<'PY'
import ipaddress, sys, urllib.parse
ip, iface, clients, upstream, url, device = sys.argv[1:]
try:
    private = [ipaddress.ip_network(p) for p in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    listen = ipaddress.IPv4Address(ip)
    net = ipaddress.IPv4Network(clients, strict=True)
    if not (any(listen in r for r in private) and any(net.subnet_of(r) for r in private) and net.prefixlen >= 24):
        raise ValueError('private listener and client /24-or-smaller network required')
    remote = ipaddress.IPv4Address(upstream)
    if remote.is_multicast or remote.is_unspecified or remote == listen:
        raise ValueError('invalid upstream')
    p = urllib.parse.urlsplit(url)
    if not (p.scheme == 'https' and p.hostname and (p.port is None or 1 <= p.port <= 65535)
            and p.username is None and p.password is None and not p.query and not p.fragment
            and p.path == f'/v1/policies/{device}/current.json'):
        raise ValueError('HTTPS policy URL must match device ID exactly')
except ValueError as exc:
    raise SystemExit(str(exc)) from None
PY
echo "DNS install plan: $LISTEN:53 interface=$IFACE clients=$CLIENTS upstream=$UPSTREAM device=$DEVICE"
echo "Policy Pull: $URL; only signed releases can reach the existing protected publish path."
((APPLY)) || { echo 'Preview only; use --apply to install. DHCP and host DNS remain unchanged.'; exit 0; }
((EUID == 0)) || { echo 'Run --apply as root (sudo).' >&2; exit 2; }
/usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" check dns --device-id "$DEVICE"
/usr/bin/python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' || { echo 'Python >=3.11 required' >&2; exit 2; }
/usr/bin/python3 -c 'import cryptography' || { echo 'Install python3-cryptography first' >&2; exit 2; }
command -v dnsmasq >/dev/null && command -v nft >/dev/null && command -v systemctl >/dev/null || { echo 'Install dnsmasq-base, nftables, systemd first' >&2; exit 2; }
for path in /opt/aleph-policy-code /etc/systemd/system/aleph-policy-fetch.service /etc/systemd/system/aleph-policy-apply.service /etc/systemd/system/aleph-policy-fetch.timer /etc/systemd/system/aleph-policy-apply.timer; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Existing installation path; refuse overwrite: $path" >&2; exit 2; }
done
if [[ -n "$(find "$ROOT/apps/dns-agent/src" "$ROOT/apps/policy-sync/src" "$ROOT/infra/edge" -type l -print -quit)" ]]; then
  echo 'Symlinked source in application tree; refuse root install' >&2; exit 2;
fi
# Reuse managed installer rather than duplicating DNS/firewall configuration.
/usr/bin/python3 -B "$ROOT/infra/edge/system_dns.py" install --listen-ip "$LISTEN" --interface "$IFACE" --client-cidr "$CLIENTS" --upstream "$UPSTREAM" --policy "$POLICY" --apply
for app in dns-agent policy-sync; do
  install -d -o root -g root -m 0755 "/opt/aleph-policy-code/apps/$app"
  /usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" copy-source \
    "$ROOT/apps/$app/src" "/opt/aleph-policy-code/apps/$app/src"
done
install -d -o root -g root -m 0755 /opt/aleph-policy-code/infra/edge
install -o root -g root -m 0644 "$ROOT/infra/edge/system_dns.py" /opt/aleph-policy-code/infra/edge/system_dns.py
install -o root -g root -m 0644 "$ROOT/infra/edge/firewall_guard.py" /opt/aleph-policy-code/infra/edge/firewall_guard.py
chown -R root:root /opt/aleph-policy-code
find /opt/aleph-policy-code -type d -exec chmod 0755 {} +
find /opt/aleph-policy-code -type f -exec chmod 0644 {} +
install -d -o root -g root -m 0755 /etc/aleph-policy-sync/trust
install -o root -g root -m 0644 "$PUB" /etc/aleph-policy-sync/trust/.incoming.pem
KEY_ID="$(PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src /usr/bin/python3 -B -m aleph_policy_sync key-id --public-key /etc/aleph-policy-sync/trust/.incoming.pem)"
[[ "$KEY_ID" =~ ^[0-9a-f]{64}$ ]] || exit 2
mv -f /etc/aleph-policy-sync/trust/.incoming.pem "/etc/aleph-policy-sync/trust/$KEY_ID.pem"
if ! id aleph-policy-fetch >/dev/null 2>&1; then
  useradd --system --user-group --no-create-home --home-dir /var/lib/aleph-policy-fetch --shell /usr/sbin/nologin aleph-policy-fetch
fi
install -d -o aleph-policy-fetch -g aleph-policy-fetch -m 0700 /var/lib/aleph-policy-fetch
install -d -o root -g root -m 0700 /var/lib/aleph-policy-apply
cat >/etc/systemd/system/aleph-policy-fetch.service <<UNIT
[Unit]
Description=ALEPH unprivileged verified HTTPS policy fetch
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
User=aleph-policy-fetch
Group=aleph-policy-fetch
UMask=0077
StateDirectory=aleph-policy-fetch
StateDirectoryMode=0700
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m aleph_policy_sync fetch --url $URL --device-id $DEVICE --trust-dir /etc/aleph-policy-sync/trust --inbox-dir /var/lib/aleph-policy-fetch
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
RestrictSUIDSGID=yes
UNIT
cat >/etc/systemd/system/aleph-policy-apply.service <<UNIT
[Unit]
Description=ALEPH root-only local policy verifier and DNS publisher
After=aleph-dns.service
ConditionPathExists=/var/lib/aleph-policy-fetch/current.json
[Service]
Type=oneshot
User=root
UMask=0077
StateDirectory=aleph-policy-apply
StateDirectoryMode=0700
Environment=PYTHONPATH=/opt/aleph-policy-code/apps/dns-agent/src:/opt/aleph-policy-code/apps/policy-sync/src
ExecStart=/usr/bin/python3 -B -m aleph_policy_sync apply --device-id $DEVICE --trust-dir /etc/aleph-policy-sync/trust --inbox-dir /var/lib/aleph-policy-fetch --fetch-user aleph-policy-fetch --state-dir /var/lib/aleph-policy-apply --dns-admin /opt/aleph-policy-code/infra/edge/system_dns.py
UNIT
install -o root -g root -m 0644 "$ROOT/infra/edge/policy-sync/aleph-policy-fetch.timer" /etc/systemd/system/aleph-policy-fetch.timer
install -o root -g root -m 0644 "$ROOT/infra/edge/policy-sync/aleph-policy-apply.timer" /etc/systemd/system/aleph-policy-apply.timer
chmod 0644 /etc/systemd/system/aleph-policy-fetch.service /etc/systemd/system/aleph-policy-apply.service
systemctl daemon-reload
systemctl enable --now aleph-policy-fetch.timer aleph-policy-apply.timer
printf 'DNS managed service and signed policy sync timers installed. Key ID: %s\n' "$KEY_ID"
echo 'Test on a separate authorized client: dig @'"$LISTEN"' example.org A and +tcp; DHCP/resolv.conf must be configured separately.'
