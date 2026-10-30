"""Non-commercial threat URL review pipeline; never modifies DNS or fetches suspect sites.

Only two fixed official remote endpoints are contacted, with no redirects:
OpenPhish's public community feed and Google's v5 urls.search endpoint.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

from dns_agent.policy import PolicyError, domain_name, timestamp

OPENPHISH = 'https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt'
GOOGLE = 'https://safebrowsing.googleapis.com/v5/urls:search'
MAX_URLS = 150
MAX_URL_BYTES = 2048
MAX_FEED_BYTES = 2_000_000
MAX_ARTIFACT_BYTES = 900_000
MAX_GOOGLE_BYTES = 1_000_000
MAX_LOOKUP_URL = 7600
VALID_TYPES = {'SOCIAL_ENGINEERING', 'MALWARE', 'UNWANTED_SOFTWARE'}
BLOCK_TYPES = {'SOCIAL_ENGINEERING', 'MALWARE'}
SOURCES = {'openphish', 'local-openphish', 'local-urlhaus'}
IDENTITY_KEYS = {'url', 'domain', 'source', 'url_sha256'}
VERIFIED_KEYS = IDENTITY_KEYS | {'status', 'threat_types', 'checked_at', 'valid_until'}
ROOT = Path(__file__).resolve().parents[4]
DURATION = re.compile(r'(?:0|[1-9]\d*)(?:\.\d{1,9})?s\Z')
# Shared and highly sensitive hosting boundaries that must never be silently
# converted from a specific URL into a SUBTREE-wide DNS block.
PROTECTED_SUFFIXES = (
    'google.com', 'github.com', 'github.io', 'pages.dev', 'workers.dev',
    'vercel.app', 'netlify.app', 'blogspot.com', 'weebly.com',
    'godaddysites.com', 'cloudfront.net', 'amazonaws.com',
    'appspot.com', 'microsoft.com', 'azurewebsites.net', 'wordpress.com',
    'firebaseapp.com', 'web.app', 'herokuapp.com', 'replit.app',
)


class IntelError(ValueError):
    """Input or external response is unsafe or does not meet the contract."""


def now_utc():
    return datetime.now(timezone.utc)


def as_utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise IntelError('timezone-aware datetime required')
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise IntelError('datetime outside supported UTC range') from exc


def iso(t):
    return as_utc(t).isoformat()


def parse_time(text):
    try:
        return timestamp(text, 'intel timestamp')
    except PolicyError as exc:
        raise IntelError('invalid timestamp') from exc


def pairs_unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise IntelError('duplicate JSON key')
        out[k] = v
    return out


def reject_number(value):
    raise IntelError('non-finite JSON constant')


def parse_json(blob):
    if not isinstance(blob, bytes) or len(blob) > MAX_ARTIFACT_BYTES:
        raise IntelError('artifact exceeds size limit')
    try:
        return json.loads(blob.decode('utf-8'), object_pairs_hook=pairs_unique,
                          parse_constant=reject_number)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise IntelError('invalid JSON artifact') from exc


def read_file(path, limit=MAX_ARTIFACT_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise IntelError('input is not a regular file')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read(limit+1)
        if len(data) > limit:
            raise IntelError('input exceeds size limit')
        return data
    finally:
        os.close(fd)


def read_json(path):
    return parse_json(read_file(path))


def write_json(path, data):
    path = Path(path)
    if not path.parent.is_dir():
        raise IntelError('output directory does not exist')
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_uid != os.geteuid())):
        raise IntelError('unsafe output target')
    # No raw public-feed URLs in the public GitHub repository. The ignored
    # data/private directory is the only in-repository exception.
    root = ROOT
    try:
        relative = path.resolve(strict=False).relative_to(root)
    except ValueError:
        pass
    else:
        if relative.parts[:2] != ('data', 'private'):
            raise IntelError('private intel artifacts must be outside the repository or in data/private/')
    raw = (json.dumps(data, ensure_ascii=True, indent=2, allow_nan=False) + '\n').encode()
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise IntelError('output artifact exceeds size limit')
    fd, tmp = tempfile.mkstemp(prefix='.aleph-candidate-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def safe_url(raw):
    """Inspect URL structure only. Never open the suspect URL or follow links."""
    if not isinstance(raw, str) or not raw.isascii() or not 1 <= len(raw.encode()) <= MAX_URL_BYTES:
        raise IntelError('URL is not bounded ASCII')
    if any(ord(c) < 33 or ord(c) == 127 for c in raw):
        raise IntelError('URL includes control/whitespace')
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc or parsed.username is not None or parsed.password is not None:
            raise IntelError('only absolute HTTP(S) URLs without credentials allowed')
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise IntelError('invalid URL authority') from exc
    if not host or not host.isascii() or '%' in host or host.endswith('..'):
        raise IntelError('invalid host')
    try:
        host = domain_name(host)
    except PolicyError as exc:
        raise IntelError('invalid public DNS hostname') from exc
    if (host.endswith(('.test', '.invalid', '.localhost', '.local', '.example', '.onion', '.internal'))
            or host.endswith('.home.arpa')):
        raise IntelError('reserved lab name')
    if port not in (None, 80 if parsed.scheme.lower() == 'http' else 443):
        raise IntelError('nonstandard port not supported')
    normal = urlunsplit((parsed.scheme.lower(), host, parsed.path or '/', parsed.query, ''))
    if len(normal.encode()) > MAX_URL_BYTES:
        raise IntelError('normalized URL exceeds limit')
    return normal, host


def is_protected(host):
    return any(host == x or host.endswith('.'+x) for x in PROTECTED_SUFFIXES)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IntelError('remote source redirected; refusing to follow')


def get_https(url, *, headers=None, limit=MAX_FEED_BYTES):
    if url != OPENPHISH and not url.startswith(GOOGLE+'?'):
        raise IntelError('remote endpoint is not allowlisted')
    opener = build_opener(HTTPSHandler(), NoRedirect())
    request = Request(url, headers=headers or {'User-Agent': 'ALEPH-Educational-Intel/1'})
    try:
        with opener.open(request, timeout=12) as stream:
            if stream.status != 200:
                raise IntelError('upstream returned an unsuccessful status')
            data = stream.read(limit+1)
    except (IntelError, OSError) as exc:
        raise IntelError('trusted source request failed; no partial policy generated') from None
    if len(data) > limit:
        raise IntelError('remote response exceeds limit')
    return data


def validate_limit(limit):
    if type(limit) is not int or not 1 <= limit <= MAX_URLS:
        raise IntelError('item limit must be an integer between 1 and 150')


def _object(value, keys, label):
    if type(value) is not dict or set(value) != keys:
        raise IntelError('invalid ' + label + ' fields')


def _identity(item):
    if any(not isinstance(item.get(key), str) for key in IDENTITY_KEYS):
        raise IntelError('invalid candidate identity fields')
    normal, host = safe_url(item['url'])
    if (normal != item['url'] or host != item['domain'] or item['source'] not in SOURCES
            or hashlib.sha256(normal.encode()).hexdigest() != item['url_sha256']):
        raise IntelError('candidate integrity or source mismatch')


def _verification_entries(value):
    _object(value, {'kind', 'checked_at', 'unassigned_expressions', 'entries'}, 'verification')
    if value['kind'] != 'aleph-verified-urls':
        raise IntelError('requires verification artifact')
    checked = parse_time(value['checked_at'])
    if type(value['unassigned_expressions']) is not int or value['unassigned_expressions'] < 0:
        raise IntelError('invalid expression count')
    entries = value['entries']
    if not isinstance(entries, list) or len(entries) > MAX_URLS:
        raise IntelError('invalid verification entries')
    seen = set()
    for item in entries:
        _object(item, VERIFIED_KEYS, 'verification entry')
        _identity(item)
        kinds = item['threat_types']
        status = item['status']
        if (not isinstance(kinds, list) or len(kinds) > len(VALID_TYPES)
                or any(not isinstance(k, str) or k not in VALID_TYPES for k in kinds)
                or len(set(kinds)) != len(kinds)
                or not isinstance(status, str) or status not in {'MATCH', 'NO_MATCH', 'UNRESOLVED'}
                or (status == 'MATCH') != bool(kinds)):
            raise IntelError('invalid verified threat status')
        observed, expires = parse_time(item['checked_at']), parse_time(item['valid_until'])
        if observed != checked or not timedelta(0) < expires - observed <= timedelta(minutes=30):
            raise IntelError('invalid verification validity interval')
        if item['url'] in seen:
            raise IntelError('duplicate verified URL')
        seen.add(item['url'])
    return entries


def collect_urls(data, *, source, fetched_at=None, limit=MAX_URLS):
    if not isinstance(source, str) or source not in SOURCES:
        raise IntelError('unsupported feed source')
    validate_limit(limit)
    if not isinstance(data, bytes) or len(data) > MAX_FEED_BYTES:
        raise IntelError('feed or item limit exceeded')
    try:
        lines = data.decode('utf-8').splitlines()
    except UnicodeError as exc:
        raise IntelError('feed must be UTF-8') from exc
    entries, seen = [], set()
    rejected = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        # URLhaus exports can include CSV metadata. For this first integration,
        # only a local plain-text URL list is accepted, not arbitrary CSV columns.
        try:
            url, host = safe_url(stripped)
        except IntelError:
            rejected += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        entries.append({'url': url, 'domain': host, 'source': source,
                        'url_sha256': hashlib.sha256(url.encode()).hexdigest()})
        if len(entries) >= limit:
            break
    if not entries:
        raise IntelError('feed has no eligible URLs')
    return {'kind': 'aleph-collected-urls', 'collected_at': iso(fetched_at or now_utc()),
            'source': source, 'rejected_count': rejected, 'entries': entries}


def batches(entries, maximum=15):
    pending, total = [], len(GOOGLE) + 1
    for item in entries:
        encoded = urlencode({'urls': item['url']})
        if len(encoded) + len(GOOGLE) + 1 > MAX_LOOKUP_URL:
            raise IntelError('URL too large for safe API request')
        if pending and (len(pending) >= maximum or total + len(encoded) + 1 > MAX_LOOKUP_URL):
            yield pending
            pending, total = [], len(GOOGLE) + 1
        pending.append(item)
        total += len(encoded) + 1
    if pending:
        yield pending


def parse_google_response(raw, queried, checked_at):
    data = parse_json(raw)
    if not isinstance(data, dict) or set(data) - {'threats','cacheDuration'}:
        raise IntelError('unexpected Google response')
    threats = data.get('threats', [])
    if not isinstance(threats, list) or len(threats) > 300:
        raise IntelError('invalid threat response')
    duration = data.get('cacheDuration')
    if not isinstance(duration, str) or not DURATION.fullmatch(duration):
        raise IntelError('invalid cacheDuration')
    seconds = float(duration[:-1])
    if not 0 < seconds <= 86400 * 7:
        raise IntelError('unexpected cacheDuration')
    # Enforce Google's own cacheDuration and its stricter 30-minute ToS.
    expires_at = checked_at + timedelta(seconds=min(seconds, 1800))
    matches = {x['url']: set() for x in queried}
    unknown = set()
    unassigned = 0
    for entry in threats:
        if not isinstance(entry, dict) or set(entry) != {'url','threatTypes'}:
            raise IntelError('invalid threat entry')
        url = entry['url']
        kinds = entry['threatTypes']
        if not isinstance(url, str) or not isinstance(kinds, list) or any(not isinstance(k, str) for k in kinds):
            raise IntelError('invalid threat fields')
        if url not in matches:
            # Google can return host/path expressions not equal to a query URL.
            # Do not falsely attribute these to specific URLs or DNS hosts.
            unassigned += 1
            continue
        matches[url].update(k for k in kinds if k in VALID_TYPES)
        if any(k not in VALID_TYPES for k in kinds):
            unknown.add(url)
    return matches, expires_at, unassigned, unknown


def verify_collected(data, key, *, fetch=None, checked_at=None):
    _object(data, {'kind', 'collected_at', 'source', 'rejected_count', 'entries'}, 'collection')
    if (data['kind'] != 'aleph-collected-urls' or not isinstance(data['source'], str)
            or data['source'] not in SOURCES or type(data['rejected_count']) is not int
            or data['rejected_count'] < 0):
        raise IntelError('invalid collection metadata')
    if (not isinstance(key, str) or not 1 <= len(key) <= 1024 or not key.isascii()
            or any(not 33 <= ord(c) <= 126 for c in key)):
        raise IntelError('API key is missing or malformed')
    checked_at = as_utc(checked_at or now_utc())
    if parse_time(data['collected_at']) - checked_at > timedelta(seconds=60):
        raise IntelError('collection timestamp is in the future')
    items = data['entries']
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_URLS:
        raise IntelError('invalid candidate count')
    # Validate ALL candidates before the first API request, not batch by batch.
    seen = set()
    for item in items:
        _object(item, IDENTITY_KEYS, 'candidate')
        _identity(item)
        if item['source'] != data['source'] or item['url'] in seen:
            raise IntelError('inconsistent source or duplicate candidate')
        seen.add(item['url'])
    fetch = get_https if fetch is None else fetch
    verified, expressions = [], 0
    for batch in batches(items):
        url_set = [item['url'] for item in batch]
        qs = urlencode([('urls', u) for u in url_set])
        response = fetch(GOOGLE+'?'+qs,
                         headers={'x-goog-api-key': key, 'Accept':'application/json',
                                  'User-Agent':'ALEPH-Educational-Intel/1'},
                         limit=MAX_GOOGLE_BYTES)
        matches, expires, unmatched, unknown = parse_google_response(response, batch, checked_at)
        expressions += unmatched
        for item in batch:
            kinds = sorted(matches[item['url']])
            status = ('MATCH' if kinds else 'UNRESOLVED' if (unmatched or item['url'] in unknown)
                      else 'NO_MATCH')
            verified.append({**item, 'status':status, 'threat_types': kinds,
                             'checked_at':iso(checked_at), 'valid_until':iso(expires)})
    return {'kind':'aleph-verified-urls','checked_at':iso(checked_at),
            'unassigned_expressions':expressions,'entries':verified}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()


def verification_fingerprint(verified):
    """Bind the full observed evidence, not just URL identity; not source authentication.

    The verified dataset and the independently reviewed approval file must both
    remain in trusted storage. An attacker who can rewrite both can recompute an
    unkeyed hash; the separate policy signer remains the authorization boundary.
    """
    entries = _verification_entries(verified)
    normalized = {**verified, 'entries': sorted(
        ({**entry, 'threat_types': sorted(entry['threat_types'])} for entry in entries),
        key=lambda entry: entry['url'])}
    return _digest({'format': 2, 'scope': 'SUBTREE', 'verification': normalized})


def review_template(verified):
    entries = _verification_entries(verified)
    proposals = []
    for item in entries:
        if item['status'] != 'MATCH' or not set(item['threat_types']) & BLOCK_TYPES:
            continue
        proposals.append({'domain': item['domain'], 'url_sha256': item['url_sha256'],
                          'checked_at': item['checked_at'], 'reviewer': '',
                          'reason': '', 'approved': False,
                          'acknowledge_subtree': False})
    return {'kind': 'aleph-manual-domain-reviews', 'format': 2, 'scope': 'SUBTREE',
            'verification_sha256': verification_fingerprint(verified), 'reviews': proposals}


def build_policy(verified, reviews, *, at=None,
                 acknowledge_replacement=False, acknowledge_notice=False):
    if acknowledge_replacement is not True or acknowledge_notice is not True:
        raise IntelError('explicit --confirm-replacement and --acknowledge-user-notice required')
    entries = _verification_entries(verified)
    _object(reviews, {'kind', 'format', 'scope', 'verification_sha256', 'reviews'},
            'reviews (regenerate and re-review legacy unbound templates)')
    fingerprint = verification_fingerprint(verified)
    if (reviews['kind'] != 'aleph-manual-domain-reviews'
            or type(reviews['format']) is not int or reviews['format'] != 2
            or reviews['scope'] != 'SUBTREE'
            or reviews['verification_sha256'] != fingerprint):
        raise IntelError('review evidence or scope changed; regenerate and re-review')
    approvals = reviews['reviews']
    if not isinstance(approvals, list) or len(approvals) > MAX_URLS:
        raise IntelError('invalid review lists')
    at = as_utc(at or now_utc())
    by_ref = {(x['domain'], x['url_sha256'], x['checked_at']): x for x in entries}
    seen_reviews = set()
    selected = {}
    host_reviews = {}
    for review in approvals:
        if not isinstance(review, dict) or set(review) != {'domain','url_sha256','checked_at','reviewer','reason','approved','acknowledge_subtree'}:
            raise IntelError('unexpected review fields')
        if any(not isinstance(review[field], str) for field in
               ('domain', 'url_sha256', 'checked_at', 'reviewer', 'reason')):
            raise IntelError('invalid review identity or text')
        reference = (review['domain'], review['url_sha256'], review['checked_at'])
        if reference in seen_reviews or reference not in by_ref:
            raise IntelError('duplicate review or approval not bound to this verification')
        seen_reviews.add(reference)
        if type(review['approved']) is not bool or type(review['acknowledge_subtree']) is not bool:
            raise IntelError('review booleans required')
        if not review['approved']:
            continue
        if review['acknowledge_subtree'] is not True:
            raise IntelError('review must acknowledge whole-domain SUBTREE consequences')
        if (not isinstance(review['reason'], str) or not 15 <= len(review['reason']) <= 400
                or not isinstance(review['reviewer'], str) or not 2 <= len(review['reviewer']) <= 80
                or any(text != text.strip() or any(ord(c) < 32 or ord(c) == 127 for c in text)
                       for text in (review['reason'], review['reviewer']))):
            raise IntelError('approved domain requires reviewer identity and detailed rationale')
        item = by_ref.get((review['domain'],review['url_sha256'],review['checked_at']))
        if item is None:
            raise IntelError('approval not bound to this verification')
        host = item['domain']
        if is_protected(host):
            raise IntelError('shared-platform or high-impact host cannot be SUBTREE-blocked by this tool')
        if item['status'] != 'MATCH' or not (set(item['threat_types']) & BLOCK_TYPES):
            raise IntelError('not a confirmed relevant Google threat')
        observed = parse_time(item['checked_at'])
        expires = parse_time(item['valid_until'])
        if observed - at > timedelta(seconds=60) or at >= expires or at - observed >= timedelta(minutes=30):
            raise IntelError('Google evidence stale; verify again before generating a block')
        until = min(expires, observed + timedelta(minutes=30), at + timedelta(minutes=15))
        if until <= at:
            raise IntelError('no useful freshness window remains')
        host_reviews.setdefault(host, []).append(review)
        if host in selected:
            # Multiple approved URLs on the same host cannot increase the TTL.
            selected[host]['expires_at'] = iso(min(parse_time(selected[host]['expires_at']), until))
        else:
            selected[host] = {'domain':host,'decision':'BLOCK','scope':'SUBTREE',
                              'approved':True,'expires_at':iso(until),'evidence':''}
    if not selected:
        raise IntelError('no approved, current, verified domains; no policy generated')
    for host, rule in selected.items():
        # Retain an audit reference to EVERY approved URL and to who approved it.
        rule['evidence'] = 'intel-review-v2:sha256:' + _digest({
            'format': 2, 'scope': 'SUBTREE', 'verification_sha256': fingerprint,
            'reviews': sorted(host_reviews[host], key=lambda review: review['url_sha256'])})
    rules = sorted(selected.values(),key=lambda x:x['domain'])
    return {'issued_at':iso(at), 'expires_at':max(x['expires_at'] for x in rules),
            'rules':rules}


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='command',required=True)
    c = sub.add_parser('collect',help='collect URL candidates; no DNS change')
    c.add_argument('--source',choices=['openphish','local-openphish','local-urlhaus'],required=True)
    c.add_argument('--feed-file',type=Path)
    c.add_argument('--accept-openphish-terms',action='store_true')
    c.add_argument('--limit',type=int,default=100)
    c.add_argument('--output',type=Path,required=True)
    v = sub.add_parser('verify',help='send public-feed URLs to Google Safe Browsing v5')
    v.add_argument('--input',type=Path,required=True)
    v.add_argument('--output',type=Path,required=True)
    v.add_argument('--ack-url-disclosure',action='store_true')
    v.add_argument('--ack-noncommercial-use',action='store_true')
    v.add_argument('--api-key-env',default='SAFE_BROWSING_API_KEY')
    r = sub.add_parser('review-template',help='create unapproved review template')
    r.add_argument('--input',type=Path,required=True)
    r.add_argument('--output',type=Path,required=True)
    opts = cli.parse_args(argv)
    try:
        if opts.command == 'collect':
            validate_limit(opts.limit)
            if opts.source == 'openphish':
                if opts.feed_file is not None or not opts.accept_openphish_terms:
                    raise IntelError('OpenPhish remote feed requires explicit --accept-openphish-terms and no --feed-file')
                blob = get_https(OPENPHISH)
            else:
                if opts.feed_file is None:
                    raise IntelError('local feed source requires --feed-file')
                blob = read_file(opts.feed_file,limit=MAX_FEED_BYTES)
            write_json(opts.output,collect_urls(blob,source=opts.source,limit=opts.limit))
        elif opts.command == 'verify':
            if not (opts.ack_url_disclosure and opts.ack_noncommercial_use):
                raise IntelError('acknowledge URL disclosure and noncommercial terms explicitly')
            key = os.getenv(opts.api_key_env)
            if not key:
                raise IntelError('Google API key environment variable not set')
            write_json(opts.output,verify_collected(read_json(opts.input),key))
        else:
            write_json(opts.output,review_template(read_json(opts.input)))
        print('Created local private artifact. No DNS service or policy was published.',file=sys.stderr)
        return 0
    except (IntelError, OSError, ValueError) as exc:
        # Never print raw feed URLs or provider request URLs (may contain tokens).
        print('ERROR: '+str(exc),file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
