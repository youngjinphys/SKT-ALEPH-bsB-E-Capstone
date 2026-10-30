"""Signed ALEPH policy snapshots: independent of DNS query execution.

This is a deliberately small single-signer format, NOT an implementation of TUF.
The TLS client, trust anchor and monotonic local state must be configured by an
operator. Signing private keys never belong on a DNS node or public web root.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from dns_agent.policy import MAX_BYTES as MAX_POLICY_BYTES, PolicyError, parse_policy, timestamp

MAX_ENVELOPE_BYTES = 2 * 1024 * 1024
MAX_SEQUENCE = (1 << 63) - 1
DEVICE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
KEY_ID = re.compile(r"[0-9a-f]{64}\Z")
SIG = re.compile(r"[A-Za-z0-9_-]{86}\Z")


class SnapshotError(ValueError):
    """Invalid, untrusted or stale signed policy artifact."""


def now_utc():
    return datetime.now(timezone.utc)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise SnapshotError("duplicate JSON key")
        obj[k] = v
    return obj


def _constant(_):
    raise SnapshotError("non-finite JSON value")


def strict_load(raw: bytes, *, limit=MAX_ENVELOPE_BYTES):
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise SnapshotError("snapshot size limit exceeded")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SnapshotError("invalid snapshot JSON") from exc


def fields(obj, expected, label):
    if type(obj) is not dict or set(obj) != set(expected):
        raise SnapshotError(f"{label}: invalid or missing keys")


def device_id(value):
    if not isinstance(value, str) or not DEVICE_ID.fullmatch(value):
        raise SnapshotError("invalid device ID")
    return value


def seq(value):
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        raise SnapshotError("sequence must be a positive 63-bit integer")
    return value


def _regular_read(path: Path, limit: int, *, forbidden=0o022, owner=None):
    """No symlink traversal at the final component; no special device reads."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_mode & forbidden
                or owner is not None and info.st_uid != owner):
            raise SnapshotError("untrusted file ownership or mode")
        with os.fdopen(os.dup(fd), "rb") as stream:
            result = stream.read(limit + 1)
        if len(result) > limit:
            raise SnapshotError("file size limit exceeded")
        return result
    finally:
        os.close(fd)


def public_key_id(key):
    raw = key.public_bytes(encoding=serialization.Encoding.Raw,
                           format=serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def load_private_key(path: Path):
    raw = _regular_read(path, 16384, forbidden=0o077, owner=os.geteuid())
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (TypeError, ValueError) as exc:
        raise SnapshotError("invalid Ed25519 signing key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise SnapshotError("signing key must be Ed25519")
    return key


def load_public_key(path: Path):
    raw = _regular_read(path, 8192, forbidden=0o022, owner=(0 if os.geteuid() == 0 else None))
    try:
        key = serialization.load_pem_public_key(raw)
    except (ValueError, TypeError) as exc:
        raise SnapshotError("invalid public key") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise SnapshotError("trusted key must be Ed25519")
    return key


def trust_key(trust_dir: Path, key_id: str):
    if not KEY_ID.fullmatch(key_id):
        raise SnapshotError("invalid signing key ID")
    if trust_dir.is_symlink():
        raise SnapshotError("unsafe trust directory")
    info = trust_dir.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
            or os.geteuid() == 0 and info.st_uid != 0):
        raise SnapshotError("unsafe trusted key directory")
    key = load_public_key(trust_dir / (key_id + ".pem"))
    if public_key_id(key) != key_id:
        raise SnapshotError("trusted key fingerprint mismatch")
    return key


def sign_policy(raw_policy: bytes, key: Ed25519PrivateKey, *, target: str,
                sequence: int, signed_at=None, confirm_empty=False):
    target = device_id(target)
    seq(sequence)
    when = signed_at or now_utc()
    try:
        policy = parse_policy(raw_policy, now=when)
        obj = strict_load(raw_policy, limit=MAX_POLICY_BYTES)
    except (ValueError, PolicyError) as exc:
        raise SnapshotError("policy failed current ALEPH contract") from exc
    if policy.expires_at <= when:
        raise SnapshotError("cannot sign expired policy")
    if not obj["rules"] and not confirm_empty:
        raise SnapshotError("empty replacement requires --confirm-empty")
    intent = "withdraw_all" if not obj["rules"] else "replace"
    payload = {
        "format": 1,
        "type": "aleph-signed-policy",
        "device_id": target,
        "sequence": sequence,
        "signed_at": when.isoformat(),
        "valid_until": policy.expires_at.isoformat(),
        "policy_sha256": policy.digest,
        "intent": intent,
        "policy": obj,
    }
    signature = key.sign(canonical(payload))
    envelope = {
        "payload": payload,
        "key_id": public_key_id(key.public_key()),
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }
    if len(canonical(envelope)) > MAX_ENVELOPE_BYTES:
        raise SnapshotError("signed envelope size exceeded")
    return envelope


def verify_envelope(raw: bytes, *, expected_device: str, trust_dir: Path, now=None,
                    allow_expired=False):
    expected_device = device_id(expected_device)
    instant = now or now_utc()
    envelope = strict_load(raw)
    fields(envelope, ("payload", "key_id", "signature"), "envelope")
    payload = envelope["payload"]
    fields(payload, ("format", "type", "device_id", "sequence", "signed_at",
                     "valid_until", "policy", "policy_sha256", "intent"), "payload")
    if type(payload["format"]) is not int or payload["format"] != 1:
        raise SnapshotError("unsupported signed snapshot format")
    if payload["type"] != "aleph-signed-policy":
        raise SnapshotError("unsupported artifact type")
    if device_id(payload["device_id"]) != expected_device:
        raise SnapshotError("signed snapshot targets a different device")
    seq(payload["sequence"])
    if not isinstance(envelope["signature"], str) or not SIG.fullmatch(envelope["signature"]):
        raise SnapshotError("malformed Ed25519 signature encoding")
    if not isinstance(envelope["key_id"], str):
        raise SnapshotError("invalid signer ID")
    key = trust_key(Path(trust_dir), envelope["key_id"])
    try:
        signature = base64.urlsafe_b64decode(envelope["signature"] + "==")
        key.verify(signature, canonical(payload))
    except (ValueError, InvalidSignature) as exc:
        raise SnapshotError("snapshot signature invalid") from exc
    signed_at = timestamp(payload["signed_at"], "signed_at")
    valid_until = timestamp(payload["valid_until"], "valid_until")
    if signed_at > instant + timedelta(seconds=60) or (valid_until <= instant and not allow_expired):
        raise SnapshotError("future-dated or expired signed snapshot")
    if not signed_at < valid_until:
        raise SnapshotError("invalid signature validity interval")
    if type(payload["policy"]) is not dict:
        raise SnapshotError("policy must be a JSON object")
    try:
        parsed = parse_policy(canonical(payload["policy"]), now=instant)
    except (PolicyError, ValueError, TypeError) as exc:
        raise SnapshotError("signed policy invalid") from exc
    if (parsed.digest != payload["policy_sha256"]
            or parsed.expires_at != valid_until):
        raise SnapshotError("policy digest or expiration mismatch")
    if payload["intent"] not in ("replace", "withdraw_all"):
        raise SnapshotError("invalid signed intent")
    if (payload["intent"] == "withdraw_all") != (not bool(parsed.rules)):
        raise SnapshotError("empty policy is missing explicit signed withdrawal intent")
    return payload, parsed
