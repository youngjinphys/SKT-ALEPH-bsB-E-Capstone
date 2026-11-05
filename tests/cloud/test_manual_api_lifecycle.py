"""Exercise the cloud HTTP adapter through a complete manual policy draft flow."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from cloud.app import app
from cloud.state import MemoryStore


class ManualPolicyApiLifecycleTests(unittest.TestCase):
    def test_manual_preview_save_build_download_and_stale_revisions(self):
        store = MemoryStore()
        origin = 'https://skt-aleph-capstone.vercel.app'
        with patch('cloud.app.require_operator', return_value='test-operator@example.org'), \
             patch('cloud.app.get_store', return_value=store), \
             patch.dict('os.environ', {'CAPSTONE_SITE_ORIGIN': origin}), \
             TestClient(app) as client:
            headers = {'Origin': origin}

            def get(path):
                response = client.get('/api/ops/' + path)
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()

            manual = get('manual')
            reviews = get('reviews')
            self.assertEqual(manual['entries'], [])
            self.assertTrue(reviews['missing'])
            candidate = {
                'domain': 'incident-sample.example.net',
                'reviewer': 'Test operator',
                'reason': 'Reviewed synthetic domain and its subtree impact',
                'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                'acknowledge_subtree': True,
                'expected_revision': manual['revision'],
            }
            preview = client.post('/api/ops/manual/preview', json=candidate, headers=headers)
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()['domain'], candidate['domain'])
            self.assertFalse(preview.json()['enforcing'])
            self.assertEqual(store.load()['revision'], 0, 'preview must not write state')

            save = client.post('/api/ops/manual/save',
                               json={**candidate, 'confirm': 'UPSERT_MANUAL_SUBTREE'}, headers=headers)
            self.assertEqual(save.status_code, 200, save.text)
            self.assertEqual(store.load()['revision'], 1)
            stale_save = client.post('/api/ops/manual/save',
                                     json={**candidate, 'confirm': 'UPSERT_MANUAL_SUBTREE'}, headers=headers)
            self.assertEqual(stale_save.status_code, 409, stale_save.text)
            self.assertEqual(store.load()['revision'], 1)

            build = {
                'fingerprint': reviews['fingerprint'],
                'review_set_revision': reviews['review_set_revision'] or 'NOT_PRESENT',
                'manual_revision': manual['revision'],
                'confirm_replacement': True,
                'acknowledge_user_notice': True,
                'excluded_expired_review_ids': [],
                'confirm_empty_replacement': False,
            }
            stale_build = client.post('/api/ops/build', json=build, headers=headers)
            self.assertEqual(stale_build.status_code, 409, stale_build.text)
            self.assertEqual(store.load()['revision'], 1)
            manual = get('manual')
            self.assertEqual([x['domain'] for x in manual['entries']], [candidate['domain']])
            build['manual_revision'] = manual['revision']
            result = client.post('/api/ops/build', json=build, headers=headers)
            self.assertEqual(result.status_code, 200, result.text)
            draft = result.json()
            self.assertEqual(draft['rules'], 1)
            self.assertFalse(draft['signed'])
            self.assertFalse(draft['published'])
            self.assertEqual(store.load()['revision'], 2)

            drafts = get('drafts')
            self.assertEqual([x['name'] for x in drafts], [draft['draft']])
            self.assertFalse(drafts[0]['signed'])
            self.assertFalse(drafts[0]['published'])
            download = client.get('/api/ops/drafts/' + draft['draft'] + '/download')
            self.assertEqual(download.status_code, 200, download.text)
            rules = download.json()['rules']
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0]['domain'], candidate['domain'])
            self.assertEqual(rules[0]['decision'], 'BLOCK')
            self.assertEqual(rules[0]['scope'], 'SUBTREE')
            self.assertTrue(rules[0]['evidence'].startswith('manual-review-v1:sha256:'))
            self.assertEqual(store.load()['revision'], 2, 'reads must not write state')


if __name__ == '__main__':
    unittest.main()
