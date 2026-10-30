"""No networking: reject approval reuse when the reviewed evidence changes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'apps/policy-server/src'), str(ROOT / 'apps/dns-agent/src')]
from policy_server import intel

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def verified():
    url = 'https://dedicated-threat.example.net/login'
    return {'kind': 'aleph-verified-urls', 'checked_at': NOW.isoformat(),
            'unassigned_expressions': 0, 'entries': [{
                'url': url, 'domain': 'dedicated-threat.example.net',
                'source': 'openphish', 'url_sha256': hashlib.sha256(url.encode()).hexdigest(),
                'status': 'MATCH', 'threat_types': ['SOCIAL_ENGINEERING'],
                'checked_at': NOW.isoformat(),
                'valid_until': (NOW + timedelta(minutes=5)).isoformat()}]}


def approve(data):
    reviews = intel.review_template(data)
    for entry in reviews['reviews']:
        entry.update(approved=True, acknowledge_subtree=True, reviewer='Test reviewer',
                     reason='Controlled test; the complete dedicated host was reviewed.')
    return reviews


def build(data, reviews):
    return intel.build_policy(data, reviews, at=NOW, acknowledge_replacement=True,
                              acknowledge_notice=True)


class ReviewIntegrityTests(unittest.TestCase):
    def test_mutating_valid_evidence_invalidates_prior_approval(self):
        original = verified()
        reviews = approve(original)
        for field, value in (
            ('valid_until', (NOW + timedelta(minutes=20)).isoformat()),
            ('threat_types', ['MALWARE']),
            ('source', 'local-urlhaus'),
        ):
            changed = deepcopy(original)
            changed['entries'][0][field] = value
            with self.subTest(field=field), self.assertRaises(intel.IntelError):
                build(changed, reviews)

    def test_verification_context_is_bound_even_if_selected_url_is_unchanged(self):
        original = verified()
        reviews = approve(original)
        changed = deepcopy(original)
        changed['unassigned_expressions'] = 1
        with self.assertRaises(intel.IntelError):
            build(changed, reviews)

    def test_legacy_unbound_reviews_require_explicit_re_review(self):
        data = verified()
        old = {'kind': 'aleph-manual-domain-reviews', 'reviews': approve(data)['reviews']}
        with self.assertRaises(intel.IntelError):
            build(data, old)

    def test_whitespace_or_control_only_approval_text_is_rejected(self):
        data = verified()
        for field, value in [('reviewer', '  '), ('reason', ' '*20),
                             ('reason', 'acceptable rationale\nforged log record')]:
            reviews = approve(data)
            reviews['reviews'][0][field] = value
            with self.subTest(field=field), self.assertRaises(intel.IntelError):
                build(data, reviews)

    def test_published_evidence_changes_with_approval_actor_or_rationale(self):
        data = verified()
        original = approve(data)
        different = deepcopy(original)
        different['reviews'][0]['reviewer'] = 'Another reviewer'
        self.assertNotEqual(build(data, original)['rules'][0]['evidence'],
                            build(data, different)['rules'][0]['evidence'])

    def test_bound_scope_cannot_be_changed_to_exact(self):
        data = verified()
        reviews = approve(data)
        self.assertEqual(reviews.get('scope'), 'SUBTREE')
        reviews['scope'] = 'EXACT'
        with self.assertRaises(intel.IntelError):
            build(data, reviews)

    def test_multi_url_evidence_is_complete_and_order_independent(self):
        data = verified()
        other = deepcopy(data['entries'][0])
        other['url'] += '/second'
        other['url_sha256'] = hashlib.sha256(other['url'].encode()).hexdigest()
        data['entries'].append(other)
        reviews = approve(data)
        expected = build(data, reviews)
        data['entries'].reverse()
        reviews['reviews'].reverse()
        self.assertEqual(build(data, reviews), expected)
        one = verified()
        self.assertNotEqual(build(one, approve(one))['rules'][0]['evidence'],
                            expected['rules'][0]['evidence'])
