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
UPGRADE = ROOT / "scripts/deploy/upgrade-policy-runtime.sh"
INTEL = ROOT / "scripts/deploy/install-intel-refresh-bridge.sh"
OPS = ROOT / "scripts/deploy/install-operations-console.sh"
TELEMETRY = ROOT / "scripts/deploy/install-dns-telemetry.sh"


class InstallerPreviewTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.folder = Path(t.name)
        key = Ed25519PrivateKey.generate()
        self.private = self.folder / "status-private.pem"
        self.private.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        self.private.chmod(0o600)
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
        for script in (REMOTE,DNS,UPGRADE,INTEL):
            with self.subTest(script=script.name):
                r=self.execute(script,"--help")
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn("--apply",r.stderr)

    def test_intel_bridge_never_grants_web_service_collector_credentials(self):
        source=INTEL.read_text(encoding="utf-8")
        self.assertIn("SocketMode=0660",source)
        self.assertIn("SocketGroup=aleph-ops-console",source)
        self.assertIn("SO_PEERCRED", (ROOT/"apps/policy-server/src/policy_server/refresh_bridge.py").read_text())
        self.assertIn("User=aleph-policy-server",source)
        self.assertIn("ALEPH_INTEL_REFRESH_SOCKET=",source)
        self.assertNotIn("chmod 777",source)
        self.assertIn("verify-runtime",source)
        self.assertIn("aleph-intel-refresh.service",UPGRADE.read_text())
        preview=self.execute(INTEL)
        self.assertEqual(preview.returncode,0,preview.stderr)
        self.assertIn("Preview only",preview.stdout)

    def test_existing_runtime_upgrade_is_not_an_initial_installer(self):
        # This operation must never create an installation during a preview.
        result=self.execute(UPGRADE,"--role","invalid")
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn("New runtime active",result.stdout)
        source=UPGRADE.read_text(encoding="utf-8")
        self.assertIn("BACKUP=/opt/.aleph-policy-code.rollback",source)
        self.assertIn("systemctl is-active --quiet",source)
        self.assertIn("mv -T -- \"$TARGET\" \"$BACKUP\"",source)
        self.assertIn("copy-source",source)
        self.assertIn("trap cleanup EXIT",source)

    def test_preview_succeeds_without_system_mutation(self):
        for script,args in ((REMOTE,self.remote_args()),(DNS,self.dns_args())):
            with self.subTest(script=script.name):
                r=self.execute(script,*args)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn("Preview only",r.stdout)

    def test_operator_console_limits_management_source_to_explicit_private_subnet(self):
        base=["--origin","https://ops.example.org","--device-id","edge-69"]
        for cidr in ("127.0.0.1/32","192.168.7.0/24","10.20.1.7/32"):
            with self.subTest(cidr=cidr):
                result=self.execute(OPS,*base,"--admin-cidr",cidr)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn("Preview only",result.stdout)
        for cidr in ("0.0.0.0/0","10.0.0.0/8","8.8.8.0/24",
                     "192.168.0.0/16","127.0.0.0/8","not-a-network"):
            with self.subTest(cidr=cidr):
                result=self.execute(OPS,*base,"--admin-cidr",cidr)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn("Preview only",result.stdout)
        contents=OPS.read_text(encoding="utf-8")
        self.assertIn("allow $ADMIN_CIDR;",contents)
        self.assertNotIn("allow 10.0.0.0/8;",contents)

    def test_dns_telemetry_cannot_probe_its_own_listener_as_upstream(self):
        args=["--device-id","edge-69","--listen-ip","192.168.7.69",
              "--report-url","https://ops.example.org/v1/nodes/report",
              "--private-key",str(self.private),"--public-key",str(self.pub)]
        for reference in ("9.9.9.9","192.168.7.1"):
            with self.subTest(reference=reference):
                run=self.execute(TELEMETRY,*args,"--probe-upstream",reference)
                self.assertEqual(run.returncode,0,run.stderr)
                self.assertIn("positive-reference="+reference,run.stdout)
        for reference in ("192.168.7.69","127.0.0.1","0.0.0.0"):
            with self.subTest(reference=reference):
                run=self.execute(TELEMETRY,*args,"--probe-upstream",reference)
                self.assertNotEqual(run.returncode,0)
                self.assertNotIn("Preview only",run.stdout)

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
