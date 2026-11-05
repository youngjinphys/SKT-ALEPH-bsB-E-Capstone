"""Read-only, target-specific preparation for independent policy signing."""
from datetime import datetime, timezone
import os
import re
import hashlib
from urllib.parse import urlsplit

from dns_agent.policy import parse_policy
from aleph_policy_sync.snapshot import device_id, trust_key, verify_envelope
from policy_server.console import ConsoleConflict
from .state import StorageUnavailable

DEFAULT_ORIGIN = 'https://skt-aleph-capstone.vercel.app'
MIN_RECOMMENDED_SECONDS = 300
MAX_BROWSER_SEQUENCE = (1 << 53) - 1


def site_origin():
    origin = os.environ.get('ALEPH_POLICY_FEED_ORIGIN', os.environ.get('CAPSTONE_SITE_ORIGIN', DEFAULT_ORIGIN))
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname
        port = parsed.port
        if (parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)
                or '..' in host or (port is not None and not 1 <= port <= 65535)
                or parsed.netloc != host + (':' + str(port) if port is not None else '')):
            raise ValueError('Invalid origin')
    except (ValueError, TypeError):
        raise StorageUnavailable('Invalid configured public site origin') from None
    return origin


def make_handoff(work, name, device, *, now=None):
    instant = now or datetime.now(timezone.utc)
    device = device_id(device)
    if '..' in device:
        raise ValueError('Invalid device ID')
    origin = site_origin()
    downloaded = work.service.download(name)
    policy = parse_policy(downloaded, now=instant)
    baseline = work.service.deployment(device=device, now=instant)
    state = baseline['state']
    if state == 'NO_PUBLISHED_FILE':
        previous = 0
        prior_issued = None
    elif state in ('SIGNED_FILE_VERIFIED', 'PUBLICATION_EXPIRED'):
        previous = baseline['sequence']
        raw = (work.root/'feed'/device/'current.json').read_bytes()
        _, prior = verify_envelope(raw, expected_device=device,
                                   trust_dir=work.root/'policy-trust', now=instant,
                                   allow_expired=True)
        prior_issued = prior.issued_at
    else:
        raise ConsoleConflict('Current publication cannot be verified; do not choose a sequence')
    if previous >= MAX_BROWSER_SEQUENCE:
        raise ConsoleConflict('Next sequence exceeds the dashboard safe integer range')
    next_sequence = previous + 1
    try:
        key_ids = []
        for path in sorted((work.root/'policy-trust').glob('*.pem')):
            trust_key(work.root/'policy-trust', path.stem)
            key_ids.append(path.stem)
    except (ValueError, OSError):
        raise StorageUnavailable('Policy signer trust cannot be verified') from None
    nodes = work.service.node_states()
    selected = next((node for node in nodes if node['device_id'] == device), None)
    node_sequence = selected.get('policy_sequence') if selected else None
    # A signed report is evidence of the node watermark, including when the
    # report has since gone stale; never jump the publication sequence to fit it.
    watermark_warning = type(node_sequence) is int and node_sequence > previous
    remaining = (policy.expires_at - instant).total_seconds()
    if watermark_warning:
        reason = 'NODE_SEQUENCE_AHEAD'
    elif remaining <= 0:
        reason = 'EXPIRED'
    elif remaining < MIN_RECOMMENDED_SECONDS:
        reason = 'SHORT_LIFETIME'
    elif prior_issued is not None and policy.issued_at <= prior_issued:
        reason = 'NOT_NEWER_THAN_PUBLICATION'
    else:
        reason = None
    sign_argv = ['python3', '-m', 'aleph_policy_sync', 'sign',
                 '--policy', '<downloaded-draft.json>', '--private-key', '<offline-private-key.pem>',
                 '--device-id', device, '--sequence', str(next_sequence),
                 '--output', '<new-signed-envelope.json>', '--confirm-replacement']
    if not policy.rules:
        sign_argv.append('--confirm-empty')
    feed = origin + '/v1/policies/' + device + '/current.json'
    install_argv = ['bash', 'scripts/deploy/install-dns-server.sh',
                    '--listen-ip', '<dns-listen-ip>', '--interface', '<interface>',
                    '--client-cidr', '<approved-client-cidr>', '--upstream', '<upstream-ip>',
                    '--bootstrap-policy', '<approved-bootstrap-policy.json>',
                    '--public-key', '<trusted-policy-public-key.pem>', '--device-id', device,
                    '--policy-url', feed]
    return {
        'draft': {'name': name, 'policy_sha256': policy.digest, 'rules': len(policy.rules),
                  'download_sha256': hashlib.sha256(downloaded).hexdigest(),
                  'issued_at': policy.issued_at.isoformat(), 'expires_at': policy.expires_at.isoformat(),
                  'remaining_seconds': max(0, int(remaining)), 'expired': remaining <= 0},
        'target': {'device_id': device, 'registered': selected is not None,
                   'node_state': selected, 'publication_state': state,
                   'current_sequence': previous, 'next_sequence': next_sequence,
                   'node_sequence': str(node_sequence) if node_sequence is not None else None,
                   'watermark_warning': watermark_warning},
        'signing': {'key_ids': key_ids, 'can_sign': reason is None, 'reason': reason,
                    'minimum_recommended_seconds': MIN_RECOMMENDED_SECONDS,
                    'minimum_is_advisory': True, 'argv_template': sign_argv,
                    'pythonpath_components': ['apps/policy-sync/src', 'apps/dns-agent/src'],
                    'requires_empty_confirmation': not bool(policy.rules),
                    'envelope_sha256': None},
        'feed': {'url': feed},
        'node_install': {'argv_template': install_argv, 'requires_local_configuration': True,
                         'preview_only': True},
    }
