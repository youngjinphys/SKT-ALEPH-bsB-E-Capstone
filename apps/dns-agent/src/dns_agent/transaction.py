"""Private state directory, exclusive lock, durable rollback journal and expiry.

Only the owned lab dnsmasq is controlled. This never edits /etc or system services.
"""
from __future__ import annotations
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from .policy import MAX_BYTES, PolicyError, parse_policy, render_config, timestamp, utcnow

class ApplyError(RuntimeError):
    """Candidate failed; previous live configuration has been restored."""

class RecoveryError(RuntimeError):
    """No trustworthy live state; stop and preserve recovery evidence."""

def read_regular(path: Path, limit: int = MAX_BYTES) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError('input must be a regular file')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise PolicyError('input size limit exceeded')
        return data
    finally:
        os.close(fd)

class Store:
    def __init__(self, directory: Path):
        self.path = Path(directory).absolute()
        self.lock_fd = None

    def __enter__(self):
        # Existing parents are operator-controlled. No symlink traversal allowed.
        for part in (self.path, *self.path.parents):
            if part.is_symlink():
                raise RuntimeError('state directory must not traverse symlinks')
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.path.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise RuntimeError('state directory must be owned by this user and mode 0700')
        fd = os.open(self.path/'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError('invalid lock file')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, RuntimeError) as exc:
            os.close(fd)
            raise RuntimeError('state lock unavailable or unsafe') from exc
        self.lock_fd = fd
        return self

    def __exit__(self, *_):
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    def _sync(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def write_text(self, name: str, text: str):
        if self.lock_fd is None:
            raise RuntimeError('write requires exclusive state lock')
        target = self.path/name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeError('unsafe state target')
        fd, temporary = tempfile.mkstemp(prefix='.candidate-', dir=self.path)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            self._sync()
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def write_json(self, name, obj):
        self.write_text(name, json.dumps(obj, ensure_ascii=True, sort_keys=True)+'\n')

    def remove(self, name):
        path = self.path/name
        if path.is_symlink():
            raise RuntimeError('unsafe state target')
        path.unlink(missing_ok=True)
        self._sync()

    @staticmethod
    def _check_snapshot(state):
        """Verify persisted policy and configuration digests before using them."""
        fields = {'policy', 'policy_sha256', 'config', 'config_sha256',
                  'applied_at', 'blocked_count'}
        if not isinstance(state, dict) or set(state) != fields:
            raise ValueError('unexpected saved-state structure')
        config, policy = state['config'], state['policy']
        if not isinstance(config, str) or not isinstance(policy, str):
            raise ValueError('saved policy and configuration must be text')
        cb, pb = config.encode('utf-8'), policy.encode('utf-8')
        if len(cb) > 2 * MAX_BYTES or len(pb) > MAX_BYTES:
            raise ValueError('saved snapshot size limit exceeded')
        if hashlib.sha256(cb).hexdigest() != state['config_sha256']:
            raise ValueError('saved configuration digest mismatch')
        if hashlib.sha256(pb).hexdigest() != state['policy_sha256']:
            raise ValueError('saved policy digest mismatch')
        if type(state['blocked_count']) is not int or not 0 <= state['blocked_count'] <= 10000:
            raise ValueError('invalid saved blocked count')
        timestamp(state['applied_at'], 'saved applied_at')

    def read_state(self):
        try:
            raw = read_regular(self.path/'state.json', 4*MAX_BYTES)
        except FileNotFoundError:
            return None
        try:
            state = json.loads(raw)
            self._check_snapshot(state)
            config = read_regular(self.path/'active.conf', 2*MAX_BYTES).decode('utf-8')
            if config != state['config']:
                raise ValueError('configuration differs from committed metadata')
            return state
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RecoveryError('state/config inconsistency; preserve evidence for inspection') from exc

    def restore(self, previous):
        if previous is None:
            self.remove('active.conf'); self.remove('state.json')
        else:
            self.write_text('active.conf', previous['config'])
            self.write_json('state.json', previous)

    def update_metadata(self, state):
        """Commit a new reviewed policy without bouncing an unchanged DNS listener."""
        previous = self.read_state()
        if previous is None or previous['config'] != state['config']:
            raise RecoveryError('metadata update requires the same active configuration')
        try:
            self.write_json('pending.json', {'previous': previous})
        except (OSError, RuntimeError) as exc:
            # No state/config changed; a full resolver outage would be unnecessary.
            raise ApplyError('metadata journal unavailable; previous DNS remains live') from exc
        try:
            self.write_json('state.json', state)
            self.remove('pending.json')
        except Exception as exc:
            try:
                self.restore(previous)
                self.remove('pending.json')
            except Exception as recovery:
                raise RecoveryError('metadata rollback failed; journal retained') from recovery
            raise ApplyError('metadata update failed; previous state restored') from exc

    def recover(self):
        try:
            raw = read_regular(self.path/'pending.json', 5*MAX_BYTES)
        except FileNotFoundError:
            return
        try:
            journal = json.loads(raw)
            if not isinstance(journal, dict) or set(journal) != {'previous'}:
                raise ValueError('unexpected recovery journal')
            previous = journal['previous']
            if previous is not None:
                self._check_snapshot(previous)
            self.restore(previous)
            self.remove('pending.json')
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            raise RecoveryError('interrupted transaction cannot be restored; journal retained') from exc

    def install(self, state, runtime):
        previous = self.read_state()
        # Staging or journaling errors must not stop a still-healthy live resolver.
        # None of these operations modifies the active configuration.
        try:
            self.write_text('candidate.conf', state['config'])
            runtime.validate(self.path/'candidate.conf')
        except Exception as exc:
            raise ApplyError('candidate preflight failed; existing DNS remains live') from exc
        finally:
            if (self.path/'candidate.conf').exists():
                try:
                    self.remove('candidate.conf')
                except (OSError, RuntimeError) as exc:
                    raise ApplyError('candidate cleanup failed; existing DNS remains live') from exc
        try:
            self.write_json('pending.json', {'previous': previous})
        except (OSError, RuntimeError) as exc:
            raise ApplyError('rollback journal write failed; existing DNS remains live') from exc
        try:
            runtime.stop()
            self.write_text('active.conf', state['config'])
            runtime.start(self.path/'active.conf')  # includes live UDP/TCP probe
            self.write_json('state.json', state)
        except Exception as exc:
            try:
                runtime.stop()
                self.restore(previous)
                if previous is not None:
                    runtime.start(self.path/'active.conf')
            except Exception as recovery:
                runtime.stop()
                raise RecoveryError('rollback failed; journal retained and owned service stopped') from recovery
            self.remove('pending.json')
            raise ApplyError('apply failed; previous state restored') from exc
        self.remove('pending.json')

class Agent:
    def __init__(self, store, runtime, *, port, upstream, upstream_port,
                 listen_address='127.0.0.1', system_dns=False,
                 http_sink_ip=None):
        self.store, self.runtime = store, runtime
        self.port, self.upstream, self.upstream_port = port, upstream, upstream_port
        self.listen_address = listen_address
        self.system_dns = system_dns
        self.http_sink_ip = http_sink_ip
        self.last_now = None
        store.recover()

    def cycle(self, raw: bytes | None, *, now: datetime | None = None):
        now = now or utcnow()
        previous = self.store.read_state()
        if previous:
            try:
                # Persisted watermark prevents old expired blocks from reviving on restart.
                now = max(now, timestamp(previous['applied_at'], 'stored applied_at'))
            except (KeyError, PolicyError) as exc:
                raise RecoveryError('saved clock watermark is missing or invalid') from exc
        if self.last_now is not None:
            now = max(now, self.last_now)
        self.last_now = now
        chosen = None
        if previous:
            try:
                chosen = parse_policy(previous['policy'].encode(), now=now)
            except (KeyError, PolicyError) as exc:
                raise RecoveryError('saved policy is not valid; refusing automatic restart') from exc
        rejected = None
        if raw is not None:
            try:
                incoming = parse_policy(raw, now=now)
                if chosen and (incoming.issued_at < chosen.issued_at or
                               (incoming.issued_at == chosen.issued_at and incoming.digest != chosen.digest)):
                    raise PolicyError('replayed timestamp or conflicting payload at same issuance')
                chosen = incoming
            except PolicyError as exc:
                rejected = str(exc)
        else:
            rejected = 'policy file unavailable'
        if chosen is None:
            raise ApplyError('no valid initial policy; service not started')
        blocked = chosen.blocked(now)
        config = render_config(blocked, port=self.port, upstream=self.upstream,
                               upstream_port=self.upstream_port,
                               listen_address=self.listen_address,
                               system_dns=self.system_dns,
                               warned=chosen.warned(now) if self.http_sink_ip else (),
                               http_sink_ip=self.http_sink_ip)
        state = {'policy': chosen.raw.decode(), 'config': config,
                 'policy_sha256': chosen.digest,
                 'config_sha256': hashlib.sha256(config.encode()).hexdigest(),
                 'applied_at': now.isoformat(), 'blocked_count': len(blocked)}
        config_changed = not previous or previous['config'] != config
        metadata_changed = not previous or previous['policy_sha256'] != chosen.digest
        restarted = config_changed or not self.runtime.healthy()
        if restarted:
            try:
                self.store.install(state, self.runtime)
            except ApplyError as exc:
                if previous:
                    old = parse_policy(previous['policy'].encode(), now=now)
                    fresh_old = render_config(old.blocked(now), port=self.port,
                                              upstream=self.upstream, upstream_port=self.upstream_port,
                                              listen_address=self.listen_address,
                                              system_dns=self.system_dns,
                                              warned=old.warned(now) if self.http_sink_ip else (),
                                              http_sink_ip=self.http_sink_ip)
                    if fresh_old != previous['config']:
                        self.runtime.stop()
                        raise RecoveryError('expired policy cannot be safely restored; service stopped') from exc
                raise
        elif metadata_changed:
            self.store.update_metadata(state)
        return {'event': 'applied' if restarted else
                'metadata_updated' if metadata_changed else 'unchanged',
                'blocked_count': len(blocked), 'policy_sha256': chosen.digest,
                'expired': now >= chosen.expires_at, 'rejected_input': rejected}
