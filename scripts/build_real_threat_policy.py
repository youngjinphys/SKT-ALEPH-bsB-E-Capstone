#!/usr/bin/env python3
"""Non-commercial threat URL review pipeline; never modifies DNS or fetches suspect sites.

Only two fixed official remote endpoints are contacted, with no redirects:
OpenPhish's public community feed and Google's v5 urls.search endpoint.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

OPENPHISH = 'https://raw.githubusercontent.com/openphish/public_feed/refs/heads/main/feed.txt'
GOOGLE = 'https://safebrowsing.googleapis.com/v5/urls:search'
MAX_URLS = 150
MAX_URL_BYTES = 2048
MAX_FEED_BYTES = 2_000_000
MAX_ARTIFACT_BYTES = 900_000
MAX_GOOGLE_BYTES = 1_000_000
MAX_LOOKUP_URL = 7600
VALID_TYPES = {'SOCIAL_ENGINEERING', 'MALWARE', 'UNWANTED_SOFTWARE'}
LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
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


def iso(t):
    return t.astimezone(timezone.utc).isoformat()


def parse_time(text):
    if not isinstance(text, str) or len(text) > 40:
        raise IntelError('invalid timestamp')
    try:
        t = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if t.tzinfo is None:
            raise ValueError('no timezone')
        return t.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
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
    if len(blob) > MAX_ARTIFACT_BYTES:
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
    root = Path(__file__).resolve().parents[1]
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
    host = host.lower().removesuffix('.')
    labs = host.split('.')
    if len(host) > 253 or len(labs) < 2 or any(not LABEL.fullmatch(x) for x in labs):
        raise IntelError('invalid DNS hostname')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise IntelError('literal IP is not a public domain candidate')
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


def collect_urls(data, *, source, fetched_at=None, limit=MAX_URLS):
    if source not in ('openphish', 'local-openphish', 'local-urlhaus'):
        raise IntelError('unsupported feed source')
    if len(data) > MAX_FEED_BYTES or not 1 <= limit <= MAX_URLS:
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


def verify_collected(data, key, *, fetch=get_https, checked_at=None):
    if data.get('kind') != 'aleph-collected-urls' or not isinstance(data.get('entries'), list):
        raise IntelError('not a collected URL artifact')
    if not isinstance(key, str) or not key or any(ord(c) < 33 for c in key):
        raise IntelError('API key is missing or malformed')
    checked_at = checked_at or now_utc()
    items = data['entries']
    if not items or len(items) > MAX_URLS:
        raise IntelError('invalid candidate count')
    if len(set(x.get('url') for x in items if isinstance(x,dict))) != len(items):
        raise IntelError('duplicate candidates')
    verified, expressions = [], 0
    for batch in batches(items):
        url_set = []
        for item in batch:
            if not isinstance(item, dict) or set(item) != {'url','domain','source','url_sha256'}:
                raise IntelError('invalid candidate entry')
            normalized, host = safe_url(item['url'])
            if (normalized != item['url'] or host != item['domain']
                    or hashlib.sha256(normalized.encode()).hexdigest() != item['url_sha256']):
                raise IntelError('candidate integrity mismatch')
            url_set.append(item['url'])
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


def review_template(verified):
    if verified.get('kind') != 'aleph-verified-urls':
        raise IntelError('requires verification artifact')
    proposals = []
    for item in verified.get('entries', []):
        if item['status'] != 'MATCH' or not item['threat_types']:
            continue
        proposals.append({'domain': item['domain'], 'url_sha256': item['url_sha256'],
                          'checked_at': item['checked_at'], 'reviewer': '',
                          'reason': '', 'approved': False,
                          'acknowledge_subtree': False})
    return {'kind':'aleph-manual-domain-reviews','reviews':proposals}


def build_policy(verified, reviews, *, at=None,
                 acknowledge_replacement=False, acknowledge_notice=False):
    if not (acknowledge_replacement and acknowledge_notice):
        raise IntelError('explicit --confirm-replacement and --acknowledge-user-notice required')
    if verified.get('kind') != 'aleph-verified-urls' or reviews.get('kind') != 'aleph-manual-domain-reviews':
        raise IntelError('artifact kind mismatch')
    entries = verified.get('entries')
    approvals = reviews.get('reviews')
    if not isinstance(entries, list) or not isinstance(approvals, list) or len(entries) > MAX_URLS:
        raise IntelError('invalid review lists')
    at = at or now_utc()
    by_ref = {}
    for item in entries:
        if not isinstance(item, dict) or not {'url','domain','url_sha256','source','status','threat_types','checked_at','valid_until'} <= set(item):
            raise IntelError('invalid verification entry')
        normal, host = safe_url(item['url'])
        if host != item['domain'] or normal != item['url'] or hashlib.sha256(normal.encode()).hexdigest() != item['url_sha256']:
            raise IntelError('tampered verification identity')
        ref = (host, item['url_sha256'], item['checked_at'])
        if ref in by_ref:
            raise IntelError('duplicate verified URL')
        by_ref[ref] = item
    selected = {}
    for review in approvals:
        if not isinstance(review, dict) or set(review) != {'domain','url_sha256','checked_at','reviewer','reason','approved','acknowledge_subtree'}:
            raise IntelError('unexpected review fields')
        if type(review['approved']) is not bool or type(review['acknowledge_subtree']) is not bool:
            raise IntelError('review booleans required')
        if not review['approved']:
            continue
        if review['acknowledge_subtree'] is not True:
            raise IntelError('review must acknowledge whole-domain SUBTREE consequences')
        if (not isinstance(review['reason'], str) or not 15 <= len(review['reason']) <= 400
                or not isinstance(review['reviewer'], str) or not 2 <= len(review['reviewer']) <= 80):
            raise IntelError('approved domain requires reviewer identity and detailed rationale')
        item = by_ref.get((review['domain'],review['url_sha256'],review['checked_at']))
        if item is None:
            raise IntelError('approval not bound to this verification')
        host = item['domain']
        if is_protected(host):
            raise IntelError('shared-platform or high-impact host cannot be SUBTREE-blocked by this tool')
        if item['status'] != 'MATCH' or not (set(item['threat_types']) & {'SOCIAL_ENGINEERING','MALWARE'}):
            raise IntelError('not a confirmed relevant Google threat')
        observed = parse_time(item['checked_at'])
        expires = parse_time(item['valid_until'])
        if observed > at + timedelta(seconds=60) or at >= expires or at - observed >= timedelta(minutes=30):
            raise IntelError('Google evidence stale; verify again before generating a block')
        until = min(expires, observed + timedelta(minutes=30), at + timedelta(minutes=15))
        if until <= at:
            raise IntelError('no useful freshness window remains')
        evidence = item['source']+':gsb:'+item['url_sha256'][:24]
        if host in selected:
            # Multiple approved URLs on the same host cannot increase the TTL.
            selected[host]['expires_at'] = iso(min(parse_time(selected[host]['expires_at']), until))
        else:
            selected[host] = {'domain':host,'decision':'BLOCK','scope':'SUBTREE',
                              'approved':True,'expires_at':iso(until),'evidence':evidence}
    if not selected:
        raise IntelError('no approved, current, verified domains; no policy generated')
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
    b = sub.add_parser('build',help='generate bounded approved BLOCK policy; does not publish')
    b.add_argument('--input',type=Path,required=True)
    b.add_argument('--reviews',type=Path,required=True)
    b.add_argument('--output',type=Path,required=True)
    b.add_argument('--confirm-replacement',action='store_true')
    b.add_argument('--acknowledge-user-notice',action='store_true')
    opts = cli.parse_args(argv)
    try:
        if opts.command == 'collect':
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
        elif opts.command == 'review-template':
            write_json(opts.output,review_template(read_json(opts.input)))
        else:
            policy = build_policy(read_json(opts.input),read_json(opts.reviews),

                                  acknowledge_replacement=opts.confirm_replacement,
                                  acknowledge_notice=opts.acknowledge_user_notice)
            # Use the same producer validation contract as the DNS agent before output.
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps/dns-agent/src'))
            from dns_agent.policy import parse_policy
            parse_policy(json.dumps(policy).encode())
            write_json(opts.output,policy)
        print('Created local private artifact. No DNS service or policy was published.',file=sys.stderr)
        return 0
    except (IntelError, OSError, ValueError) as exc:
        # Never print raw feed URLs or provider request URLs (may contain tokens).
        print('ERROR: '+str(exc),file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
