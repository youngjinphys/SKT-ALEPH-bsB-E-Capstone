"""Synthetic credentials only; no production configuration is read."""
import hashlib
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cloud import pin_auth as pin
from cloud.app import app


def encoded(value):
    salt = b'unit-test-salt!!'
    digest = hashlib.scrypt(value.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f'scrypt${salt.hex()}${digest.hex()}'


class PinAuth(unittest.TestCase):
    def setUp(self):
        self.now = int(time.time())
        self.env = {'CAPSTONE_SITE_ORIGIN': 'https://testserver', 'CAPSTONE_TEST_PIN_ENABLED': 'true', 'CAPSTONE_TEST_PIN_HASH': encoded('94271538'),
                    'CAPSTONE_TEST_PIN_STARTS_AT': str(self.now-1),
                    'CAPSTONE_TEST_PIN_EXPIRES_AT': str(self.now+3600), 'CAPSTONE_TEST_ACCESS_CODE_HASH': ''}
        self.env_patch = patch.dict(os.environ, self.env)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_shipped_bundle_includes_pin_before_connect(self):
        from cloud.assets import assets
        html, _, script = assets()
        self.assertIn('id="cloud-pin-form"', html)
        self.assertLess(script.index('let cloudPinLoginPending=null'),script.index('async function cloudConnect('))

    def test_disabled_invalid_and_future_config_fail_closed(self):
        for key, value in [('CAPSTONE_TEST_PIN_ENABLED','false'), ('CAPSTONE_TEST_PIN_HASH','1234'),
                           ('CAPSTONE_TEST_PIN_STARTS_AT',str(self.now+1)),
                           ('CAPSTONE_TEST_PIN_STARTS_AT',str(self.now-15*86400)),
                           ('CAPSTONE_TEST_PIN_EXPIRES_AT',str(self.now-1))]:
            with self.subTest(key=key), patch.dict(os.environ, {key:value}):
                self.assertIsNone(pin.config())

    def test_attempt_reserved_before_verification_and_failure(self):
        with patch.object(pin,'rpc',return_value=False), patch.object(pin,'matches') as matches:
            with self.assertRaises(HTTPException) as error: pin.login({'pin':'94271538'})
            self.assertEqual(error.exception.status_code,429)
            matches.assert_not_called()
        with patch.object(pin,'rpc',return_value=True) as rpc:
            with self.assertRaises(HTTPException) as error: pin.login({'pin':'00000000'})
            self.assertEqual(error.exception.status_code,401)
            self.assertEqual(rpc.call_count,1)

    def test_session_is_opaque_hashed_bounded_and_revocable(self):
        with patch.object(pin,'rpc',return_value=True) as rpc:
            token, seconds = pin.login({'pin':'94271538'})
            self.assertEqual(len(token),43)
            self.assertEqual(seconds,900)
            body=rpc.call_args.args[1]
            self.assertEqual(body['token_hash'],pin.fingerprint(token))
            self.assertNotIn(token,str(body))
            request=SimpleNamespace(cookies={pin.COOKIE:token})
            self.assertEqual(pin.identity(request),'test-pin-operator')
            pin.logout(request)
            self.assertEqual(rpc.call_args.args[1]['operation'],'delete')

    def test_optional_code_required_only_when_configured(self):
        with patch.dict(os.environ,{'CAPSTONE_TEST_ACCESS_CODE_HASH':encoded('synthetic-extra-code')}), patch.object(pin,'rpc',return_value=True):
            with self.assertRaises(HTTPException): pin.login({'pin':'94271538'})
            self.assertEqual(pin.login({'pin':'94271538','access_code':'synthetic-extra-code'})[1],900)

    def test_rotation_changes_session_version(self):
        old=pin.config().version
        with patch.dict(os.environ,{'CAPSTONE_TEST_PIN_HASH':encoded('82519374')}):
            self.assertNotEqual(pin.config().version,old)

    def test_post_origin_cookie_flags_and_logout_failure(self):
        client=TestClient(app,base_url='https://testserver')
        self.assertEqual(client.post('/api/ops/test-auth',json={'action':'login','pin':'94271538'},headers={'Origin':'https://evil.invalid'}).status_code,403)
        with patch.object(pin,'rpc',return_value=True):
            response=client.post('/api/ops/test-auth',json={'action':'login','pin':'94271538'},headers={'Origin':'https://testserver'})
            self.assertEqual(response.status_code,200,response.text)
            for flag in ['HttpOnly','Secure','SameSite=strict','Path=/','Max-Age=900']:
                self.assertIn(flag,response.headers['set-cookie'])
            self.assertNotIn('94271538',response.text)
        with patch.object(pin,'rpc',side_effect=HTTPException(503,'unavailable')):
            response=client.post('/api/ops/test-auth',json={'action':'logout'},headers={'Origin':'https://testserver'})
            self.assertEqual(response.status_code,503)
            self.assertNotIn('set-cookie',response.headers)

if __name__=='__main__': unittest.main()
