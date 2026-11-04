"""Operator-enrolled DNS nodes and authenticated, non-privileged status receipt.

No arbitrary HTTP probes, remote shell, DNS configuration writes or private
signing keys exist in this service. Each node key is pinned by an operator.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import threading

from aleph_policy_sync.snapshot import (canonical, device_id, strict_load, trust_key,
                                         timestamp, _regular_read)
from aleph_policy_sync.telemetry import (MAX_REPORT_BYTES, REPORT_LIFETIME,
                                         TelemetryError, private_ipv4, verify_report)
from . import intel
from .analytics import append_history, history_points, MAX_RECEIPT_BYTES

HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_NODES = 64
MAX_RETIRED_KEYS = 1024


class NodeError(ValueError):
    """A node enrollment, attestation or status request was rejected."""


class NodeConflict(NodeError):
    """Stale or replayed node report; current state preserved."""


class _RetiredNodeKey(Exception):
    """Prior key report retained for audit; not an active report for a new key."""


def _label(value):
    if (not isinstance(value, str) or not 2 <= len(value) <= 64
            or value.strip() != value
            or any(ord(x) < 32 or ord(x) == 127 for x in value)):
        raise NodeError("node label must be 2-64 printable characters")
    return value


def _digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def _owned_file(path: Path, limit: int) -> object:
    return strict_load(_regular_read(path, limit, forbidden=0o077, owner=os.geteuid()), limit=limit)


class Nodes:
    def __init__(self, workspace: Path, trust_dir: Path | None = None):
        self.workspace = Path(workspace)
        self.trust_dir = Path(trust_dir) if trust_dir is not None else None
        self.state = self.workspace / "nodes-state"
        self.state.mkdir(mode=0o700, exist_ok=True)
        info = self.state.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise NodeError("node state must be owner-only 0700")
        if self.trust_dir is not None:
            info = self.trust_dir.lstat()
            if (not stat.S_ISDIR(info.st_mode)
                    or info.st_uid not in (0, os.geteuid()) or info.st_mode & 0o022):
                raise NodeError("node trust directory must be protected and pre-created")
        self.mutex = threading.RLock()

    @contextmanager
    def _write_lock(self):
        """Coordinate registry and receipt writes across separate console processes."""
        with self.mutex:
            fd = os.open(self.state / ".nodes.lock",
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or
                        info.st_uid != os.geteuid() or info.st_mode & 0o077):
                    raise NodeError("unsafe node-state lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def _registry(self):
        """Atomically migrate v1 registrations to v2's permanent key tombstones."""
        try:
            obj = _owned_file(self.workspace / "nodes.json", 131072)
        except FileNotFoundError:
            obj = {"format": 2, "nodes": [], "retired_key_ids": []}
        if type(obj) is not dict or type(obj.get("format")) is not int:
            raise NodeError("invalid node registry")
        if obj["format"] == 1 and set(obj) == {"format", "nodes"}:
            obj = {"format": 2, "nodes": obj["nodes"], "retired_key_ids": []}
        if (obj["format"] != 2 or set(obj) != {"format", "nodes", "retired_key_ids"}
                or type(obj["nodes"]) is not list or len(obj["nodes"]) > MAX_NODES
                or type(obj["retired_key_ids"]) is not list
                or len(obj["retired_key_ids"]) > MAX_RETIRED_KEYS):
            raise NodeError("invalid node registry")
        retired = obj["retired_key_ids"]
        if (any(not isinstance(x, str) or not HEX.fullmatch(x) for x in retired)
                or len(retired) != len(set(retired))):
            raise NodeError("invalid retired key history")
        names, keys = set(), set()
        for node in obj["nodes"]:
            if type(node) is not dict or set(node) != {"device_id", "dns_address", "label", "key_id"}:
                raise NodeError("invalid registered node fields")
            device_id(node["device_id"])
            private_ipv4(node["dns_address"])
            _label(node["label"])
            if not isinstance(node["key_id"], str) or not HEX.fullmatch(node["key_id"]):
                raise NodeError("invalid node trust key fingerprint")
            if (node["device_id"] in names or node["key_id"] in keys
                    or node["key_id"] in retired):
                raise NodeError("duplicate, retired or reused device key")
            names.add(node["device_id"])
            keys.add(node["key_id"])
        return obj

    def registered(self):
        return self._registry()["nodes"]

    def register(self, body: dict):
        if self.trust_dir is None:
            raise NodeError("node trust directory must be configured by administrator")
        if type(body) is not dict or set(body) != {"device_id", "dns_address", "label", "key_id"}:
            raise NodeError("node registration requires exact identity fields")
        item = {
            "device_id": device_id(body["device_id"]),
            "dns_address": private_ipv4(body["dns_address"]),
            "label": _label(body["label"]),
            "key_id": body["key_id"]
        }
        if not isinstance(item["key_id"], str) or not HEX.fullmatch(item["key_id"]):
            raise NodeError("invalid registered key id")
        # Trust material is provisioned separately by root/administrator, not uploaded via GUI.
        try:
            trust_key(self.trust_dir, item["key_id"])
        except (OSError, ValueError) as exc:
            raise NodeError("node public key is not installed or trusted") from exc
        with self._write_lock():
            registry = self._registry()
            nodes = registry["nodes"]
            if item["key_id"] in registry["retired_key_ids"]:
                raise NodeError("retired device key cannot be re-enrolled; rotate it")
            if len(nodes) >= MAX_NODES:
                raise NodeError("node registry limit reached")
            if any(x["device_id"] == item["device_id"] or x["key_id"] == item["key_id"]
                   for x in nodes):
                raise NodeError("device/key already registered; replace via explicit maintenance procedure")
            nodes.append(item)
            registry["nodes"] = sorted(nodes, key=lambda x: x["device_id"])
            intel.write_json(self.workspace / "nodes.json", registry)
        return {"registered": True, "device_id": item["device_id"]}

    def unregister(self, body):
        if (type(body) is not dict or set(body) != {"device_id", "confirm", "expected_key_id"}
                or body["confirm"] != "UNREGISTER_NODE"
                or not isinstance(body["expected_key_id"], str)
                or HEX.fullmatch(body["expected_key_id"]) is None):
            raise NodeError("explicit device removal confirmation required")
        target = device_id(body["device_id"])
        with self._write_lock():
            registry = self._registry()
            nodes = registry["nodes"]
            selected = next((n for n in nodes if n["device_id"] == target), None)
            if selected is None:
                raise NodeError("device is not registered")
            if not hmac.compare_digest(selected["key_id"], body["expected_key_id"]):
                raise NodeConflict("Device identity changed; reload before removing this node")
            retired = registry["retired_key_ids"]
            if len(retired) >= MAX_RETIRED_KEYS:
                raise NodeError("retired key history full; maintenance required")
            registry["retired_key_ids"] = sorted([*retired, selected["key_id"]])
            registry["nodes"] = [n for n in nodes if n["device_id"] != target]
            intel.write_json(self.workspace / "nodes.json", registry)
            # Retaining the old receipt is safe: its key can never be enrolled
            # again. A replacement must prove possession of a new device key.
        return {"removed": True, "device_id": target}

    def _path(self, device):
        return self.state / (device_id(device) + ".json")

    def receive(self, raw: bytes, *, now=None):
        if self.trust_dir is None:
            raise NodeError("node trust directory is not configured")
        if not isinstance(raw, bytes) or len(raw) > MAX_REPORT_BYTES:
            raise NodeError("node report too large")
        untrusted = strict_load(raw, limit=MAX_REPORT_BYTES)
        if type(untrusted) is not dict or set(untrusted) != {"payload", "key_id", "signature"}:
            raise NodeError("invalid node report wrapper")
        outer = untrusted["payload"]
        if type(outer) is not dict:
            raise NodeError("invalid node report")
        device = device_id(outer.get("device_id"))
        instant = now or datetime.now(timezone.utc)
        with self._write_lock():
            enrolled = next((n for n in self.registered() if n["device_id"] == device), None)
            if enrolled is None:
                raise NodeError("node is not enrolled")
            try:
                payload = verify_report(raw, expected_device=device,
                                        expected_key_id=enrolled["key_id"],
                                        trust_dir=self.trust_dir, now=instant)
            except (OSError, ValueError) as exc:
                raise NodeError("invalid signed node report") from exc
            if payload["dns_address"] != enrolled["dns_address"]:
                raise NodeError("reported DNS address differs from enrolled device")
            path = self._path(device)
            try:
                previous = _owned_file(path, MAX_RECEIPT_BYTES)
            except FileNotFoundError:
                previous = None
            if previous is not None and previous["signed"].get("key_id") != enrolled["key_id"]:
                # Explicit unenroll/re-enroll with a NEW root-pinned key resets
                # the replay domain. A key cannot be silently changed in place.
                previous = None
            if previous is not None:
                old_raw = canonical(previous["signed"])
                old = verify_report(old_raw, expected_device=device,
                                    expected_key_id=enrolled["key_id"],
                                    trust_dir=self.trust_dir,
                                    now=timestamp(previous["received_at"], "received_at"))
                if payload["report_sequence"] < old["report_sequence"]:
                    raise NodeConflict("out-of-order status counter rejected")
                if payload["report_sequence"] == old["report_sequence"]:
                    if not hmac.compare_digest(_digest(untrusted), _digest(previous["signed"])):
                        raise NodeConflict("conflicting status at same report counter")
                    return {"accepted": True, "duplicate": True, "device": device,
                            "report_sequence": payload["report_sequence"]}
            # Only an accepted, newly authenticated report updates the freshness clock.
            history = append_history(previous.get('history') if previous else None, payload, instant)
            receipt = {"received_at": instant.isoformat(), "signed": untrusted, "history": history}
            if len(json.dumps(receipt, ensure_ascii=True, indent=2).encode()) >= MAX_RECEIPT_BYTES:
                raise NodeError("bounded node history capacity exceeded")
            intel.write_json(path, receipt)
            return {"accepted": True, "duplicate": False, "device": device,
                    "report_sequence": payload["report_sequence"]}

    def analytics(self, deployment):
        now = datetime.now(timezone.utc)
        nodes = []
        for current in self.states(deployment):
            points = []
            history_error = False
            if current['report_at'] is not None and current['state'] not in ('INVALID_REPORT', 'REKEY_PENDING'):
                try:
                    stored = _owned_file(self._path(current['device_id']), MAX_RECEIPT_BYTES)
                    # Registry pin + verified current receipt define the observation epoch.
                    if stored['signed']['key_id'] != current['key_id']:
                        raise ValueError('Telemetry identity changed during read')
                    points = history_points(stored.get('history'), now)
                    if points and points[-1]['sequence'] > current['report_sequence']:
                        raise ValueError('Telemetry changed during read; retry')
                except (ValueError, OSError, KeyError, TypeError):
                    history_error = True
            nodes.append({k: current[k] for k in ('device_id', 'label', 'state', 'report_at', 'received_at', 'dns_applied')} |
                         {'points': points if not history_error else [], 'history_error': history_error,
                          'metrics': current['metrics'], 'report_format': current['report_format'], 'lan_verified': False})
        return {'observed_at': now.isoformat(), 'retention_hours': 24,
                'recent_limit': 48, 'hourly_limit': 24, 'poll_seconds': 10,
                'collection_seconds': 60, 'source': 'verified-node-receipts',
                'privacy': 'aggregate-only-no-client-history', 'nodes': nodes}

    def states(self, deployment):
        """Always separate signed report, publisher, and LAN application claims."""
        instant = datetime.now(timezone.utc)
        result = []
        for item in self.registered():
            summary = {**item, "state": "NO_REPORT", "report_at": None,
                       "received_at": None, "report_sequence": None,
                       "policy_sequence": None, "policy_sha256": None,
                       "published_sequence": None, "published_sha256": None,
                       "attestation": None, "probe": None,
                       "dns_applied": None, "lan_verified": False, "metrics": None, "report_format": None}
            state = None
            try:
                state = _owned_file(self._path(item["device_id"]), MAX_RECEIPT_BYTES)
                if (type(state) is not dict or type(state.get("signed")) is not dict):
                    raise NodeError("invalid node receipt")
                if state["signed"].get("key_id") != item["key_id"]:
                    raise _RetiredNodeKey()
                reported = verify_report(canonical(state["signed"]),
                                         expected_device=item["device_id"],
                                         expected_key_id=item["key_id"],
                                         trust_dir=self.trust_dir,
                                         now=timestamp(state["received_at"], "received_at"))
                received = timestamp(state["received_at"], "received_at")
                summary.update(report_at=reported["reported_at"], received_at=state["received_at"],
                               report_sequence=reported["report_sequence"],
                               policy_sequence=reported["policy_sequence"],
                               policy_sha256=reported["policy_sha256"],
                               attestation=reported["attestation"], probe=reported["probe"],
                               metrics=reported.get("metrics"), report_format=reported["format"])
                report_at = timestamp(reported["reported_at"], "reported_at")
                if received > instant + timedelta(seconds=60) or report_at > instant + timedelta(seconds=60):
                    # Local clock regressions must not keep a future-dated report healthy.
                    summary["state"] = "CLOCK_SKEW"
                elif instant - received > REPORT_LIFETIME or instant - report_at > REPORT_LIFETIME:
                    summary["state"] = "STALE"
                elif reported["attestation"] == "NO_POLICY":
                    summary["state"] = "NO_POLICY"
                elif reported["attestation"] == "EXPIRED":
                    summary["state"] = "POLICY_EXPIRED"
                elif reported["attestation"] != "ATTESTED":
                    summary["state"] = "DNS_ATTESTATION_FAILED"
                elif reported["probe"]["domain"] is not None and (
                        reported["probe"]["udp"] is False or reported["probe"]["tcp"] is False):
                    summary["state"] = "LOCAL_DNS_PROBE_FAILED"
                else:
                    summary["state"] = "NODE_ATTESTED"
            except FileNotFoundError:
                pass
            except _RetiredNodeKey:
                summary["state"] = "REKEY_PENDING"
            except (OSError, ValueError, KeyError, TypeError):
                summary["state"] = "INVALID_REPORT"
            published = deployment(item["device_id"])
            comparable = published["state"] in ("SIGNED_FILE_VERIFIED", "PUBLICATION_EXPIRED")
            if comparable:
                summary["published_sequence"] = published["sequence"]
                summary["published_sha256"] = published["policy_sha256"]
            same = (comparable and summary["policy_sequence"] is not None and
                    summary["policy_sequence"] == published["sequence"] and
                    summary["policy_sha256"] == published["policy_sha256"])
            if published["state"] == "SIGNED_FILE_VERIFIED" and summary["state"] == "NODE_ATTESTED":
                if same:
                    local = summary["probe"]
                    if local is None or local["domain"] is None:
                        summary["state"] = "LOCAL_POLICY_ATTESTED"
                    elif reported["format"] < 2 or local["baseline"] is None:
                        # Pre-v2 reports and unconfigured upstream references
                        # cannot prove that NXDOMAIN was caused by this policy.
                        summary["state"] = "LOCAL_DNS_UNCORROBORATED"
                    elif local["baseline"] is False:
                        summary["state"] = "LOCAL_DNS_REFERENCE_UNVERIFIED"
                    else:
                        summary["state"] = "LOCAL_DNS_VERIFIED"
                    summary["dns_applied"] = True
                else:
                    summary["state"] = "POLICY_MISMATCH"
                    summary["dns_applied"] = False
            elif published["state"] == "PUBLICATION_EXPIRED" and summary["state"] in (
                    "NODE_ATTESTED", "DNS_ATTESTATION_FAILED", "POLICY_EXPIRED"):
                # Expiry is not a current attestation. Collectors that predate
                # the EXPIRED status report FAILED when the inbox is past valid_until.
                if same:
                    summary["state"] = "POLICY_EXPIRED"
                    summary["dns_applied"] = None
                elif summary["policy_sequence"] is not None:
                    summary["state"] = "POLICY_MISMATCH"
                    summary["dns_applied"] = False
            elif (summary["state"] == "POLICY_EXPIRED" and
                    published["state"] == "SIGNED_FILE_VERIFIED" and not same and
                    summary["policy_sequence"] is not None):
                summary["state"] = "POLICY_MISMATCH"
                summary["dns_applied"] = False
            elif summary["state"] == "NODE_ATTESTED":
                summary["state"] = "PUBLISHER_UNVERIFIED"
            result.append(summary)
        return result
