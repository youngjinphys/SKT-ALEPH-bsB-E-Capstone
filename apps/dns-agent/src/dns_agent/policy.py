"""Bounded, explicit policy contract; no shell, network, or filesystem mutation."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import re

MAX_BYTES = 1024 * 1024
MAX_RULES = 10000
MAX_LIFETIME = timedelta(days=7)
LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
HEALTH_ZONE = 'capstone.test'

class PolicyError(ValueError):
    """Untrusted input cannot be safely interpreted."""

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f'duplicate JSON key: {key}')
        result[key] = value
    return result

def _constant(value):
    raise PolicyError(f'non-finite JSON constant: {value}')

def strict_json(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise PolicyError('policy exceeds 1 MiB')
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PolicyError(f'invalid JSON: {exc}') from exc

def _keys(obj, expected, where):
    if not isinstance(obj, dict) or set(obj) != set(expected):
        raise PolicyError(f'{where}: require exactly {", ".join(expected)}')

def timestamp(value, field) -> datetime:
    if (not isinstance(value, str) or len(value) > 40
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value)
            or value.endswith('-00:00')):
        raise PolicyError(f'{field}: expected timezone-aware ISO timestamp')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise PolicyError(f'{field}: invalid timestamp') from exc
    if stamp.tzinfo is None:
        raise PolicyError(f'{field}: timezone required')
    try:
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise PolicyError(f'{field}: timestamp outside supported UTC range') from exc

def domain_name(value: object, *, allow_public: bool = False) -> str:
    if not isinstance(value, str) or not value.isascii() or value != value.strip():
        raise PolicyError('domain: expected ASCII hostname without whitespace')
    name = value.lower().removesuffix('.')
    labels = name.split('.')
    if len(name) > 253 or len(labels) < 2 or any(not LABEL.fullmatch(x) for x in labels):
        raise PolicyError('domain: invalid labels or length')
    if labels[-1].isdigit():
        raise PolicyError('domain: numeric final label is not a hostname')
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise PolicyError('domain: IP literal is not allowed')
    if name == HEALTH_ZONE or name.endswith('.' + HEALTH_ZONE):
        raise PolicyError('domain overlaps reserved health-check namespace')
    # IDNA conversion belongs to the reviewed producer, not a lossy local repair.
    if not allow_public and labels[-1] != 'test':
        raise PolicyError('lab policy accepts only .test; public names require explicit opt-in')
    return name

@dataclass(frozen=True)
class Rule:
    domain: str
    decision: str
    approved: bool
    expires_at: datetime
    evidence: str

@dataclass(frozen=True)
class Policy:
    issued_at: datetime
    expires_at: datetime
    rules: tuple[Rule, ...]
    raw: bytes
    digest: str

    def blocked(self, now: datetime) -> tuple[str, ...]:
        if now >= self.expires_at:
            return ()
        return tuple(sorted(r.domain for r in self.rules
                            if r.approved and r.decision == 'BLOCK' and now < r.expires_at))

def parse_policy(raw: bytes, *, now: datetime | None = None,
                 allow_public: bool = False) -> Policy:
    now = now or utcnow()
    obj = strict_json(raw)
    _keys(obj, ('issued_at', 'expires_at', 'rules'), 'policy')
    issued = timestamp(obj['issued_at'], 'issued_at')
    expires = timestamp(obj['expires_at'], 'expires_at')
    if issued > now + timedelta(seconds=60) or not issued < expires:
        raise PolicyError('policy: future issuance or invalid validity interval')
    if expires - issued > MAX_LIFETIME:
        raise PolicyError('policy: validity exceeds seven days')
    if not isinstance(obj['rules'], list) or len(obj['rules']) > MAX_RULES:
        raise PolicyError('rules: expected array of at most 10000 items')
    by_name: dict[str, Rule] = {}
    for item in obj['rules']:
        _keys(item, ('domain','decision','scope','approved','expires_at','evidence'), 'rule')
        name = domain_name(item['domain'], allow_public=allow_public)
        if item['scope'] != 'SUBTREE':
            raise PolicyError('dnsmasq backend supports SUBTREE only; EXACT is not silently widened')
        decision = item['decision']
        if not isinstance(decision, str) or decision not in {'BLOCK','WARN','ALLOW'}:
            raise PolicyError('decision: BLOCK, WARN or ALLOW required')
        if type(item['approved']) is not bool:
            raise PolicyError('approved: boolean required, not a score or integer')
        evidence = item['evidence']
        if not isinstance(evidence, str) or not 1 <= len(evidence) <= 256 or any(ord(c) < 32 for c in evidence):
            raise PolicyError('evidence: require nonempty text of at most 256 characters')
        until = timestamp(item['expires_at'], 'rule.expires_at')
        if not issued < until <= expires:
            raise PolicyError('rule validity must fit the policy interval')
        if name in by_name:
            raise PolicyError('duplicate canonical domain')
        by_name[name] = Rule(name, decision, item['approved'], until, evidence)
    # At most 127 label steps per name: avoid O(n^2) pairwise matching.
    for name, rule in by_name.items():
        labels = name.split('.')
        for i in range(1, len(labels) - 1):
            parent = by_name.get('.'.join(labels[i:]))
            if (parent and parent.approved and rule.approved
                    and parent.decision != rule.decision):
                raise PolicyError('conflict: overlapping SUBTREE policies with different decisions')
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()
    if len(canonical) > MAX_BYTES:
        raise PolicyError('canonical policy exceeds 1 MiB after JSON escaping')
    return Policy(issued, expires, tuple(by_name.values()), canonical,
                  hashlib.sha256(canonical).hexdigest())

def render_config(blocked: tuple[str, ...], *, port: int,
                  upstream: str, upstream_port: int,
                  listen_address: str = '127.0.0.1', system_dns: bool = False) -> str:
    """A privileged port is permitted ONLY in explicitly selected system DNS mode."""
    if type(system_dns) is not bool:
        raise PolicyError('system_dns must be a boolean')
    if system_dns:
        if port != 53:
            raise PolicyError('system DNS mode requires port 53')
    elif type(port) is not int or not 1024 <= port <= 65535:
        raise PolicyError('lab listener requires an unprivileged port')
    try:
        listen = ipaddress.IPv4Address(listen_address)
    except (ipaddress.AddressValueError, ValueError) as exc:
        raise PolicyError('listener must be an IPv4 literal') from exc
    private_nets = tuple(ipaddress.ip_network(n) for n in
                         ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    if system_dns:
        if not any(listen in net for net in private_nets):
            raise PolicyError('system listener must be a private RFC1918 IPv4 address')
    elif str(listen) != '127.0.0.1':
        raise PolicyError('lab listener must remain on 127.0.0.1')
    if type(upstream_port) is not int or not 1 <= upstream_port <= 65535:
        raise PolicyError('invalid upstream port')
    if not isinstance(upstream, str) or '%' in upstream or upstream != upstream.strip():
        raise PolicyError('upstream: scoped addresses and whitespace are not supported')
    try:
        address = ipaddress.ip_address(upstream)
    except ValueError as exc:
        raise PolicyError('upstream must be an IP literal, not a URL or config fragment') from exc
    if address.is_unspecified or address.is_multicast:
        raise PolicyError('upstream must be a unicast destination')
    if (address.is_loopback and upstream_port == port and not system_dns
            or str(address) == str(listen) and upstream_port == port):
        raise PolicyError('upstream points back to the listener')
    names = tuple(sorted(domain_name(x, allow_public=True) for x in blocked))
    marker = hashlib.sha256('\n'.join(names).encode()).hexdigest()[:20]
    lines = [f'port={port}', f'listen-address={listen}', 'bind-interfaces',
             'no-resolv', 'no-hosts', 'cache-size=0', 'local-ttl=0',
             'domain-needed', f'server={address}#{upstream_port}',
             f'local=/{HEALTH_ZONE}/',
             f'host-record=health-{marker}.{HEALTH_ZONE},192.0.2.1,2001:db8::1']
    lines.extend(f'address=/{name}/' for name in names)
    return '\n'.join(lines) + '\n'
