#!/usr/bin/env python3
"""실습용 캠페인 카탈로그를 로컬 DNS 정책 JSON으로 컴파일한다.

읽기/검사 후 stdout 출력만 한다. DNS, 방화벽, 사용자 브라우저는 수정하지 않는다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / 'packages/policy-contract/campaigns/catalog.json'
ID = re.compile(r'[a-z][a-z0-9-]{1,47}\Z')
CASE = re.compile(r'LAB-[A-Z0-9-]{4,48}\Z')
LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')


class CatalogError(ValueError):
    pass


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def unexpected_constant(value):
    raise CatalogError(f'non-finite value: {value}')


def require_keys(obj, keys, where):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise CatalogError(f'{where}: unexpected or missing fields')


def load_catalog(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(256 * 1024 + 1)
    except OSError as exc:
        raise CatalogError(f'cannot read catalog: {exc}') from exc
    if len(raw) > 256 * 1024:
        raise CatalogError('catalog exceeds 256 KiB')
    try:
        catalog = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_pairs,
                             parse_constant=unexpected_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CatalogError(f'invalid catalog JSON: {exc}') from exc
    require_keys(catalog, ('synthetic', 'campaigns'), 'catalog')
    if catalog['synthetic'] is not True:
        raise CatalogError('only synthetic laboratory campaign catalogs are supported')
    campaigns = catalog['campaigns']
    if not isinstance(campaigns, list) or not 1 <= len(campaigns) <= 100:
        raise CatalogError('campaigns: expected 1..100 records')
    identifiers = set()
    names = set()
    case_ids = set()
    reviewed = []
    for group in campaigns:
        require_keys(group, ('id', 'title', 'scenario', 'rules'), 'campaign')
        ident = group['id']
        if not isinstance(ident, str) or not ID.fullmatch(ident) or ident in identifiers:
            raise CatalogError('invalid or duplicate campaign id')
        identifiers.add(ident)
        for attr, limit in (('title', 90), ('scenario', 350)):
            value = group[attr]
            if (not isinstance(value, str) or not 1 <= len(value) <= limit
                    or any(ord(char) < 32 for char in value)):
                raise CatalogError(f'{ident}: invalid {attr}')
        entries = group['rules']
        if not isinstance(entries, list) or not 1 <= len(entries) <= 200:
            raise CatalogError(f'{ident}: rules must be 1..200 items')
        for item in entries:
            require_keys(item, ('domain', 'decision', 'approved', 'ttl_minutes', 'case_id'),
                         f'{ident}.rule')
            name = item['domain']
            if not isinstance(name, str) or name != name.lower() or not name.isascii():
                raise CatalogError(f'{ident}: ASCII lowercase domain required')
            labels = name.split('.')
            if (len(name) > 253 or len(labels) < 2 or labels[-1] != 'test'
                    or any(not LABEL.fullmatch(part) for part in labels)
                    or name == 'capstone.test' or name.endswith('.capstone.test')):
                raise CatalogError(f'{ident}: invalid or non-test domain: {name!r}')
            if name in names:
                raise CatalogError(f'duplicate domain across campaigns: {name}')
            names.add(name)
            if item['decision'] not in ('BLOCK', 'WARN', 'ALLOW'):
                raise CatalogError(f'{ident}: unsupported decision')
            if type(item['approved']) is not bool:
                raise CatalogError(f'{ident}: approved must be boolean')
            if type(item['ttl_minutes']) is not int or not 1 <= item['ttl_minutes'] <= 1440:
                raise CatalogError(f'{ident}: ttl_minutes must be integer 1..1440')
            case = item['case_id']
            if not isinstance(case, str) or not CASE.fullmatch(case) or case in case_ids:
                raise CatalogError(f'{ident}: invalid or duplicate case_id')
            case_ids.add(case)
        reviewed.append(group)
    # Detect exact-subtree contradictions before emission; never change intended scope.
    records = [(item['domain'], item['decision'], item['approved'])
               for group in reviewed for item in group['rules']]
    for name, decision, approved in records:
        if not approved:
            continue
        for other, other_decision, other_approved in records:
            if other_approved and name != other and name.endswith('.' + other):
                if decision != other_decision:
                    raise CatalogError('overlapping approved subtree rules with conflicting decisions')
    return reviewed


def parse_issued_at(value):
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str) or not value.endswith('Z'):
        raise CatalogError('--issued-at must be a timezone-aware UTC timestamp ending in Z')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise CatalogError('--issued-at is invalid') from exc
    if parsed.tzinfo is None:
        raise CatalogError('--issued-at timezone required')
    return parsed.astimezone(timezone.utc)


def create_policy(groups, issued_at, selected=()):
    selected = tuple(selected)
    available = {g['id'] for g in groups}
    if len(selected) != len(set(selected)) or set(selected) - available:
        raise CatalogError('unknown or duplicate --campaign selection')
    filtered = [g for g in groups if not selected or g['id'] in selected]
    rules = []
    for group in sorted(filtered, key=lambda entry: entry['id']):
        for item in sorted(group['rules'], key=lambda entry: entry['domain']):
            rules.append({
                'domain': item['domain'],
                'decision': item['decision'],
                'scope': 'SUBTREE',
                'approved': item['approved'],
                'expires_at': (issued_at + timedelta(minutes=item['ttl_minutes'])).isoformat(),
                'evidence': f"synthetic-campaign:{group['id']}:{item['case_id']}",
            })
    if not rules:
        raise CatalogError('empty campaign policy is not allowed')
    if len(rules) > 10000:
        raise CatalogError('more than 10000 rules cannot be applied by the DNS agent')
    expires = max(datetime.fromisoformat(rule['expires_at']) for rule in rules)
    return {'issued_at': issued_at.isoformat(), 'expires_at': expires.isoformat(), 'rules': rules}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=DEFAULT_CATALOG)
    parser.add_argument('--campaign', action='append', default=[], metavar='ID',
                        help='select a campaign; repeat to combine (default: all)')
    parser.add_argument('--issued-at', help='deterministic UTC timestamp for tests (ending in Z)')
    parser.add_argument('--list', action='store_true', help='show available campaign IDs only')
    args = parser.parse_args(argv)
    try:
        groups = load_catalog(args.catalog)
        if args.list:
            if args.campaign or args.issued_at:
                raise CatalogError('--list cannot be combined with --campaign or --issued-at')
            for group in groups:
                print(f"{group['id']}\t{group['title']}")
            return 0
        policy = create_policy(groups, parse_issued_at(args.issued_at), args.campaign)
        output = json.dumps(policy, ensure_ascii=False, indent=2) + '\n'
        if len(output.encode('utf-8')) > 1024 * 1024:
            raise CatalogError('output policy exceeds 1 MiB')
    except (CatalogError, OverflowError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
