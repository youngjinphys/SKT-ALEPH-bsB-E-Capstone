"""Opt-in real PostgreSQL concurrency tests. DISPOSABLE LOCAL DATABASE ONLY.

PIN_TEST_DATABASE_URL must target localhost; requires psycopg installed separately.
"""
import concurrent.futures
import hashlib
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse

URL=os.getenv('PIN_TEST_DATABASE_URL','')

@unittest.skipUnless(URL, 'Set PIN_TEST_DATABASE_URL to a disposable local PostgreSQL database')
class PostgresPin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if urlparse(URL).hostname not in ('localhost','127.0.0.1','::1'):
            raise ValueError('Refusing non-local integration database')
        import psycopg
        cls.pg=psycopg
        cls.cap='synthetic-integration-test-capability-not-for-production-12345678'
        with cls.pg.connect(URL,autocommit=True) as conn:
            conn.execute("do $$ begin if not exists(select from pg_roles where rolname='anon') then create role anon; end if; if not exists(select from pg_roles where rolname='authenticated') then create role authenticated; end if; end $$")
            root=Path(__file__).resolve().parents[2]
            for name in ['001_ops_state.sql','002_test_pin_auth.sql']:
                matches=list((root/'cloud/migrations').glob(name if name.startswith('002') else '001*.sql'))
                conn.execute(matches[0].read_text())
            conn.execute('insert into aleph_ops_private.settings values(true,%s) on conflict(id) do update set capability_sha256=excluded.capability_sha256',(hashlib.sha256(cls.cap.encode()).hexdigest(),))

    def sql(self,sql,args=()):
        with self.pg.connect(URL,autocommit=True) as conn:
            return conn.execute(sql,args).fetchone()[0]

    def test_atomic_attempts_across_connections(self):
        self.sql("update aleph_ops_private.test_auth_attempts set attempted_at='{}' returning id")
        def attempt(_): return self.sql('select public.aleph_test_auth_attempt(%s)',(self.cap,))
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            self.assertEqual(sum(pool.map(attempt,range(40))),5)
        self.sql("update aleph_ops_private.test_auth_attempts set attempted_at=array_fill(clock_timestamp()-interval '2 minutes',array[30]) returning id")
        self.assertFalse(attempt(0))
        self.sql("update aleph_ops_private.test_auth_attempts set attempted_at=array_fill(clock_timestamp()-interval '2 hours',array[30]) returning id")
        self.assertTrue(attempt(0))

    def test_session_create_check_rotate_delete_and_capability(self):
        token='a'*64; version='b'*64
        def session(op,v=version,ttl=900):
            return self.sql('select public.aleph_test_auth_session(%s,%s,%s,%s,%s)',(self.cap,op,token,v,ttl))
        session('delete')
        self.assertFalse(session('create',ttl=901))
        self.assertTrue(session('create'))
        self.assertTrue(session('check'))
        self.assertFalse(session('check','c'*64))
        self.assertTrue(session('delete'))
        self.assertFalse(session('check'))
        with self.assertRaises(self.pg.errors.InsufficientPrivilege):
            self.sql('select public.aleph_test_auth_attempt(%s)',('incorrect',))

if __name__=='__main__': unittest.main()
