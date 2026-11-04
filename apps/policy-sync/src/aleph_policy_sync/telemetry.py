"""Signed, outbound-only DNS node status. Never grants remote DNS administration.

Root creates a local Ed25519 attestation using a DEVICE-ONLY key. An
unprivileged process sends its signed report to the HTTPS policy console.
The policy signer key is never used here or installed on the DNS node.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import grp
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .snapshot import (canonical, device_id, fields, load_private_key, public_key_id,
                       seq, strict_load, timestamp, trust_key, _regular_read,
                       verify_envelope, MAX_SEQUENCE)
from dns_agent.runtime import dns_rcode
from .metrics import collect_metrics, validate_metrics

MAX_REPORT_BYTES = 8192
REPORT_FORMAT = 4
REPORT_LIFETIME = timedelta(seconds=150)
HEX = re.compile(r"[0-9a-f]{64}\Z")


class TelemetryError(ValueError):
    """A status report or operational prerequisite is invalid."""


def private_ipv4(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except (ValueError, TypeError) as exc:
        raise TelemetryError("DNS listening address must be IPv4") from exc
    if not any(address in ipaddress.IPv4Network(cidr)
               for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
        raise TelemetryError("DNS listening address must be RFC1918")
    return str(address)


def validate_payload(payload: object, *, now=None) -> dict:
    fields(payload, ("format", "type", "device_id", "report_sequence",
                     "reported_at", "dns_address", "policy_sequence", "policy_sha256",
                     "applied_at", "attestation", "probe") +
           (("metrics",) if type(payload) is dict and payload.get("format") in (3, 4) else ()), "status payload")
    if (type(payload["format"]) is not int or payload["format"] not in (1, 2, 3, REPORT_FORMAT)
            or payload["type"] != "aleph-dns-node-report"):
        raise TelemetryError("unsupported report format")
    device_id(payload["device_id"])
    seq(payload["report_sequence"])
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    reported = timestamp(payload["reported_at"], "reported_at")
    if reported > instant + timedelta(seconds=60) or instant - reported > REPORT_LIFETIME:
        raise TelemetryError("stale or future report")
    private_ipv4(payload["dns_address"])
    policy_seq, digest, applied_at = (payload[x] for x in
                                      ("policy_sequence", "policy_sha256", "applied_at"))
    if policy_seq is None:
        if digest is not None or applied_at is not None:
            raise TelemetryError("missing policy identity")
    else:
        seq(policy_seq)
        if not isinstance(digest, str) or HEX.fullmatch(digest) is None:
            raise TelemetryError("invalid policy digest")
        applied = timestamp(applied_at, "applied_at")
        if applied > reported + timedelta(seconds=60):
            raise TelemetryError("application time is after report")
    if payload["attestation"] not in ("ATTESTED", "FAILED", "NO_POLICY", "EXPIRED"):
        raise TelemetryError("invalid DNS attestation status")
    if payload["attestation"] == "ATTESTED" and policy_seq is None:
        raise TelemetryError("cannot attest absent policy")
    probe = payload["probe"]
    v2 = payload["format"] >= 2
    required = {"domain", "udp", "tcp", "baseline"} if v2 else {"domain", "udp", "tcp"}
    if type(probe) is not dict or set(probe) != required:
        raise TelemetryError("invalid local probe")
    if probe["domain"] is None:
        if (probe["udp"] is not None or probe["tcp"] is not None
                or v2 and probe["baseline"] is not None):
            raise TelemetryError("probe must identify the canary")
    else:
        from dns_agent.policy import domain_name
        if domain_name(probe["domain"]) != probe["domain"]:
            raise TelemetryError("probe domain must be canonical")
        if type(probe["udp"]) is not bool or type(probe["tcp"]) is not bool:
            raise TelemetryError("incomplete DNS UDP/TCP probe")
        if v2 and probe["baseline"] is not None and type(probe["baseline"]) is not bool:
            raise TelemetryError("baseline must be boolean or unknown")
        if payload["attestation"] != "ATTESTED":
            raise TelemetryError("probes only valid after local attestation")
    if payload["format"] in (3, 4):
        validate_metrics(payload["metrics"])
        if ("system" in payload["metrics"]) != (payload["format"] == 4):
            raise TelemetryError("Resource metrics must match report format 4")
        if payload["probe"]["domain"] is None and payload["metrics"]["checks"]:
            raise TelemetryError("Probe measurements require an attested canary")
    return payload


def signed_report(payload: dict, key: Ed25519PrivateKey, *, now=None) -> bytes:
    validate_payload(payload, now=now)
    wrapper = {
        "payload": payload, "key_id": public_key_id(key.public_key()),
        "signature": base64.urlsafe_b64encode(key.sign(canonical(payload))).decode().rstrip("=")
    }
    raw = canonical(wrapper) + b"\n"
    if len(raw) > MAX_REPORT_BYTES:
        raise TelemetryError("report exceeds size bound")
    return raw


def verify_report(raw: bytes, *, expected_device: str, expected_key_id: str,
                  trust_dir: Path, now=None) -> dict:
    report = strict_load(raw, limit=MAX_REPORT_BYTES)
    fields(report, ("payload", "key_id", "signature"), "device report")
    if report["key_id"] != expected_key_id or not HEX.fullmatch(expected_key_id):
        raise TelemetryError("unregistered report signing key")
    sig = report["signature"]
    if not isinstance(sig, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", sig):
        raise TelemetryError("invalid device report signature encoding")
    key = trust_key(Path(trust_dir), expected_key_id)
    try:
        key.verify(base64.urlsafe_b64decode(sig + "=="), canonical(report["payload"]))
    except (ValueError, InvalidSignature, TypeError) as exc:
        raise TelemetryError("device signature invalid") from exc
    payload = validate_payload(report["payload"], now=now)
    if payload["device_id"] != expected_device:
        raise TelemetryError("device identity mismatch")
    return payload


def _dir(path: Path, owner: int, *, mode=0o700):
    if path.is_symlink() or not path.is_dir():
        raise TelemetryError("pre-created private telemetry directory required")
    st = path.stat()
    if st.st_uid != owner or st.st_mode & 0o007 or st.st_mode & 0o020:
        raise TelemetryError("unsafe telemetry directory ownership or mode")
    if mode == 0o700 and st.st_mode & 0o070:
        raise TelemetryError("root-only telemetry state must be private")


def _atomic(path: Path, raw: bytes, *, gid=None, mode=0o600):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise TelemetryError("unsafe output file")
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pending-status-")
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            if gid is not None:
                os.fchown(stream.fileno(), 0, gid)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_applied(path: Path):
    try:
        raw = _regular_read(path, 2048, forbidden=0o077, owner=0)
    except FileNotFoundError:
        return None
    state = strict_load(raw, limit=2048)
    fields(state, ("sequence", "payload_sha256", "policy_sha256", "applied_at"), "apply watermark")
    seq(state["sequence"])
    for field in ("policy_sha256", "payload_sha256"):
        if not isinstance(state[field], str) or not HEX.fullmatch(state[field]):
            raise TelemetryError("invalid applied policy identity")
    timestamp(state["applied_at"], "applied_at")
    return state


def _attest(admin: Path, digest: str) -> bool:
    # Same local root-only validation path used by policy-sync apply.
    from .sync import _safe_root_program
    executable = _safe_root_program(admin)
    try:
        proc = subprocess.run(
            ["/usr/bin/python3", "-B", str(executable), "attest", "--policy-sha256", digest],
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, stdin=subprocess.DEVNULL, timeout=30, check=False)
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_upstream_ipv4(value: str | None, address: str) -> str | None:
    """An explicit independent resolver, never the local policy listener."""
    if value is None:
        return None
    try:
        server = ipaddress.IPv4Address(value)
    except (TypeError, ValueError) as exc:
        raise TelemetryError("upstream probe must use a valid IPv4 address") from exc
    if (server.is_unspecified or server.is_multicast or server.is_loopback
            or server.is_link_local or server.is_reserved or str(server) == address):
        raise TelemetryError("upstream probe must use an independent reachable resolver")
    return str(server)


def build_local_payload(*, device: str, address: str, applied: dict | None,
                        inbox: Path, trust_dir: Path, dns_admin: Path,
                        report_sequence: int, now=None, attest=None, probe=None,
                        upstream: str | None = None, cache_metrics=False, metrics_interface=None, quality_probes=False):
    """Read current signed inbox and validate live state before claiming success."""
    instant = now or datetime.now(timezone.utc)
    device = device_id(device)
    address = private_ipv4(address)
    upstream = probe_upstream_ipv4(upstream, address)
    identity = applied is not None
    metrics = collect_metrics(address, cache_enabled=cache_metrics, interface=metrics_interface,
                              quality_probes=quality_probes, upstream=upstream)
    basic = {
        "format": REPORT_FORMAT, "type": "aleph-dns-node-report",
        "device_id": device, "report_sequence": report_sequence,
        "reported_at": instant.astimezone(timezone.utc).isoformat(),
        "dns_address": address,
        "policy_sequence": applied["sequence"] if identity else None,
        "policy_sha256": applied["policy_sha256"] if identity else None,
        "applied_at": applied["applied_at"] if identity else None,
        "attestation": "NO_POLICY" if not identity else "FAILED",
        "probe": {"domain": None, "udp": None, "tcp": None, "baseline": None},
        "metrics": metrics
    }
    raw_probe = probe or dns_rcode
    def measured_probe(name, qtype, port, **kwargs):
        started = time.perf_counter()
        sample = {'target': 'local' if kwargs.get('server_ip') == address else 'upstream',
                  'transport': 'tcp' if kwargs.get('tcp') else 'udp',
                  'qtype': 'A' if qtype == 1 else 'AAAA', 'rcode': None,
                  'elapsed_ms': 0, 'outcome': 'error'}
        try:
            code = raw_probe(name, qtype, port, **kwargs)
            sample.update(rcode=code, outcome='response')
            return code
        except TimeoutError:
            sample['outcome'] = 'timeout'
            raise
        finally:
            sample['elapsed_ms'] = min(60000, round(max(0, time.perf_counter()-started)*1000, 3))
            metrics['checks'].append(sample)
    if not identity:
        return basic
    try:
        blob = _regular_read(inbox, 2 * 1024 * 1024, forbidden=0o077)
        envelope, policy = verify_envelope(blob, expected_device=device, trust_dir=trust_dir,
                                           now=instant, allow_expired=True)
        if (envelope["sequence"] != applied["sequence"] or
                policy.digest != applied["policy_sha256"] or
                hashlib.sha256(canonical(envelope)).hexdigest() != applied["payload_sha256"]):
            return basic
        metrics["policy"] = {"valid_until": envelope["valid_until"], "active_blocks": len(policy.blocked(instant))}
        if timestamp(envelope["valid_until"], "valid_until") <= instant:
            # The signature still matches, but a lapsed window is not attestation.
            basic["attestation"] = "EXPIRED"
            return basic
        checker = attest if attest is not None else _attest
        if not checker(dns_admin, policy.digest):
            return basic
        basic["attestation"] = "ATTESTED"
        names = policy.blocked(instant)
        if names:
            name = names[0]  # Only an already approved, signed BLOCK; never an arbitrary URL.
            answers = {}
            for tcp in (False, True):
                try:
                    resolver = measured_probe
                    answers["tcp" if tcp else "udp"] = (
                        resolver(name, 1, 53, tcp=tcp, server_ip=address, timeout=1.0) == 3 and
                        resolver(name, 28, 53, tcp=tcp, server_ip=address, timeout=1.0) == 3)
                except (OSError, RuntimeError, ValueError):
                    answers["tcp" if tcp else "udp"] = False
            # Local NXDOMAIN alone is inconclusive: the name may also be
            # nonexistent upstream. Only a positive A record from an
            # independent resolver corroborates an actual block.
            reference = None
            if upstream is not None:
                reference = True
                for tcp in (False, True):
                    try:
                        resolver = measured_probe
                        if resolver(name, 1, 53, tcp=tcp, server_ip=upstream,
                                    timeout=1.0, require_answer=True) != 0:
                            reference = False
                    except (OSError, RuntimeError, ValueError):
                        reference = False
            basic["probe"] = {"domain": name, **answers, "baseline": reference}
    except (OSError, ValueError, RuntimeError):
        pass  # Preserve FAILED/NO_POLICY state, never fabricate success.
    return basic


def collect(*, device: str, address: str, state_dir: Path, outbox_dir: Path,
            key_file: Path, inbox: Path, trust_dir: Path, dns_admin: Path,
            sender_group: str, applied_path: Path = Path("/var/lib/aleph-policy-apply/applied.json"),
            now=None, attest=None, probe=None, upstream: str | None = None, cache_metrics=False, metrics_interface=None, quality_probes=False):
    if os.geteuid() != 0:
        raise TelemetryError("device reporter collection requires root")
    state_dir, outbox_dir = Path(state_dir), Path(outbox_dir)
    _dir(state_dir, 0)
    _dir(outbox_dir, 0, mode=0o750)
    group = grp.getgrnam(sender_group)
    if outbox_dir.stat().st_gid != group.gr_gid:
        raise TelemetryError("outbox group mismatch")
    key = load_private_key(key_file)
    lock = os.open(state_dir / ".telemetry.lock",
                   os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(lock).st_mode & 0o077:
            raise TelemetryError("unsafe telemetry lock")
        fcntl.flock(lock, fcntl.LOCK_EX)
        counter_path = state_dir / "counter.json"
        try:
            counter = strict_load(_regular_read(counter_path, 2048, forbidden=0o077, owner=0), limit=2048)
            fields(counter, ("sequence",), "report sequence state")
            prior = counter["sequence"]
            if type(prior) is not int or not 0 <= prior < MAX_SEQUENCE:
                raise TelemetryError("invalid report sequence")
        except FileNotFoundError:
            prior = 0
        number = prior + 1
        # Counter committed first: a crash may skip a number, never reuse one.
        _atomic(counter_path, canonical({"sequence": number}) + b"\n")
        status = build_local_payload(
            device=device, address=address, applied=_read_applied(applied_path),
            inbox=inbox, trust_dir=trust_dir, dns_admin=dns_admin,
            report_sequence=number, now=now, attest=attest, probe=probe,
            upstream=upstream, cache_metrics=cache_metrics, metrics_interface=metrics_interface, quality_probes=quality_probes)
        raw = signed_report(status, key, now=now)
        _atomic(outbox_dir / "report.json", raw, gid=group.gr_gid, mode=0o640)
        return {"device": device, "report_sequence": number,
                "attestation": status["attestation"], "probe": status["probe"]}
    finally:
        os.close(lock)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        return None


def send(*, report_file: Path, url: str, expected_device: str, key_id: str,
         trust_dir: Path, ca_file: Path | None = None, post=None):
    if os.geteuid() == 0:
        raise TelemetryError("HTTPS status sender must be unprivileged")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment or parsed.path != "/v1/nodes/report"):
        raise TelemetryError("outbound status target must be exact HTTPS /v1/nodes/report")
    raw = _regular_read(report_file, MAX_REPORT_BYTES, forbidden=0o027, owner=0)
    payload = verify_report(raw, expected_device=expected_device, expected_key_id=key_id,
                            trust_dir=trust_dir)
    request = urllib.request.Request(url, data=raw, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json"})
    if post is None:
        import ssl
        ctx = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect,
                                             urllib.request.HTTPSHandler(context=ctx))
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                raise TelemetryError("status receiver rejected report")
            body = response.read(4097)
    else:
        body = post(request)
    if len(body) > 4096:
        raise TelemetryError("receiver response too large")
    receipt = strict_load(body, limit=4096)
    if (type(receipt) is not dict or
            not set(receipt) == {"accepted", "duplicate", "device", "report_sequence"}
            or receipt["accepted"] is not True
            or type(receipt["duplicate"]) is not bool or
            receipt["device"] != payload["device_id"] or
            receipt["report_sequence"] != payload["report_sequence"]):
        raise TelemetryError("mismatched status receipt")
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="action", required=True)
    col = commands.add_parser("collect", help="root-only local attest + signed outbox")
    col.add_argument("--device-id", required=True)
    col.add_argument("--listen-ip", required=True)
    col.add_argument("--metrics-interface", help="explicit NIC for aggregate traffic counters")
    col.add_argument("--quality-probes", action="store_true", help="opt in to fixed example.org A DNS probes")
    col.add_argument("--cache-metrics", action="store_true", help="opt in to aggregate dnsmasq CHAOS counters; no query logs")
    col.add_argument("--probe-upstream", help="independent upstream positive A reference for DNS canary")
    col.add_argument("--state-dir", type=Path, default=Path("/var/lib/aleph-ops-root"))
    col.add_argument("--outbox-dir", type=Path, default=Path("/var/lib/aleph-ops-outbox"))
    col.add_argument("--sender-group", default="aleph-ops-sender")
    col.add_argument("--private-key", required=True, type=Path)
    col.add_argument("--inbox", type=Path, default=Path("/var/lib/aleph-policy-fetch/current.json"))
    col.add_argument("--trust-dir", type=Path, default=Path("/etc/aleph-policy-sync/trust"))
    col.add_argument("--dns-admin", type=Path, default=Path("/opt/aleph-policy-code/infra/edge/system_dns.py"))
    col.add_argument("--applied-state", type=Path, default=Path("/var/lib/aleph-policy-apply/applied.json"))
    tx = commands.add_parser("send", help="non-root HTTPS POST of an already signed report")
    tx.add_argument("--url", required=True)
    tx.add_argument("--device-id", required=True)
    tx.add_argument("--key-id", required=True)
    tx.add_argument("--trust-dir", required=True, type=Path)
    tx.add_argument("--report-file", type=Path, default=Path("/var/lib/aleph-ops-outbox/report.json"))
    tx.add_argument("--ca-file", type=Path)
    args = p.parse_args(argv)
    try:
        if args.action == "collect":
            result = collect(device=args.device_id, address=args.listen_ip,
                             state_dir=args.state_dir, outbox_dir=args.outbox_dir,
                             sender_group=args.sender_group, key_file=args.private_key,
                             inbox=args.inbox, trust_dir=args.trust_dir, dns_admin=args.dns_admin,
                             applied_path=args.applied_state,
                             upstream=args.probe_upstream, cache_metrics=args.cache_metrics,
                             metrics_interface=args.metrics_interface, quality_probes=args.quality_probes)
        else:
            result = send(report_file=args.report_file, url=args.url,
                          expected_device=args.device_id, key_id=args.key_id,
                          trust_dir=args.trust_dir, ca_file=args.ca_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        print("DNS_TELEMETRY_ERROR: " + str(exc)[:180], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
