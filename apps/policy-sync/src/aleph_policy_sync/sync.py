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
    prior = read_state(meta, owner=os.geteuid(), optional=True)
    old_etag = _etag(prior)
    old_raw = None
    if prior and current.exists():
        old_raw = _regular_read(current, MAX_ENVELOPE_BYTES, forbidden=0o077,
                                owner=os.geteuid())
        if hashlib.sha256(old_raw).hexdigest() != prior["envelope_sha256"]:
            # Crash between atomic inbox and metadata writes. Force a full
            # download instead of permanently deadlocking future updates.
            old_raw, old_etag, old_payload = None, None, None
        else:
            try:
                # An expired but once-valid snapshot must not stop fetching
                # its successor. Never use an ETag for an expired snapshot.
                old_payload, _ = verify_envelope(old_raw, expected_device=device,
                                                 trust_dir=trust_dir, now=now,
                                                 allow_expired=True)
                expiry = datetime.fromisoformat(old_payload["valid_until"])
                if expiry <= (now or now_utc()):
                    old_etag = None
            except SnapshotError:
                # Key rotation can revoke a signer; force a fresh download.
                old_raw, old_etag, old_payload = None, None, None
    else:
        old_etag, old_payload = None, None
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
        if exc.code == 304:
            if old_raw is None or old_etag is None:
                raise SyncError("unexpected 304 without a valid conditional request") from exc
            return "not-modified"
        raise SyncError(f"policy download HTTP error {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SyncError("policy HTTPS download failed") from exc
    if len(blob) > MAX_ENVELOPE_BYTES:
        raise SyncError("HTTP policy exceeds maximum size")
    payload, _ = verify_envelope(blob, expected_device=device, trust_dir=trust_dir, now=now)
    if prior is not None and old_raw is not None:
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
    path = Path(path).absolute()
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


def _apply_locked(*, device: str, trust_dir: Path, inbox_dir: Path,
               fetch_user: str, state_dir: Path, dns_admin: Path, now=None,
               publisher=None):
    """Root-only: reverify the signed input, publish, THEN persist replay watermark.

    Never performs HTTP requests; rejects snapshots below the last good sequence.
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
    previous = read_state(metadata_path, owner=0, optional=True)
    digest = hashlib.sha256(canonical(payload)).hexdigest()
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
        if payload["sequence"] == prior_seq:
            if (digest != previous["payload_sha256"]
                    or policy.digest != previous["policy_sha256"]):
                raise SyncError("conflicting policy at same signed sequence")
            return "already-applied"  # No root publish and no expiry extension.
    # The policy applied by the signed producer is always canonicalised before
    # invoking existing trusted DNS publish machinery.
    candidate = dest / "pending-policy.json"
    atomic_private(candidate, canonical(payload["policy"]) + b"\n", owner=0)
    if publisher is None:
        _locked_publish(dns_admin, candidate)
    else:
        publisher(candidate)  # dependency injection only for offline tests
    accepted = {"sequence":payload["sequence"], "payload_sha256":digest,
                "policy_sha256":policy.digest, "applied_at":(now or now_utc()).isoformat()}
    atomic_private(metadata_path, canonical(accepted) + b"\n", owner=0)
    candidate.unlink()
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
               publisher=None):
    if os.geteuid() != 0:
        raise SyncError("apply must run as root")
    folder = owner_dir(state_dir, 0, create=True)
    with file_lock(folder, owner=0):
        return _apply_locked(device=device, trust_dir=trust_dir, inbox_dir=inbox_dir,
                             fetch_user=fetch_user, state_dir=folder,
                             dns_admin=dns_admin, now=now, publisher=publisher)
