"""Root-only signed publication with a durable journal and verified local receipts.

The signature authorizes NEW input. A root-owned receipt binds the full previously
verified envelope, so revoking an old key does not deadlock an explicit rotation.
Only current.json is served; receipts/journals are private administrative state.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

from aleph_policy_sync.snapshot import (
    MAX_ENVELOPE_BYTES, canonical, device_id, seq, strict_load, verify_envelope,
    _regular_read,
)
from dns_agent.policy import parse_policy, timestamp


class PromotionError(ValueError):
    """Publication needs an authorized correction or a retry of its prepared release."""


def _read(path: Path, limit=MAX_ENVELOPE_BYTES, *, owned=False, private=False):
    return _regular_read(path, limit, forbidden=0o077 if private else 0o022,
                         owner=os.geteuid() if owned else None)


def _optional(path, *, limit=MAX_ENVELOPE_BYTES, private=False):
    try:
        return strict_load(_read(path, limit, owned=True, private=private), limit=limit)
    except FileNotFoundError:
        return None


def _digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def _fsync_dir(folder):
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, data: bytes, mode=0o644):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise PromotionError('unsafe current or state file')
    fd, temp = tempfile.mkstemp(prefix='.pending-release-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as file:
            os.fchmod(file.fileno(), mode)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _folder(feed_root, device):
    folder = Path(feed_root).absolute() / device
    # Inspect components without resolve(): resolving first hides symlink traversal.
    for directory in (folder, *folder.parents):
        info = directory.lstat()
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022 and not sticky_root):
            raise PromotionError('untrusted publication directory or ancestor')
    info = folder.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise PromotionError('feed directory must be owned by publisher and not writable by others')
    return folder


@contextmanager
def _lock(folder):
    fd = os.open(folder / '.publish.lock',
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise PromotionError('unsafe publication lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PromotionError('another publication is in progress') from None
        yield
    finally:
        os.close(fd)


def _receipt(envelope):
    payload = envelope['payload']
    return {'format': 2, 'sequence': payload['sequence'], 'key_id': envelope['key_id'],
            'payload_sha256': _digest(payload), 'envelope_sha256': _digest(envelope)}


def _valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _validate_receipt(state):
    if state is None:
        return
    legacy = {'sequence', 'payload_sha256'}
    current = legacy | {'format', 'key_id', 'envelope_sha256'}
    if type(state) is not dict or set(state) not in (legacy, current):
        raise PromotionError('invalid publisher receipt')
    seq(state['sequence'])
    if not _valid_hash(state['payload_sha256']):
        raise PromotionError('invalid publisher receipt digest')
    if set(state) == current and (type(state['format']) is not int or state['format'] != 2
            or not _valid_hash(state['key_id']) or not _valid_hash(state['envelope_sha256'])):
        raise PromotionError('invalid publisher receipt format')


def _previous(envelope, state, *, device, trusted_keys, now):
    _validate_receipt(state)
    if envelope is None:
        if state is not None:
            raise PromotionError('published snapshot missing; preserve receipt and restore the exact release')
        return None, None
    if state is not None and state.get('format') == 2:
        # Receipt is a local root decision, not remote input or a substitute for
        # verifying the new signature. It remains valid when an old key is revoked.
        if _digest(envelope) != state['envelope_sha256']:
            raise PromotionError('published snapshot and receipt disagree')
        payload = envelope['payload']
        policy = parse_policy(canonical(payload['policy']), now=now)
        if (payload['device_id'] != device or envelope['key_id'] != state['key_id']
                or policy.digest != payload['policy_sha256']):
            raise PromotionError('published receipt identity mismatch')
    else:
        # Legacy receipts did not bind the signer/envelope. Migrate only while
        # the old signature can still be verified; never silently trust a file.
        payload, policy = verify_envelope(canonical(envelope), expected_device=device,
                                         trust_dir=trusted_keys, now=now, allow_expired=True)
    if state is not None and (payload['sequence'] != state['sequence']
                             or _digest(payload) != state['payload_sha256']):
        raise PromotionError('published snapshot and receipt disagree')
    return payload, policy


def _recover(folder, journal, envelope, *, device, trusted_keys, now, apply):
    fields = {'format', 'envelope', 'before_current_sha256', 'before_receipt_sha256'}
    if (type(journal) is not dict or set(journal) != fields
            or type(journal['format']) is not int or journal['format'] != 1
            or any(value is not None and not _valid_hash(value)
                   for value in (journal['before_current_sha256'], journal['before_receipt_sha256']))):
        raise PromotionError('invalid publication journal; preserve for inspection')
    if canonical(journal['envelope']) != canonical(envelope):
        raise PromotionError('unfinished publication; retry its original signed release first')
    payload, policy = verify_envelope(canonical(envelope), expected_device=device,
                                     trust_dir=trusted_keys, now=now, allow_expired=True)
    current = _optional(folder / 'current.json')
    state = _optional(folder / '.publication.json', limit=4096, private=True)
    _validate_receipt(state)
    current_hash = _digest(current) if current is not None else None
    state_hash = _digest(state) if state is not None else None
    receipt = _receipt(envelope)
    new_current, new_state = _digest(envelope), _digest(receipt)
    if (current_hash not in (journal['before_current_sha256'], new_current)
            or state_hash not in (journal['before_receipt_sha256'], new_state)
            or state_hash == new_state and current_hash != new_current):
        raise PromotionError('journal and publication state disagree; refuse rollback or overwrite')
    expired = policy.expires_at <= now
    result = {'device': device, 'sequence': payload['sequence'], 'published': False,
              'recovered': False, 'recovery_pending': True, 'expired': expired,
              'active_blocks': len(policy.blocked(now))}
    if not apply:
        return result
    if expired and current_hash != new_current:
        # This intent was never served. Aborting it cannot roll back a published
        # sequence or prolong a threat verdict. Keep previous policy and receipt.
        (folder / '.pending-publication.json').unlink()
        _fsync_dir(folder)
        raise PromotionError('prepared release expired before publication; discarded intent, generate a fresh release')
    if current_hash != new_current:
        _write(folder / 'current.json', canonical(envelope) + b'\n')
    if state_hash != new_state:
        _write(folder / '.publication.json', canonical(receipt) + b'\n', mode=0o600)
    (folder / '.pending-publication.json').unlink()
    _fsync_dir(folder)
    return {**result, 'published': not expired, 'recovered': True, 'recovery_pending': False}


def promote(*, release: Path, feed_root: Path, trusted_keys: Path, device: str,
            apply=False, acknowledge_withdrawals=False, acknowledge_key_rotation=False,
            now: datetime | None = None):
    device = device_id(device)
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise PromotionError('timezone-aware publication time required')
    if apply and os.geteuid() != 0:
        raise PromotionError('promotion requires root; signing must be non-root')
    folder = _folder(feed_root, device)
    with (_lock(folder) if apply else nullcontext()):
        envelope = strict_load(_read(Path(release)))
        pending = _optional(folder / '.pending-publication.json',
                            limit=MAX_ENVELOPE_BYTES + 4096, private=True)
        if pending is not None:
            return _recover(folder, pending, envelope, device=device, trusted_keys=trusted_keys,
                            now=instant, apply=apply)
        incoming, policy = verify_envelope(canonical(envelope), expected_device=device,
                                          trust_dir=trusted_keys, now=instant)
        current = _optional(folder / 'current.json')
        state = _optional(folder / '.publication.json', limit=4096, private=True)
        old, prior_policy = _previous(current, state, device=device,
                                      trusted_keys=trusted_keys, now=instant)
        if old and incoming['sequence'] <= old['sequence']:
            if (incoming['sequence'] == old['sequence']
                    and canonical(envelope) == canonical(current)):
                return {'device': device, 'sequence': incoming['sequence'],
                        'published': False, 'already_published': True,
                        'active_blocks': len(policy.blocked(instant))}
            raise PromotionError('stale or conflicting publication sequence')
        if old and timestamp(old['policy']['issued_at'], 'old.issued_at') >= policy.issued_at:
            raise PromotionError('new snapshot must have later issuance time')
        if current and current['key_id'] != envelope['key_id'] and acknowledge_key_rotation is not True:
            raise PromotionError('signer rotation needs explicit acknowledgement')
        before = set(prior_policy.blocked(instant)) if prior_policy else set()
        after = set(policy.blocked(instant))
        old_until = {r.domain: r.expires_at for r in prior_policy.rules} if prior_policy else {}
        shortened = sorted(r.domain for r in policy.rules
                           if r.domain in before & after and r.expires_at < old_until[r.domain])
        removed = sorted(before - after)
        if (removed or shortened) and acknowledge_withdrawals is not True:
            raise PromotionError('active block removal or shorter lifetime requires --ack-withdrawals')
        summary = {'device': device, 'sequence': incoming['sequence'],
                   'added_blocks': sorted(after - before), 'withdrawn_blocks': removed,
                   'shortened_blocks': shortened, 'active_blocks': len(after), 'published': False}
        if apply:
            journal = {'format': 1, 'envelope': envelope,
                       'before_current_sha256': _digest(current) if current is not None else None,
                       'before_receipt_sha256': _digest(state) if state is not None else None}
            # Persist authorized intent BEFORE public output. The private journal
            # makes every interrupted write retryable without reauthorizing data.
            _write(folder / '.pending-publication.json', canonical(journal) + b'\n', mode=0o600)
            completed = _recover(folder, journal, envelope, device=device,
                                 trusted_keys=trusted_keys, now=instant, apply=True)
            return {**summary, **completed, 'recovered': False}
        return summary
