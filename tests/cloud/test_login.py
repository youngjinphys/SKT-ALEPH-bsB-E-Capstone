"""Authentication must not depend on policy state availability."""
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from cloud.app import app


class OperatorLogin(unittest.TestCase):
    def test_missing_cookie_is_denied_before_storage(self):
        with patch('cloud.app.get_store') as storage:
            result = TestClient(app).get('/api/ops/session')
            self.assertEqual(result.status_code, 401)
            storage.assert_not_called()

    def test_authorized_identity_does_not_read_or_write_policy_state(self):
        with patch('cloud.app.require_operator', return_value='owner@example.org'), patch('cloud.app.get_store') as storage:
            result = TestClient(app).get('/api/ops/session')
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json(), {'authorized': True, 'email': 'owner@example.org'})
            self.assertIn('no-store', result.headers['cache-control'])
            storage.assert_not_called()

    def test_general_confirmed_login_is_not_operator_authorization(self):
        env = {'SUPABASE_URL': 'https://test.supabase.co', 'SUPABASE_PUBLISHABLE_KEY': 'test-public',
               'CAPSTONE_OPS_ALLOWED_EMAILS': 'owner@example.org'}
        for email, confirmed, status in [('other@example.org', True, 403),
                                        ('owner@example.org', False, 403),
                                        ('OWNER@example.org', True, 200)]:
            with self.subTest(email=email, confirmed=confirmed), patch.dict(os.environ, env), patch(
                    'cloud.security.remote_json', return_value={
                        'id': 'test-user', 'email': email,
                        'email_confirmed_at': '2026-01-01T00:00:00Z' if confirmed else None}), patch('cloud.app.get_store') as storage:
                result = TestClient(app).get('/api/ops/session', headers={'Cookie': '__Host-capstone_at=synthetic-test-session'})
                self.assertEqual(result.status_code, status, result.text)
                storage.assert_not_called()

if __name__ == '__main__':
    unittest.main()
