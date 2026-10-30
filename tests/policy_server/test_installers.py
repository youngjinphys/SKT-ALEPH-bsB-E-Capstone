"""Offline smoke tests for installer dry-runs and trust-anchor preflights."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
REMOTE = ROOT / "scripts/deploy/install-policy-server.sh"
DNS = ROOT / "scripts/deploy/install-dns-server.sh"


class InstallerPreviewTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.folder = Path(t.name)
        key = Ed25519PrivateKey.generate()
        self.pub = self.folder / "trusted.pem"
        self.pub.write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ))
        self.api = self.folder / "api.key"
        self.api.write_text("test-only-not-real\n")
        self.api.chmod(0o600)
        now = datetime.now(timezone.utc)
        import json
        self.policy = self.folder / "bootstrap.json"
        self.policy.write_text(json.dumps({"issued_at":(now - timedelta(minutes=1)).isoformat(),
            "expires_at":(now + timedelta(minutes=5)).isoformat(), "rules":[]}), encoding="utf-8")

    def execute(self, path, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(["bash",str(path),*args],cwd=ROOT,env=env,
                              capture_output=True,text=True,timeout=20)

    def remote_args(self):
        return ["--server-name","policy.example.org","--device-id","edge-69",
                "--api-key-file",str(self.api),"--public-key",str(self.pub),
                "--accept-openphish-terms","--ack-url-disclosure","--ack-noncommercial-use"]

    def dns_args(self, device="edge-69"):
        return ["--listen-ip","192.168.7.69","--interface","eth0",
                "--client-cidr","192.168.7.0/24","--upstream","9.9.9.9",
                "--bootstrap-policy",str(self.policy),"--public-key",str(self.pub),
                "--device-id",device,
                "--policy-url","https://policy.example.org/v1/policies/edge-69/current.json"]

    def test_help_is_successful_and_non_mutating(self):
        for script in (REMOTE,DNS):
            with self.subTest(script=script.name):
                r=self.execute(script,"--help")
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn("--apply",r.stderr)

    def test_preview_succeeds_without_system_mutation(self):
        for script,args in ((REMOTE,self.remote_args()),(DNS,self.dns_args())):
            with self.subTest(script=script.name):
                r=self.execute(script,*args)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn("Preview only",r.stdout)

    def test_mismatched_device_url_is_rejected(self):
        r=self.execute(DNS,*self.dns_args(device="other-device"))
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn("Preview only",r.stdout)

    def test_invalid_public_key_fails_before_setup(self):
        bad=self.folder / "not-ed25519.pem"
        bad.write_text("this is not a public key")
        args=self.remote_args()
        args[args.index("--public-key")+1]=str(bad)
        r=self.execute(REMOTE,*args)
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn("Preview only",r.stdout)


if __name__=="__main__":
    unittest.main()
