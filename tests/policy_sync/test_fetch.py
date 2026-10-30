"""TLS loopback-only download tests. Never contacts internet or publishes DNS."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import os
import ssl
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import TestCase, skipIf
from unittest.mock import patch
from urllib.error import HTTPError

from aleph_policy_sync import sync

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.x509.oid import NameOID

from aleph_policy_sync.snapshot import SnapshotError, canonical, public_key_id, sign_policy
from aleph_policy_sync.sync import SyncError, fetch_once, validate_https_url
from test_snapshot import NOW, policy, trust


class FixtureServer:
    def __init__(self, root: Path):
        tls_key=ec.generate_private_key(ec.SECP256R1())
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
              .public_key(tls_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(datetime.now(timezone.utc)-timedelta(days=1))
              .not_valid_after(datetime.now(timezone.utc)+timedelta(days=2))
              .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
              .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
              .sign(tls_key,hashes.SHA256()))
        self.cert_path=root/'ca.crt';self.key_path=root/'server.pem'
        self.cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        self.key_path.write_bytes(tls_key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        self.key_path.chmod(0o600)
        self.status=200;self.body=b'';self.etag='"v1"';self.calls=[]
        fixture=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                fixture.calls.append((self.path,self.headers.get('If-None-Match'),
                                      self.headers.get('Authorization')))
                if fixture.status==302:
                    self.send_response(302);self.send_header('Location','https://example.com/');self.end_headers();return
                if fixture.status==503:
                    self.send_error(503);return
                if self.headers.get('If-None-Match')==fixture.etag or fixture.status==304:
                    self.send_response(304);self.end_headers();return
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('ETag',fixture.etag)
                self.send_header('Content-Length',str(len(fixture.body)))
                self.end_headers();self.wfile.write(fixture.body)
            def log_message(self,*_):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.cert_path,self.key_path)
        self.server.socket=ctx.wrap_socket(self.server.socket,server_side=True)
        self.port=self.server.server_port
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True)
    def __enter__(self):self.worker.start();return self
    def __exit__(self,*_):self.server.shutdown();self.worker.join(2);self.server.server_close()


@skipIf(os.geteuid()==0,'Download service must run as an unprivileged account')
class FetchTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.trust=self.root/'trust';self.trust.mkdir(mode=0o700)
        self.key=ed25519.Ed25519PrivateKey.generate();trust(self.trust,self.key)
        self.inbox=self.root/'inbox'
        self.inbox.mkdir(mode=0o700)
    def signed(self, sequence=1, at=NOW):
        return canonical(sign_policy(canonical(policy(at)),self.key,target='edge-69',
                                     sequence=sequence,signed_at=at))+b'\n'
    def download(self, server, *, at=NOW):
        return fetch_once(url=f'https://localhost:{server.port}/v1/policies/edge-69/current.json',
                          device='edge-69',trust_dir=self.trust,inbox_dir=self.inbox,
                          ca_file=server.cert_path,now=at)

    def test_tls_verify_download_etag_and_no_rewrites_on_304(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.assertEqual(self.download(server),'downloaded')
            raw=(self.inbox/'current.json').read_bytes()
            self.assertEqual(raw,server.body)
            self.assertEqual((self.inbox/'current.json').stat().st_mode & 0o777,0o600)
            self.assertEqual(self.download(server),'not-modified')
            self.assertEqual((self.inbox/'current.json').read_bytes(),raw)
            self.assertEqual(server.calls[0][1],None)
            self.assertEqual(server.calls[1][1],'"v1"')

    def test_invalid_signature_and_503_preserve_last_good(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server);last=(self.inbox/'current.json').read_bytes()
            server.etag='"bad"';server.body=last.replace(b'"sequence":1',b'"sequence":2')
            with self.assertRaises(SnapshotError):self.download(server)
            self.assertEqual((self.inbox/'current.json').read_bytes(),last)
            server.status=503
            with self.assertRaises(SyncError):self.download(server)
            self.assertEqual((self.inbox/'current.json').read_bytes(),last)

    def test_old_expired_snapshot_does_not_block_new_valid(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            later=NOW+timedelta(minutes=13)
            server.etag='"v2"';server.body=self.signed(2,later)
            self.assertEqual(self.download(server,at=later),'downloaded')
            self.assertEqual((self.inbox/'current.json').read_bytes(),server.body)
            self.assertIsNone(server.calls[-1][1])  # expired ETag ignored

    def test_signed_sequence_rollback_is_rejected_before_staging(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed(3)
            self.download(server)
            original=(self.inbox/'current.json').read_bytes()
            server.etag='"old"';server.body=self.signed(2)
            with self.assertRaisesRegex(SyncError,'rollback'):
                self.download(server)
            self.assertEqual((self.inbox/'current.json').read_bytes(),original)

    def test_redirect_and_wrong_ca_are_rejected(self):
        with FixtureServer(self.root) as server:
            server.status=302
            with self.assertRaises(SyncError):self.download(server)
            server.status=200;server.body=self.signed()
            with self.assertRaises(SyncError):
                fetch_once(url=f'https://localhost:{server.port}/v1/policies/edge-69/current.json',
                           device='edge-69',trust_dir=self.trust,inbox_dir=self.inbox,now=NOW)
            self.assertFalse((self.inbox/'current.json').exists())

    def test_missing_inbox_forces_download_without_old_etag(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            (self.inbox/'current.json').unlink()
            self.assertEqual(self.download(server),'downloaded')
            self.assertIsNone(server.calls[-1][1])

    def test_symlinked_destination_fails_and_preserves_external(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            external=self.root/'external';external.write_text('never change')
            (self.inbox/'current.json').symlink_to(external)
            with self.assertRaises((SyncError,SnapshotError,OSError)):
                self.download(server)
            self.assertEqual(external.read_text(),'never change')

    def test_partial_previous_metadata_write_is_recovered_by_full_download(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            state=self.inbox/'fetch-state.json'
            meta=json.loads(state.read_text())
            meta['envelope_sha256']='f'*64
            state.write_text(json.dumps(meta));state.chmod(0o600)
            self.assertEqual(self.download(server),'downloaded')
            self.assertIsNone(server.calls[-1][1])

    def test_revoked_cached_key_does_not_prevent_trusted_successor(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            retired=public_key_id(self.key.public_key())
            self.key=ed25519.Ed25519PrivateKey.generate()
            trust(self.trust,self.key)
            (self.trust/(retired+'.pem')).unlink()
            later=NOW+timedelta(minutes=1)
            server.etag='"successor"';server.body=self.signed(2,later)
            try:
                result=self.download(server,at=later)
            except OSError as exc:
                self.fail(f'retired cached signer blocked a trusted new download: {exc}')
            self.assertEqual(result,'downloaded')
            self.assertIsNone(server.calls[-1][1])
            self.assertEqual((self.inbox/'current.json').read_bytes(),server.body)

    def test_revoked_cached_key_never_authorizes_an_unknown_successor(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            previous=(self.inbox/'current.json').read_bytes()
            retired=public_key_id(self.key.public_key())
            self.key=ed25519.Ed25519PrivateKey.generate()  # intentionally NOT trusted
            (self.trust/(retired+'.pem')).unlink()
            later=NOW+timedelta(minutes=1)
            server.etag='"unknown"';server.body=self.signed(2,later)
            before=len(server.calls)
            with self.assertRaises((SnapshotError,FileNotFoundError)):
                self.download(server,at=later)
            self.assertEqual(len(server.calls),before+1,
                             'fresh download must be checked independently of the retired cache')
            self.assertIsNone(server.calls[-1][1])
            self.assertEqual((self.inbox/'current.json').read_bytes(),previous)

    def _advance_on_304(self, clock, *, revoke=False):
        # Keep real localhost TLS and Ed25519 checks. Only inject what changes
        # while the request is in flight; no wall-clock sleep is needed.
        make_opener=sync.build_opener
        def factory(*handlers):
            opener=make_opener(*handlers)
            open_request=opener.open
            def intercepted(*args,**kwargs):
                try:
                    return open_request(*args,**kwargs)
                except HTTPError as exc:
                    if exc.code==304:
                        if revoke:
                            kid=public_key_id(self.key.public_key())
                            (self.trust/(kid+'.pem')).unlink()
                        else:
                            clock[0]=NOW+timedelta(minutes=12,seconds=1)
                    raise
            opener.open=intercepted
            return opener
        return factory

    def test_304_cannot_confirm_a_policy_that_expired_in_flight(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            before=(self.inbox/'current.json').read_bytes()
            metadata=(self.inbox/'fetch-state.json').read_bytes()
            clock=[NOW+timedelta(minutes=11)]
            with patch('aleph_policy_sync.snapshot.now_utc',side_effect=lambda:clock[0]), \
                 patch('aleph_policy_sync.sync.now_utc',side_effect=lambda:clock[0]), \
                 patch('aleph_policy_sync.sync.build_opener',side_effect=self._advance_on_304(clock)):
                with self.assertRaises((SyncError,SnapshotError)):
                    self.download(server,at=None)
            self.assertEqual((self.inbox/'current.json').read_bytes(),before)
            self.assertEqual((self.inbox/'fetch-state.json').read_bytes(),metadata)

    def test_304_cannot_confirm_a_signer_revoked_in_flight(self):
        with FixtureServer(self.root) as server:
            server.body=self.signed()
            self.download(server)
            before=(self.inbox/'current.json').read_bytes()
            metadata=(self.inbox/'fetch-state.json').read_bytes()
            clock=[NOW]
            with patch('aleph_policy_sync.snapshot.now_utc',side_effect=lambda:clock[0]), \
                 patch('aleph_policy_sync.sync.now_utc',side_effect=lambda:clock[0]), \
                 patch('aleph_policy_sync.sync.build_opener',side_effect=self._advance_on_304(clock,revoke=True)):
                with self.assertRaises((SyncError,SnapshotError,FileNotFoundError)):
                    self.download(server,at=None)
            self.assertEqual((self.inbox/'current.json').read_bytes(),before)
            self.assertEqual((self.inbox/'fetch-state.json').read_bytes(),metadata)

    def test_never_accept_plaintext_credentials_redirects_or_fragments(self):
        for url in ('http://localhost/policy.json','https://u:p@host/policy',
                    'https://host/policy?key=x','https://host/policy#fragment',
                    'https://host/ab\r\nInjected:x'):
            with self.subTest(url=url),self.assertRaises(SyncError):validate_https_url(url)

if __name__=='__main__':unittest.main()
