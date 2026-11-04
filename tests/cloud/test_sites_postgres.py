"""Optional atomic replay integration test on a disposable local PostgreSQL DB."""
import concurrent.futures,hashlib,os,threading,time,unittest
from pathlib import Path
from urllib.parse import urlparse
URL=os.getenv('SITES_TEST_DATABASE_URL','')
@unittest.skipUnless(URL,'Set SITES_TEST_DATABASE_URL to a disposable local PostgreSQL database')
class SitesPostgres(unittest.TestCase):
    def test_atomic_nonce_capability_and_expiry(self):
        if urlparse(URL).hostname not in ('localhost','127.0.0.1','::1'):raise ValueError('Refusing non-local database')
        import psycopg
        cap='synthetic-sites-integration-test-capability-not-production-12345678'
        with psycopg.connect(URL,autocommit=True) as conn:
            conn.execute("do $$ begin if not exists(select from pg_roles where rolname='anon') then create role anon; end if; if not exists(select from pg_roles where rolname='authenticated') then create role authenticated; end if; end $$")
            root=Path(__file__).resolve().parents[2]
            for name in ['001_operations.sql','003_sites_bridge_nonce.sql']:conn.execute((root/'cloud/migrations'/name).read_text())
            conn.execute('insert into aleph_ops_private.settings values(true,%s) on conflict(id) do update set capability_sha256=excluded.capability_sha256',(hashlib.sha256(cap.encode()).hexdigest(),))
        nonce=hashlib.sha256(str(time.time_ns()).encode()).hexdigest();expiry=int(time.time())+30
        barrier=threading.Barrier(40,timeout=15)
        def consume(_,key=cap,expires=expiry,simultaneous=False):
            with psycopg.connect(URL,autocommit=True) as conn:
                conn.execute("set statement_timeout='10s'")
                if simultaneous:barrier.wait()
                return conn.execute('select public.aleph_sites_consume_nonce(%s,%s,%s)',(key,nonce,expires)).fetchone()[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=40) as pool:
            results=list(pool.map(lambda i:consume(i,simultaneous=True),range(40)))
        self.assertEqual(results.count(True),1)
        self.assertEqual(results.count(False),39)
        self.assertFalse(consume(0,expires=int(time.time())-1))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):consume(0,key='incorrect')
        self.assertFalse(consume(0,expires=int(time.time())+120))
        # Test low-privilege roles themselves, not only superuser ACL metadata.
        for role in ('anon','authenticated'):
            with self.subTest(role=role),psycopg.connect(URL,autocommit=True) as conn:
                conn.execute(psycopg.sql.SQL('set role {}').format(psycopg.sql.Identifier(role)))
                for statement in (
                    'select * from aleph_ops_private.sites_bridge_nonces',
                    "insert into aleph_ops_private.sites_bridge_nonces values(repeat('a',64),now())",
                    'update aleph_ops_private.sites_bridge_nonces set expires_at=now()',
                    'delete from aleph_ops_private.sites_bridge_nonces',
                    'truncate aleph_ops_private.sites_bridge_nonces',
                ):
                    with self.subTest(statement=statement),self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        conn.execute(statement)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    conn.execute('select public.aleph_sites_consume_nonce(%s,%s,%s)',('incorrect',nonce,int(time.time())+30))
                role_nonce=hashlib.sha256((nonce+role).encode()).hexdigest()
                args=(cap,role_nonce,int(time.time())+30)
                self.assertTrue(conn.execute('select public.aleph_sites_consume_nonce(%s,%s,%s)',args).fetchone()[0])
                self.assertFalse(conn.execute('select public.aleph_sites_consume_nonce(%s,%s,%s)',args).fetchone()[0])
