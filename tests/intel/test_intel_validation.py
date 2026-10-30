"""Malformed intel is rejected before network I/O or approval; never contact URLs."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'apps/policy-server/src'), str(ROOT / 'apps/dns-agent/src')]
from policy_server import intel as m

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
URL = 'https://malicious-example-domain.online/login'


def collected(count=1):
    urls = [URL] if count == 1 else [f'https://host{i}.example.net/login' for i in range(count)]
    return m.collect_urls(('\n'.join(urls)+'\n').encode(), source='local-openphish', fetched_at=NOW)


def response(url=URL, kinds=None):
    return json.dumps({'threats': [{'url': url, 'threatTypes': kinds or ['SOCIAL_ENGINEERING']}],
                       'cacheDuration': '300s'}).encode()


def verified():
    return m.verify_collected(collected(), 'fake-key', checked_at=NOW,
                              fetch=Mock(return_value=response()))


def reviews(v):
    value = m.review_template(v)
    value['reviews'][0].update(approved=True, acknowledge_subtree=True,
                               reviewer='Reviewer', reason='Verified dedicated phishing host and descendants')
    return value


class IntelValidationTests(unittest.TestCase):
    def test_non_object_artifacts_rejected_without_network(self):
        for value in (None, [], 1, 'bad'):
            fetch = Mock(side_effect=AssertionError('network must not run'))
            with self.subTest(value=value), self.assertRaises(m.IntelError):
                m.verify_collected(value, 'fake-key', fetch=fetch, checked_at=NOW)
            fetch.assert_not_called()

    def test_boolean_and_non_integer_item_limits_rejected(self):
        for limit in (True, 1.5, '10', None, 0, m.MAX_URLS+1):
            with self.subTest(limit=limit), self.assertRaises(m.IntelError):
                m.collect_urls((URL+'\n').encode(), source='local-openphish', limit=limit)

    def test_non_bytes_feed_rejected(self):
        for value in (None, [], 'https://example.net/'):
            with self.subTest(value=value), self.assertRaises(m.IntelError):
                m.collect_urls(value, source='local-openphish')

    def test_candidate_identity_fields_validated_before_hashing(self):
        for field in ('url', 'domain', 'url_sha256', 'source'):
            artifact = collected()
            artifact['entries'][0][field] = []
            fetch = Mock(side_effect=AssertionError('network must not run'))
            with self.subTest(field=field), self.assertRaises(m.IntelError):
                m.verify_collected(artifact, 'fake-key', fetch=fetch, checked_at=NOW)
            fetch.assert_not_called()

    def test_entire_dataset_validated_before_first_batch_request(self):
        artifact = collected(16)
        artifact['entries'][-1]['url_sha256'] = '0'*64
        fetch = Mock(return_value=b'{"threats": [], "cacheDuration": "300s"}')
        with self.assertRaises(m.IntelError):
            m.verify_collected(artifact, 'fake-key', fetch=fetch, checked_at=NOW)
        fetch.assert_not_called()

    def test_untrusted_provenance_not_passed_through(self):
        artifact = collected()
        artifact['entries'][0]['source'] = 'administrator-approved'
        fetch = Mock(return_value=response())
        with self.assertRaises(m.IntelError):
            m.verify_collected(artifact, 'fake-key', fetch=fetch, checked_at=NOW)
        fetch.assert_not_called()

    def test_default_transport_is_resolved_at_call_time(self):
        # No real connection even when this regression runs against old code.
        with patch.object(m, 'get_https', return_value=response()) as remote, patch(
                'urllib.request.OpenerDirector.open', side_effect=AssertionError('real network forbidden')):
            result = m.verify_collected(collected(), 'fake-key', checked_at=NOW)
        remote.assert_called_once()
        self.assertEqual(result['entries'][0]['status'], 'MATCH')

    def test_invalid_api_key_rejected_before_transport(self):
        for key in ('x'*1025, 'unicode-열쇠', 'x\x7f', [], None):
            fetch = Mock(return_value=response())
            with self.subTest(key_type=type(key).__name__), self.assertRaises(m.IntelError):
                m.verify_collected(collected(), key, fetch=fetch, checked_at=NOW)
            fetch.assert_not_called()

    def test_unknown_verification_status_is_not_reviewed(self):
        value = verified()
        value['entries'][0]['status'] = 'APPROVED'
        with self.assertRaises(m.IntelError):
            m.review_template(value)

    def test_unwanted_software_does_not_generate_unbuildable_dns_review(self):
        value = m.verify_collected(collected(), 'fake-key', checked_at=NOW,
                                  fetch=Mock(return_value=response(kinds=['UNWANTED_SOFTWARE'])))
        self.assertEqual(m.review_template(value)['reviews'], [])

    def test_malformed_verification_fields_rejected_before_review(self):
        for field in ('checked_at', 'threat_types', 'valid_until', 'source'):
            value = verified()
            value['entries'][0][field] = {}
            with self.subTest(field=field), self.assertRaises(m.IntelError):
                m.review_template(value)

    def test_duplicate_reviews_cannot_conflict_or_self_overwrite(self):
        value = verified()
        approved = reviews(value)
        duplicate = deepcopy(approved['reviews'][0])
        duplicate['approved'] = False
        approved['reviews'].append(duplicate)
        with self.assertRaises(m.IntelError):
            m.build_policy(value, approved, at=NOW,
                           acknowledge_replacement=True, acknowledge_notice=True)

    def test_unhashable_review_identity_is_a_handled_input_error(self):
        value = verified()
        approved = reviews(value)
        approved['reviews'][0]['domain'] = []
        with self.assertRaises(m.IntelError):
            m.build_policy(value, approved, at=NOW,
                           acknowledge_replacement=True, acknowledge_notice=True)

    def test_numeric_final_label_uses_dns_contract(self):
        with self.assertRaises(m.IntelError):
            m.safe_url('https://host.123/login')

    def test_source_artifacts_remain_private_after_module_move(self):
        with self.assertRaisesRegex(m.IntelError, 'outside the repository'):
            m.write_json(ROOT/'private-intel-must-not-leak.json', {'no': 'leak'})
        self.assertFalse((ROOT/'private-intel-must-not-leak.json').exists())


if __name__ == '__main__':
    unittest.main()
