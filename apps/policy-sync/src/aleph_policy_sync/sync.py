"""Unprivileged HTTPS fetcher and separate root-only verified policy apply.

There is NO remote API or database access in the DNS resolution process. Fetch
cannot publish, and apply cannot make HTTP requests. Both verify Ed25519.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import ssl
import stat
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (HTTPSHandler, HTTPRedirectHandler, ProxyHandler,
                            Request, build_opener)

from dns_agent.policy import timestamp

from .snapshot import (MAX_ENVELOPE_BYTES, SnapshotError, canonical, device_id,
                       now_utc, strict_load, verify_envelope, _regular_read)


class SyncError(RuntimeError):
    """Policy download, validation, persistence or application failed."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def validate_https_url(url: str):
    if not isinstance(url, str) or len(url) > 2048:
        raise SyncError("invalid policy endpoint")
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.fragment or parts.query
                or not parts.path.startswith("/") or parts.port is not None and not 1 <= parts.port <= 65535):
            raise ValueError("not a pinned HTTPS policy endpoint")
        if any(ord(c) < 33 or ord(c) > 126 for c in url):
            raise ValueError("invalid URL characters")
    except (ValueError, TypeError) as exc:
        raise SyncError("policy endpoint must be explicit HTTPS URL without credentials, query or fragment") from exc
    return url


def owner_dir(path: Path, owner_uid: int, *, create=False):
    path = Path(path).absolute()
    if path.is_symlink():
        raise SyncError("state directory must not be a symlink")
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    st = path.stat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != owner_uid
            or st.st_mode & 0o077):
        raise SyncError("state directory owner/mode must be 0700 for its service account")
    return path


def atomic_private(path: Path, data: bytes, *, owner: int):
    if not isinstance(data, bytes) or len(data) > MAX_ENVELOPE_BYTES:
        raise SyncError("data exceeds signed snapshot size bound")
    directory = owner_dir(path.parent, owner)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SyncError("unsafe state file destination")
    temp = None
    fd = None
    try:
        fd, temp = tempfile.mkstemp(prefix=".aleph-stage-", dir=directory)
        os.fchmod(fd, 0o600)
        if os.fstat(fd).st_uid != owner:
            raise SyncError("temporary file owner mismatch")
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        temp = None
        fsd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fsd)
        finally:
            os.close(fsd)
    finally:
        if fd is not None:
            os.close(fd)
        if temp is not None:
            os.unlink(temp)



