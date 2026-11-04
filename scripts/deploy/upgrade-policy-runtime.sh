#!/usr/bin/env bash
# Opt-in code-only upgrade for existing ALEPH nodes and policy publishers.
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)"
TARGET=/opt/aleph-policy-code
BACKUP=/opt/.aleph-policy-code.rollback
ROLE=''
APPLY=0
usage(){ echo "Usage: $0 --role policy|dns [--apply]" >&2; }
die(){ echo "ALEPH_UPGRADE_ERROR: $*" >&2; exit 2; }
while (($#));do
  case "$1" in
    --role) [[ $# -ge 2 ]] || die "role is required"; ROLE="$2";shift 2;;
    --apply) APPLY=1;shift;;
    --help|-h) usage;exit 0;;
    *) usage;exit 2;;
  esac
done
[[ "$ROLE" == policy || "$ROLE" == dns ]] || { usage;exit 2; }
[[ -d "$TARGET" && ! -L "$TARGET" && $(stat -c '%u' "$TARGET") == 0 ]] ||
  die "root-owned existing /opt/aleph-policy-code directory required"
[[ ! -e "$BACKUP" && ! -L "$BACKUP" ]] ||
  die "rollback directory already exists; inspect it before another upgrade"
if [[ "$ROLE" == dns ]];then
  [[ -f "$TARGET/infra/edge/system_dns.py" ]] || die "DNS runtime missing"
else
  [[ ! -e "$TARGET/infra/edge/system_dns.py" ]] || die "DNS host detected: use --role dns"
fi
python3 -B - "$TARGET" "$ROOT" "$ROLE" <<'PY'
import ast
from pathlib import Path
import stat
import sys
target, source, role = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
apps = {"dns-agent", "policy-sync", "policy-server"}
for file in (target, *target.rglob("*")):
    mode = file.lstat().st_mode
    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or file.stat().st_uid != 0 or mode & 0o022:
        raise SystemExit("Unsafe installed runtime entry: " + str(file))
    if stat.S_ISREG(mode):
        parts = file.relative_to(target).parts
        good = (len(parts) >= 4 and parts[0] == "apps" and parts[1] in apps
                and parts[2] == "src" and file.suffix in {".py", ".json"})
        good |= (role == "dns" and file.relative_to(target).as_posix() in
                 {"infra/edge/system_dns.py", "infra/edge/firewall_guard.py"})
        if not good:
            raise SystemExit("Unrecognized installed file; preserve before upgrade: " + str(file))
for app in apps:
    directory = source / "apps" / app / "src"
    if not directory.is_dir() or directory.is_symlink():
        raise SystemExit("Missing source tree: " + str(directory))
    for file in directory.rglob("*"):
        mode = file.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise SystemExit("Unsafe source entry: " + str(file))
        if stat.S_ISREG(mode) and file.suffix == ".py":
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
if role == "dns":
    for name in ("system_dns.py", "firewall_guard.py"):
        file = source / "infra" / "edge" / name
        if file.is_symlink() or not file.is_file():
            raise SystemExit("Missing DNS admin source: " + str(file))
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
PY
echo "Upgrade plan: role=$ROLE; runtime=$TARGET; backup=$BACKUP"
echo "This changes /opt code only; keys, state and policies under /etc, /var/lib and /srv remain untouched."
((APPLY)) || { echo "Preview only. Stop the relevant timers/services before --apply.";exit 0; }
((EUID == 0)) || die "--apply requires root"
if [[ "$ROLE" == policy ]];then
  UNITS="aleph-policy-refresh.timer aleph-policy-refresh.service aleph-ops-console.service aleph-intel-refresh.service aleph-intel-refresh.socket"
else
  UNITS="aleph-policy-fetch.timer aleph-policy-apply.timer aleph-ops-collect.timer aleph-ops-send.timer aleph-policy-fetch.service aleph-policy-apply.service aleph-ops-collect.service aleph-ops-send.service"
fi
for unit in $UNITS;do
  if systemctl is-active --quiet "$unit";then
    die "$unit is active; explicitly stop it before code upgrade"
  fi
done
STAGING="$(mktemp -d /opt/.aleph-policy-next.XXXXXXXX)"
cleanup(){
  result=$?
  if [[ ! -e "$TARGET" && -d "$BACKUP" ]];then
    mv -T -- "$BACKUP" "$TARGET" || echo "URGENT: restore $BACKUP manually" >&2
  fi
  if [[ -n "$STAGING" && -d "$STAGING" ]];then rm -rf -- "$STAGING";fi
  exit "$result"
}
trap cleanup EXIT
for app in dns-agent policy-sync policy-server;do
  install -d -o root -g root -m 0755 "$STAGING/apps/$app"
  /usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" copy-source "$ROOT/apps/$app/src" "$STAGING/apps/$app/src"
done
if [[ "$ROLE" == dns ]];then
  install -d -o root -g root -m 0755 "$STAGING/infra/edge"
  for file in system_dns.py firewall_guard.py;do
    install -o root -g root -m 0644 "$ROOT/infra/edge/$file" "$STAGING/infra/edge/$file"
  done
fi
chown -R root:root "$STAGING"
find "$STAGING" -type d -exec chmod 0755 {} +
find "$STAGING" -type f -exec chmod 0644 {} +
/usr/bin/python3 -B "$ROOT/scripts/deploy/install_checks.py" verify-runtime "$ROOT" "$STAGING" --role "$ROLE" ||
  die "staged runtime failed the source equivalence check"
# Two same-filesystem renames with rollback on process failure.
# A power cut between them can require restoring the backup manually.
mv -T -- "$TARGET" "$BACKUP"
mv -T -- "$STAGING" "$TARGET"
STAGING=''
trap - EXIT
echo "New runtime active; rollback copy preserved at $BACKUP"
echo "Restart only services previously enabled; validate host behavior before cleanup."
