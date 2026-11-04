"""Production control-plane DB must not reuse the OAuth tenant by accident."""
import os
import unittest
from unittest.mock import patch

from cloud.state import SupabaseStore, StorageUnavailable


class StorageRouting(unittest.TestCase):
    def test_naver_database_credentials_are_isolated_from_auth(self):
        env = {
            "VERCEL_ENV": "production",
            "SUPABASE_URL": "https://auth-tenant.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_auth",
            "ALEPH_STATE_CAPABILITY": "A" * 64,
            "ALEPH_STATE_URL": "https://naver-tenant.supabase.co",
            "ALEPH_STATE_PUBLISHABLE_KEY": "sb_publishable_naver",
            "ALEPH_STATE_DB_CAPABILITY": "N" * 64,
        }
        with patch.dict(os.environ, env, clear=True):
            store = SupabaseStore()
            self.assertEqual(store.url, env["ALEPH_STATE_URL"])
            self.assertEqual(store.key, env["ALEPH_STATE_PUBLISHABLE_KEY"])
            self.assertEqual(store.cap, env["ALEPH_STATE_DB_CAPABILITY"])

    def test_production_requires_dedicated_database_configuration(self):
        baseline = {
            "VERCEL_ENV": "production",
            "SUPABASE_URL": "https://auth-tenant.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_auth",
            "ALEPH_STATE_CAPABILITY": "A" * 64,
        }
        with patch.dict(os.environ, baseline, clear=True):
            with self.assertRaises(StorageUnavailable):
                SupabaseStore()
        with patch.dict(os.environ, {**baseline,"ALEPH_STATE_URL":"https://naver-tenant.supabase.co"}, clear=True):
            with self.assertRaises(StorageUnavailable):
                SupabaseStore()

    def test_preview_must_not_connect_to_production_storage(self):
        env={
            "VERCEL_ENV":"preview",
            "ALEPH_STATE_URL":"https://naver-tenant.supabase.co",
            "ALEPH_STATE_PUBLISHABLE_KEY":"sb_publishable_naver",
            "ALEPH_STATE_DB_CAPABILITY":"N" * 64,
        }
        with patch.dict(os.environ,env,clear=True):
            with self.assertRaises(StorageUnavailable):
                SupabaseStore()

    def test_legacy_local_development_remains_explicitly_supported(self):
        env={
            "SUPABASE_URL":"https://auth-tenant.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY":"sb_publishable_legacy",
            "ALEPH_STATE_CAPABILITY":"L" * 64,
        }
        with patch.dict(os.environ,env,clear=True):
            store=SupabaseStore()
            self.assertEqual(store.url, env["SUPABASE_URL"])