@contextmanager
def file_lock(directory: Path, *, owner: int):
    """Serialize the entire fetch or root apply transaction, not just the write."""
    directory = owner_dir(directory, owner)
    fd = os.open(directory / "sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & 0o077:
            raise SyncError("unsafe policy transaction lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncError("another policy sync transaction is active") from exc
        yield
    finally:
        os.close(fd)


def read_state(path: Path, *, owner, optional=False, limit=2048):
    try:
        raw = _regular_read(path, limit, forbidden=0o077, owner=owner)
    except FileNotFoundError:
        if optional:
            return None
        raise
    return strict_load(raw, limit=limit)


def _etag(state):
    if state is None:
        return None
    if not isinstance(state, dict) or set(state) != {"etag", "envelope_sha256"}:
        raise SyncError("invalid fetch metadata")
    etag = state["etag"]
    if etag is not None and (not isinstance(etag, str) or len(etag) > 200
                            or any(ord(c) < 33 or ord(c) > 126 for c in etag)):
        raise SyncError("invalid HTTP ETag")
    if not isinstance(state["envelope_sha256"], str) or not re.fullmatch("[0-9a-f]{64}", state["envelope_sha256"]):
        raise SyncError("invalid fetch digest")
    return etag



def _read_fetch_metadata(path: Path):
    """HTTP hints are disposable, unlike root replay/application receipts.

    Fail closed on unsafe file ownership, symlinks, oversized data or I/O
    errors. Only bounded JSON/metadata-format damage permits a full fetch.
    """
    try:
        raw = _regular_read(path, 2048, forbidden=0o077, owner=os.geteuid())
    except FileNotFoundError:
        return None
    try:
        value = strict_load(raw, limit=2048)
        _etag(value)
        return value
    except (SnapshotError, SyncError):
        return None


def _fetch_locked(*, url: str, device: str, trust_dir: Path, inbox_dir: Path,
               ca_file: Path | None = None, token_file: Path | None = None,
               timeout=8, now=None):
    """No root and no publish: only atomically stage a verified signed document."""
    if os.geteuid() == 0:
        raise SyncError("fetch must not run as root")
    url = validate_https_url(url)
    device = device_id(device)
    folder = owner_dir(inbox_dir, os.geteuid(), create=True)
    current = folder / "current.json"
    meta = folder / "fetch-state.json"
    prior = _read_fetch_metadata(meta)
    old_etag = None
    old_raw, old_payload = None, None
    try:
        old_raw = _regular_read(current, MAX_ENVELOPE_BYTES, forbidden=0o077,
                                owner=os.geteuid())
    except FileNotFoundError:
        pass
    if old_raw is not None:
        try:
            # The signature, not a disposable HTTP sidecar, authenticates the
            # cached sequence. Keep its rollback bound even after a torn write.
            old_payload, _ = verify_envelope(old_raw, expected_device=device,
                                             trust_dir=trust_dir, now=now,
                                             allow_expired=True)
        except (SnapshotError, FileNotFoundError):
            # An invalid or retired cached signer cannot authorize any successor.
            # The freshly downloaded envelope must pass independent verification.
            old_raw, old_payload = None, None
        else:
            if (prior is not None
                    and hashlib.sha256(old_raw).hexdigest() == prior["envelope_sha256"]
                    and timestamp(old_payload["valid_until"], "valid_until") > (now or now_utc())):
                old_etag = _etag(prior)
    headers = {"Accept": "application/json", "Accept-Encoding": "identity",
               "Cache-Control": "no-cache", "User-Agent": "ALEPH-PolicySync/1"}
    if old_etag:
        headers["If-None-Match"] = old_etag
    if token_file is not None:
        token = _regular_read(Path(token_file), 2048, forbidden=0o077,
                              owner=os.geteuid()).decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9._~+/-]{12,1024}", token):
            raise SyncError("invalid bearer token file")
        headers["Authorization"] = "Bearer " + token
    context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    request = Request(url, headers=headers, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise SyncError("unexpected HTTPS response status")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise SyncError("compressed snapshot response is unsupported")
            blob = response.read(MAX_ENVELOPE_BYTES + 1)
            new_etag = response.headers.get("ETag")
    except HTTPError as exc:
        try:
            if exc.code == 304:
                if old_raw is None or old_etag is None:
                    raise SyncError("unexpected 304 without a valid conditional request") from exc
                # A matching HTTP ETag does not renew signature validity or trust.
                # Recheck at response time: the policy may have expired or its
                # signing key may have been removed while HTTPS was in flight.
                verify_envelope(old_raw, expected_device=device,
                                trust_dir=trust_dir, now=now)
                return "not-modified"
            raise SyncError(f"policy download HTTP error {exc.code}") from exc
        finally:
            exc.close()
    except (URLError, TimeoutError, OSError) as exc:
        raise SyncError("policy HTTPS download failed") from exc
    if len(blob) > MAX_ENVELOPE_BYTES:
        raise SyncError("HTTP policy exceeds maximum size")
    payload, _ = verify_envelope(blob, expected_device=device, trust_dir=trust_dir, now=now)
    if old_payload is not None:
        if payload["sequence"] < old_payload["sequence"]:
            raise SyncError("downloaded policy sequence rollback")
        if (payload["sequence"] == old_payload["sequence"]
                and canonical(payload) != canonical(old_payload)):
            raise SyncError("same sequence with conflicting signed payload")
    if new_etag is not None and (len(new_etag) > 200 or
                                 any(ord(c) < 33 or ord(c) > 126 for c in new_etag)):
        raise SyncError("invalid HTTPS ETag")
    atomic_private(current, blob, owner=os.geteuid())
    atomic_private(meta, canonical({"etag":new_etag,
                                    "envelope_sha256":hashlib.sha256(blob).hexdigest()}) + b"\n",
                   owner=os.geteuid())
    return "downloaded"


def _safe_root_program(path: Path):
    path = Path(path)
    if not path.is_absolute():
        raise SyncError("administrator program path must be absolute")
    for directory in (path.parent, *path.parents):
        st = directory.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise SyncError("administrator program has untrusted ancestor")
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        raise SyncError("administrator program is not root owned")
    return path


def _locked_publish(script: Path, candidate: Path):
    """Invoke only a root-owned ALEPH installer publish subcommand."""
    program = _safe_root_program(script)
    try:
        subprocess.run(["/usr/bin/python3", "-B", str(program), "publish", "--policy", str(candidate)],
                       check=True, timeout=30, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       env={"PATH":"/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE":"1"})
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise SyncError("ALEPH DNS publish failed; inspect DNS service and publication journal") from exc


def _locked_attest(script: Path, digest: str):
    """Read-only root DNS attestation; never re-publish on a replay."""
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SyncError("invalid expected DNS policy digest")
    program = _safe_root_program(script)
    try:
        subprocess.run(["/usr/bin/python3", "-B", str(program), "attest",
                        "--policy-sha256", digest],
                       check=True, timeout=30, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise SyncError("DNS no longer attests the signed policy; inspect DNS service") from exc


def _intent(payload, policy, digest):
    """Small durable pre-publish journal. Not a committed replay watermark."""
    return {"format": 1, "sequence": payload["sequence"],
            "payload_sha256": digest, "policy_sha256": policy.digest}


def _checked_intent(value):
    if (type(value) is not dict or set(value) !=
            {"format", "sequence", "payload_sha256", "policy_sha256"}
            or type(value["format"]) is not int or value["format"] != 1
            or type(value["sequence"]) is not int
            or not 1 <= value["sequence"] <= (1 << 63) - 1
            or any(not isinstance(value[k], str) or
                   re.fullmatch(r"[0-9a-f]{64}", value[k]) is None
                   for k in ("payload_sha256", "policy_sha256"))):
        raise SyncError("invalid pending signed-policy intent")
    return value


def _attest_policy(admin, digest, attestor):
    if attestor is None:
        _locked_attest(admin, digest)
    else:
        attestor(digest)


def _delete_intent(path):
    if path.is_symlink():
        raise SyncError("unsafe pending intent symlink")
    path.unlink()
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _apply_locked(*, device: str, trust_dir: Path, inbox_dir: Path,
               fetch_user: str, state_dir: Path, dns_admin: Path, now=None,
               publisher=None, attestor=None):
    """Prepare a durable intent, publish, then commit the replay watermark.

    The journal is not evidence of a successful publish. A failed metadata
    write is retryable only with the identical signed input; a different
    release must not silently supersede a possibly-applied predecessor.
    """
    if os.geteuid() != 0:
        raise SyncError("apply must run as root")
    device = device_id(device)
    if not isinstance(fetch_user, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", fetch_user):
        raise SyncError("invalid download service user")
    uid = pwd.getpwnam(fetch_user).pw_uid
    if uid == 0:
        raise SyncError("fetch user must be unprivileged")
    folder = owner_dir(inbox_dir, uid)
    raw = _regular_read(folder / "current.json", MAX_ENVELOPE_BYTES,
                        forbidden=0o077, owner=uid)
    payload, policy = verify_envelope(raw, expected_device=device, trust_dir=trust_dir, now=now)
    dest = owner_dir(state_dir, 0, create=True)
    metadata_path = dest / "applied.json"
    pending_path = dest / "pending-apply.json"
    candidate = dest / "pending-policy.json"
    previous = read_state(metadata_path, owner=0, optional=True)
    pending = read_state(pending_path, owner=0, optional=True)
    if pending is not None:
        pending = _checked_intent(pending)
    digest = hashlib.sha256(canonical(payload)).hexdigest()
    incoming = _intent(payload, policy, digest)
    attested_prior = False
    if previous is not None:
        if (not isinstance(previous, dict) or
            set(previous) != {"sequence", "payload_sha256", "policy_sha256", "applied_at"}):
            raise SyncError("invalid replay watermark")
        prior_seq = previous["sequence"]
        if type(prior_seq) is not int or not 1 <= prior_seq <= (1 << 63)-1:
            raise SyncError("invalid stored sequence")
        if any(not isinstance(previous[k], str) or
               not re.fullmatch(r"[0-9a-f]{64}", previous[k])
               for k in ("payload_sha256", "policy_sha256")):
            raise SyncError("invalid stored digests")
        try:
            seen = timestamp(previous["applied_at"], "applied_at")
        except (ValueError, TypeError) as exc:
            raise SyncError("invalid stored application clock") from exc
        if (now or now_utc()) < seen - timedelta(seconds=60):
            raise SyncError("local clock rollback detected")
        if payload["sequence"] < prior_seq:
            raise SyncError("signed policy rollback rejected")
        if pending is not None and pending["sequence"] == prior_seq:
            if (pending["payload_sha256"] != previous["payload_sha256"]
                    or pending["policy_sha256"] != previous["policy_sha256"]):
                raise SyncError("pending intent conflicts with recorded application")
            # Metadata was committed but cleanup interrupted. Do not discard
            # the journal without verifying the policy still active in DNS.
            _attest_policy(dns_admin, previous["policy_sha256"], attestor)
            attested_prior = True
            _delete_intent(pending_path)
            pending = None
        if payload["sequence"] == prior_seq:
            if (digest != previous["payload_sha256"]
                    or policy.digest != previous["policy_sha256"]):
                raise SyncError("conflicting policy at same signed sequence")
            if pending is not None:
                raise SyncError("another signed policy application is still pending")
            if not attested_prior:
                _attest_policy(dns_admin, policy.digest, attestor)
            return "already-applied"
    if pending is not None and pending != incoming:
        # The downloader may already have replaced an unfinished release with
        # a newer signed one. Recover what actually reached the live resolver,
        # rather than deadlocking solely because the old inbox has vanished.
        if (pending["sequence"] >= incoming["sequence"] or
                previous is not None and pending["sequence"] <= previous["sequence"]):
            raise SyncError("unfinished signed-policy application; retry the original release first")
        try:
            _attest_policy(dns_admin, pending["policy_sha256"], attestor)
        except SyncError as pending_error:
            if previous is None:
                raise SyncError("unfinished signed-policy application; no verified fallback DNS policy") from pending_error
            # A newer signed policy may replace an abandoned attempt only if
            # the previous recorded policy is demonstrably STILL active.
            _attest_policy(dns_admin, previous["policy_sha256"], attestor)
        else:
            # Publisher succeeded, but saving the old replay watermark failed.
            # Repair it from the durable root-owned intent before advancing.
            reconciled = {"sequence": pending["sequence"],
                          "payload_sha256": pending["payload_sha256"],
                          "policy_sha256": pending["policy_sha256"],
                          "applied_at": (now or now_utc()).isoformat()}
            atomic_private(metadata_path, canonical(reconciled) + b"\n", owner=0)
        _delete_intent(pending_path)
        pending = None
    if pending is None:
        # This record survives a publisher success followed by a failed local
        # watermark write. It also prevents a newer release from skipping the
        # recovery of an older partially-applied one.
        atomic_private(pending_path, canonical(incoming) + b"\n", owner=0)
    atomic_private(candidate, canonical(payload["policy"]) + b"\n", owner=0)
    if publisher is None:
        _locked_publish(dns_admin, candidate)
    else:
        publisher(candidate)  # dependency injection only for offline tests
    accepted = {"sequence": payload["sequence"], "payload_sha256": digest,
                "policy_sha256": policy.digest, "applied_at": (now or now_utc()).isoformat()}
    atomic_private(metadata_path, canonical(accepted) + b"\n", owner=0)
    # After the replay watermark is durably committed, leftover cleanup is
    # recoverable via the same-sequence live attestation path above.
    candidate.unlink()
    _delete_intent(pending_path)
    return "applied"


def fetch_once(*, url: str, device: str, trust_dir: Path, inbox_dir: Path,
               ca_file=None, token_file=None, timeout=8, now=None):
    if os.geteuid() == 0:
        raise SyncError("fetch must not run as root")
    folder = owner_dir(inbox_dir, os.geteuid(), create=True)
    with file_lock(folder, owner=os.geteuid()):
        return _fetch_locked(url=url, device=device, trust_dir=trust_dir,
                             inbox_dir=folder, ca_file=ca_file, token_file=token_file,
                             timeout=timeout, now=now)


def apply_once(*, device: str, trust_dir: Path, inbox_dir: Path,
               fetch_user: str, state_dir: Path, dns_admin: Path, now=None,
               publisher=None, attestor=None):
    if os.geteuid() != 0:
        raise SyncError("apply must run as root")
    folder = owner_dir(state_dir, 0, create=True)
    with file_lock(folder, owner=0):
        return _apply_locked(device=device, trust_dir=trust_dir, inbox_dir=inbox_dir,
                             fetch_user=fetch_user, state_dir=folder,
                             dns_admin=dns_admin, now=now,
                             publisher=publisher, attestor=attestor)
