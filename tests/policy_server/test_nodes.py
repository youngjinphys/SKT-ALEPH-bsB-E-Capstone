"""Offline DNS telemetry proof, replay and separated-policy/edge identity tests."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/"apps/policy-server/src"),
                str(ROOT/"apps/policy-sync/src"), str(ROOT/"apps/dns-agent/src")]

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from aleph_policy_sync.snapshot import canonical, public_key_id, sign_policy
from aleph_policy_sync.telemetry import (
    TelemetryError, build_local_payload, collect, private_ipv4, signed_report, verify_report)
from policy_server.console import ConsoleService, handler_for
from policy_server.nodes import NodeConflict, NodeError


class NodeTelemetryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.workspace = self.root/"console"
        self.workspace.mkdir(mode=0o700)
        self.token = self.root/"token"
        self.token.write_text("x"*48)
        self.token.chmod(0o600)
        self.device_key = Ed25519PrivateKey.generate()
        self.device_key_id = public_key_id(self.device_key.public_key())
        self.publisher_key = Ed25519PrivateKey.generate()
        self.publisher_key_id = public_key_id(self.publisher_key.public_key())
        self.device_trust = self.root/"device-trust"
        self.device_trust.mkdir()
        self.policy_trust = self.root/"policy-trust"
        self.policy_trust.mkdir()
        for path,key in ((self.device_trust,self.device_key),
                         (self.policy_trust,self.publisher_key)):
            kid=public_key_id(key.public_key())
            (path/(kid+".pem")).write_bytes(key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo))
        self.feed = self.root/"feed"
        (self.feed/"edge-69").mkdir(parents=True)
        self.console = ConsoleService(self.workspace,self.token,feed_root=self.feed,
                                      device="edge-69",trust_dir=self.policy_trust,
                                      node_trust_dir=self.device_trust)
        self.entry={"device_id":"edge-69","label":"Lab node",
                    "dns_address":"192.168.7.69","key_id":self.device_key_id}
        self.console.register_node(self.entry)

    def policy(self):
        now = datetime.now(timezone.utc)
        end = (now+timedelta(minutes=10)).isoformat()
        policy={"issued_at":now.isoformat(),"expires_at":end,
                "rules":[{"domain":"blocked.example.org","decision":"BLOCK","scope":"SUBTREE",
                         "approved":True,"evidence":"offline-test-only","expires_at":end}]}
        env=sign_policy(canonical(policy), self.publisher_key,target="edge-69",sequence=7)
        (self.feed/"edge-69"/"current.json").write_bytes(canonical(env))
        digest=hashlib.sha256(canonical(env["payload"])).hexdigest()
        applied={"sequence":7,"policy_sha256":env["payload"]["policy_sha256"],
                 "payload_sha256":digest, "applied_at":now.isoformat()}
        inbox = self.root/"inbox.json"
        inbox.write_bytes(canonical(env));inbox.chmod(0o600)
        return applied,inbox

    def report(self, sequence=1,*,attestation="ATTESTED",ip=None,now=None):
        at=now or datetime.now(timezone.utc)
        pub=self.console.deployment()
        payload={
            "format":1,"type":"aleph-dns-node-report","device_id":"edge-69",
            "report_sequence":sequence,"reported_at":at.isoformat(),
            "dns_address":ip or "192.168.7.69",
            "policy_sequence":7,"policy_sha256":pub["policy_sha256"],
            "applied_at":(at-timedelta(seconds=1)).isoformat(),
            "attestation":attestation,
            "probe":{"domain":"blocked.example.org","udp":True,"tcp":True}
            if attestation=="ATTESTED" else {"domain":None,"udp":None,"tcp":None}
        }
        return signed_report(payload,self.device_key,now=at)

    def test_verified_receiver_agrees_with_locally_published_policy(self):
        self.policy()
        raw=self.report()
        accepted=self.console.receive_node_report(raw)
        self.assertFalse(accepted["duplicate"])
        self.assertTrue(self.console.receive_node_report(raw)["duplicate"])
        states=self.console.node_states()
        self.assertEqual(len(states),1)
        self.assertEqual(states[0]["state"],"LOCAL_DNS_UNCORROBORATED")
        self.assertEqual(states[0]["policy_sequence"],7)
        self.assertEqual(states[0]["published_sequence"],7)
        self.assertTrue(states[0]["dns_applied"])
        self.assertFalse(states[0]["lan_verified"])
        self.assertTrue(states[0]["probe"]["udp"])
        self.assertTrue(states[0]["probe"]["tcp"])
        aggregate=self.console.overview()["nodes"]
        self.assertEqual(aggregate,{"registered":1,"local_attested":1,
                                    "dns_correlated":0,"needs_verification":1})

    def test_correlated_dns_probe_requires_positive_independent_upstream(self):
        from aleph_policy_sync.telemetry import probe_upstream_ipv4
        applied,inbox=self.policy()
        calls=[]
        def resolver(name, qtype, port, *, tcp, server_ip, timeout, require_answer=False):
            calls.append((qtype,tcp,server_ip,require_answer))
            return 0 if server_ip=="9.9.9.9" and qtype==1 and require_answer else 3
        kwargs=dict(device="edge-69",address="192.168.7.69",applied=applied,
                    inbox=inbox,trust_dir=self.policy_trust,dns_admin=self.root/"admin",
                    attest=lambda *_:True,probe=resolver,upstream="9.9.9.9")
        corroborated=build_local_payload(report_sequence=20,**kwargs)
        self.assertEqual(corroborated["format"],4)
        self.assertEqual(corroborated["probe"]["baseline"],True)
        self.assertTrue(corroborated["probe"]["udp"])
        self.assertTrue(corroborated["probe"]["tcp"])
        self.assertEqual(len(calls),6)  # A+AAAA local, A upstream; UDP and TCP
        self.console.receive_node_report(signed_report(corroborated,self.device_key))
        self.assertEqual(self.console.node_states()[0]["state"],"LOCAL_DNS_VERIFIED")
        self.assertFalse(self.console.node_states()[0]["lan_verified"])
        # If the queried hostname is already NXDOMAIN upstream, both local
        # NXDOMAIN responses are inconclusive, never a verified block.
        unavailable=build_local_payload(report_sequence=21,
                                        **{**kwargs,"probe":lambda *a,**k:3})
        self.assertEqual(unavailable["probe"]["baseline"],False)
        self.console.receive_node_report(signed_report(unavailable,self.device_key))
        self.assertEqual(self.console.node_states()[0]["state"],
                         "LOCAL_DNS_REFERENCE_UNVERIFIED")
        # A format-2 report without the reference cannot claim DNS verification.
        missing=build_local_payload(report_sequence=22,
                                    **{**kwargs,"upstream":None})
        self.assertIsNone(missing["probe"]["baseline"])
        self.console.receive_node_report(signed_report(missing,self.device_key))
        self.assertEqual(self.console.node_states()[0]["state"],
                         "LOCAL_DNS_UNCORROBORATED")
        with self.assertRaises(TelemetryError):
            probe_upstream_ipv4("192.168.7.69","192.168.7.69")
        with self.assertRaises(TelemetryError):
            probe_upstream_ipv4("127.0.0.1","192.168.7.69")

    def test_v2_malformed_probe_is_rejected_and_v1_is_never_correlated(self):
        self.policy()
        first=json.loads(self.report(sequence=2))["payload"]
        first["format"]=2
        with self.assertRaises(TelemetryError):
            signed_report(first,self.device_key)
        first["probe"]["baseline"]="true"
        with self.assertRaises(TelemetryError):
            signed_report(first,self.device_key)
        first["probe"]["baseline"]=True
        signed=signed_report(first,self.device_key)
        self.console.receive_node_report(signed)
        self.assertEqual(self.console.node_states()[0]["state"],"LOCAL_DNS_VERIFIED")
        legacy=self.report(sequence=3)
        self.console.receive_node_report(legacy)
        self.assertEqual(self.console.node_states()[0]["state"],"LOCAL_DNS_UNCORROBORATED")

    def test_newer_report_mismatch_is_detected_and_not_success(self):
        self.policy()
        old=json.loads(self.report())
        old["payload"]["policy_sequence"]=6
        old["payload"]["policy_sha256"]="f"*64
        raw=signed_report(old["payload"],self.device_key)
        self.console.receive_node_report(raw)
        status=self.console.node_states()[0]
        self.assertEqual(status["state"],"POLICY_MISMATCH")
        self.assertFalse(status["dns_applied"])

    def test_signature_replay_collision_and_unregistered_address_fail_closed(self):
        self.policy()
        raw=self.report(sequence=4)
        self.console.receive_node_report(raw)
        with self.assertRaises(NodeConflict):
            self.console.receive_node_report(self.report(sequence=3))
        collision=json.loads(raw)
        collision["payload"]["probe"]["udp"]=False
        with self.assertRaises(NodeError):
            self.console.receive_node_report(canonical(collision)) # altered signature
        with self.assertRaises(NodeConflict):
            self.console.receive_node_report(signed_report(collision["payload"],self.device_key))
        with self.assertRaises(NodeError):
            self.console.receive_node_report(self.report(sequence=5,ip="192.168.1.9"))
        with self.assertRaises(NodeError):
            self.console.receive_node_report(self.report(sequence=5).replace(b"edge-69",b"edge-70"))
        self.assertEqual(self.console.node_states()[0]["report_sequence"],4)

    def test_disabled_status_without_any_applied_policy(self):
        plain={"format":1,"type":"aleph-dns-node-report","device_id":"edge-69",
               "report_sequence":1,"reported_at":datetime.now(timezone.utc).isoformat(),
               "dns_address":"192.168.7.69","policy_sequence":None,"policy_sha256":None,
               "applied_at":None,"attestation":"NO_POLICY",
               "probe":{"domain":None,"udp":None,"tcp":None}}
        self.console.receive_node_report(signed_report(plain,self.device_key))
        self.assertEqual(self.console.node_states()[0]["state"],"NO_POLICY")
        self.assertIsNone(self.console.node_states()[0]["dns_applied"])

    def test_future_dated_receipt_does_not_claim_healthy_node(self):
        self.policy()
        future=datetime.now(timezone.utc)+timedelta(minutes=5)
        envelope=self.report(sequence=100, now=future)
        self.console.nodes.receive(envelope, now=future)
        status=self.console.node_states()[0]
        self.assertEqual(status["state"],"CLOCK_SKEW")
        self.assertIsNone(status["dns_applied"])

    def test_expired_reports_are_not_current_evidence(self):
        self.policy()
        prior=datetime.now(timezone.utc)-timedelta(minutes=5)
        raw=self.report(now=prior)
        self.console.nodes.receive(raw,now=prior)
        self.assertEqual(self.console.node_states()[0]["state"],"STALE")
        with self.assertRaises((NodeError,TelemetryError,ValueError)):
            self.console.receive_node_report(raw)

    def test_node_enrollment_requires_public_key_and_valid_private_lan_address(self):
        with self.assertRaises((ValueError,NodeError)):
            self.console.register_node({**self.entry,"device_id":"edge-70","key_id":"f"*64})
        for invalid in ("8.8.8.8","127.0.0.1","169.254.0.1","::1","192.0.2.5"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                private_ipv4(invalid)
        other = self.console.node_states()[0]
        self.assertEqual(other["state"],"NO_REPORT")
        self.console.unregister_node({"device_id":"edge-69","confirm":"UNREGISTER_NODE",
                                      "expected_key_id":self.device_key_id})
        self.assertEqual(self.console.node_states(),[])

    def test_node_removal_requires_the_identity_shown_at_confirmation(self):
        old_key = self.device_key_id
        with self.assertRaises(NodeError):
            self.console.unregister_node({"device_id":"edge-69", "confirm":"UNREGISTER_NODE"})
        self.console.unregister_node({"device_id":"edge-69", "confirm":"UNREGISTER_NODE",
                                      "expected_key_id":old_key})
        replacement = Ed25519PrivateKey.generate()
        new_key = public_key_id(replacement.public_key())
        (self.device_trust/(new_key+".pem")).write_bytes(replacement.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.console.register_node({**self.entry, "key_id":new_key})
        before = (self.workspace/"nodes.json").read_bytes()
        with self.assertRaises(NodeConflict):
            self.console.unregister_node({"device_id":"edge-69", "confirm":"UNREGISTER_NODE",
                                          "expected_key_id":old_key})
        self.assertEqual((self.workspace/"nodes.json").read_bytes(), before)
        self.assertEqual(self.console.nodes.registered()[0]["key_id"], new_key)

    def test_explicit_device_key_rotation_can_restart_report_sequence(self):
        self.policy()
        self.console.receive_node_report(self.report(sequence=100))
        self.console.unregister_node({"device_id":"edge-69","confirm":"UNREGISTER_NODE",
                                      "expected_key_id":self.device_key_id})
        with self.assertRaisesRegex(NodeError, "retired"):
            self.console.register_node(self.entry)
        replacement = Ed25519PrivateKey.generate()
        new_id=public_key_id(replacement.public_key())
        (self.device_trust/(new_id+".pem")).write_bytes(replacement.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo))
        self.console.register_node({**self.entry, "key_id":new_id})
        # A former signed receipt is retained but cannot assert current health
        # after explicit re-enrollment with a new device identity key.
        self.assertEqual(self.console.node_states()[0]["state"], "REKEY_PENDING")
        payload=json.loads(self.report(sequence=101))["payload"]
        payload["report_sequence"]=1
        signed=signed_report(payload,replacement)
        self.assertFalse(self.console.receive_node_report(signed)["duplicate"])
        self.assertEqual(self.console.node_states()[0]["report_sequence"],1)

    def test_legacy_registry_migrates_atomically_and_retires_removed_key(self):
        from policy_server import intel
        # A v1 registry remains readable until the next authorized mutation.
        path=self.workspace/"nodes.json"
        intel.write_json(path,{"format":1,"nodes":[self.entry]})
        self.assertEqual(self.console.nodes.registered(),[self.entry])
        self.console.unregister_node({"device_id":"edge-69","confirm":"UNREGISTER_NODE",
                                      "expected_key_id":self.device_key_id})
        upgraded=intel.read_json(path)
        self.assertEqual(upgraded["format"],2)
        self.assertEqual(upgraded["nodes"],[])
        self.assertEqual(upgraded["retired_key_ids"],[self.device_key_id])
        with self.assertRaises(NodeError):
            self.console.register_node(self.entry)

    def test_symlinked_node_lock_cannot_mutate_registry(self):
        victim=self.root/"victim"
        victim.write_text("untouched")
        lock_path=self.workspace/"nodes-state"/".nodes.lock"
        # Initial node enrollment creates the legitimate lock. Simulate an
        # attacker swapping that entry before a subsequent write attempt.
        lock_path.unlink()
        lock_path.symlink_to(victim)
        with self.assertRaises((OSError,NodeError)):
            self.console.unregister_node({"device_id":"edge-69",
                                          "confirm":"UNREGISTER_NODE", "expected_key_id":self.device_key_id})
        self.assertEqual(victim.read_text(),"untouched")
        self.assertEqual(self.console.nodes.registered()[0]["device_id"],"edge-69")

    def test_local_attestation_uses_existing_signed_inbox_and_dns_runtime(self):
        applied,inbox=self.policy()
        admin=self.root/"not-invoked"
        local=build_local_payload(device="edge-69",address="192.168.7.69",
                                  applied=applied,inbox=inbox,trust_dir=self.policy_trust,
                                  dns_admin=admin,report_sequence=9,
                                  attest=lambda _p,_digest:True,
                                  probe=lambda *args,**kwargs:3)
        self.assertEqual(local["attestation"],"ATTESTED")
        self.assertEqual(local["format"],4)
        self.assertEqual(local["probe"],{
            "domain":"blocked.example.org","udp":True,"tcp":True,"baseline":None})
        fail=build_local_payload(device="edge-69",address="192.168.7.69",
                                 applied={**applied,"policy_sha256":"b"*64},
                                 inbox=inbox,trust_dir=self.policy_trust,dns_admin=admin,
                                 report_sequence=10,attest=lambda *_:True)
        self.assertEqual(fail["attestation"],"FAILED")
        self.assertIsNone(fail["probe"]["domain"])

    def test_expired_inbox_is_not_a_current_attestation(self):
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        end = past + timedelta(minutes=30)
        policy = {"issued_at": past.isoformat(), "expires_at": end.isoformat(),
                  "rules": [{"domain": "google.com", "decision": "BLOCK", "scope": "SUBTREE",
                             "approved": True, "evidence": "expired-node-test",
                             "expires_at": end.isoformat()}]}
        env = sign_policy(canonical(policy), self.publisher_key, target="edge-69",
                          sequence=2, signed_at=past)
        (self.feed / "edge-69" / "current.json").write_bytes(canonical(env))
        inbox = self.root / "inbox.json"
        inbox.write_bytes(canonical(env))
        inbox.chmod(0o600)
        applied = {"sequence": 2, "policy_sha256": env["payload"]["policy_sha256"],
                   "payload_sha256": hashlib.sha256(canonical(env["payload"])).hexdigest(),
                   "applied_at": past.isoformat()}
        def boom(*_args, **_kwargs):
            raise AssertionError("expired inbox must not be attested or probed")
        local = build_local_payload(device="edge-69", address="192.168.7.69",
                                    applied=applied, inbox=inbox, trust_dir=self.policy_trust,
                                    dns_admin=self.root / "admin", report_sequence=4,
                                    attest=boom, probe=boom)
        self.assertEqual(local["attestation"], "EXPIRED")
        self.assertIsNone(local["probe"]["domain"])
        self.assertEqual(self.console.deployment()["state"], "PUBLICATION_EXPIRED")
        raw = signed_report(local, self.device_key)
        self.console.receive_node_report(raw)
        state = self.console.node_states()[0]
        self.assertEqual(state["state"], "POLICY_EXPIRED")
        self.assertIsNone(state["dns_applied"])
        self.assertEqual(state["published_sequence"], 2)
        self.assertEqual(state["policy_sha256"], applied["policy_sha256"])

        legacy = dict(local)
        legacy["attestation"] = "FAILED"
        legacy["report_sequence"] = 5
        self.console.receive_node_report(signed_report(legacy, self.device_key))
        self.assertEqual(self.console.node_states()[0]["state"], "POLICY_EXPIRED")

        mismatched = dict(legacy)
        mismatched["report_sequence"] = 6
        mismatched["policy_sha256"] = "c" * 64
        self.console.receive_node_report(signed_report(mismatched, self.device_key))
        mismatch = self.console.node_states()[0]
        self.assertEqual(mismatch["state"], "POLICY_MISMATCH")
        self.assertIs(mismatch["dns_applied"], False)

    def test_failed_report_against_a_current_feed_is_not_relabelled_expired(self):
        self.policy()
        raw = self.report(sequence=3, attestation="FAILED")
        self.console.receive_node_report(raw)
        state = self.console.node_states()[0]
        self.assertEqual(state["state"], "DNS_ATTESTATION_FAILED")
        self.assertIsNone(state["dns_applied"])
        self.assertEqual(state["published_sequence"], 7)

    def test_unprivileged_sender_checks_signed_body_and_tls_receipt(self):
        from aleph_policy_sync.telemetry import send
        from unittest.mock import patch
        self.policy()
        raw=self.report(sequence=12)
        def accept(request):
            self.assertEqual(request.data, raw)
            self.assertEqual(request.get_method(), "POST")
            return canonical({"accepted":True,"duplicate":False,
                              "device":"edge-69","report_sequence":12})
        with patch("aleph_policy_sync.telemetry.os.geteuid",return_value=12345), \
             patch("aleph_policy_sync.telemetry._regular_read",return_value=raw):
            answer=send(report_file=self.root/"outbox.json",
                        url="https://ops.example.org/v1/nodes/report",
                        expected_device="edge-69",key_id=self.device_key_id,
                        trust_dir=self.device_trust,post=accept)
            self.assertTrue(answer["accepted"])
            with self.assertRaises(TelemetryError):
                send(report_file=self.root/"outbox.json",
                     url="http://ops.example.org/v1/nodes/report",
                     expected_device="edge-69",key_id=self.device_key_id,
                     trust_dir=self.device_trust,post=accept)
            with self.assertRaises(TelemetryError):
                send(report_file=self.root/"outbox.json",
                     url="https://ops.example.org/v1/nodes/report",
                     expected_device="edge-69",key_id=self.device_key_id,
                     trust_dir=self.device_trust,
                     post=lambda _:canonical({"accepted":True,"duplicate":False,
                                              "device":"edge-69","report_sequence":999}))

    def test_bounded_http_worker_limit_configuration(self):
        from policy_server.console import BoundedThreadingHTTPServer
        with self.assertRaises(ValueError):
            BoundedThreadingHTTPServer(("127.0.0.1",0),handler_for(self.console,
                                       "http://127.0.0.1:8765"), max_handlers=0)
        server=BoundedThreadingHTTPServer(("127.0.0.1",0),handler_for(self.console,
                                          "http://127.0.0.1:8765"),max_handlers=1)
        self.addCleanup(server.server_close)
        self.assertTrue(server._slots.acquire(blocking=False))
        self.assertFalse(server._slots.acquire(blocking=False))
        server._slots.release()

    def test_http_signed_endpoint_is_distinct_from_operator_bearer(self):
        self.policy()
        svc=self.console
        server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(svc,"http://127.0.0.1:8765"))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(thread.join,2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(path,raw,headers=None):
            client=HTTPConnection("127.0.0.1",server.server_port,timeout=3)
            head={"Host":"127.0.0.1:8765","Content-Type":"application/json", **(headers or {})}
            client.putrequest("POST",path,skip_host=True)
            for key,value in head.items():client.putheader(key,value)
            client.putheader("Content-Length",str(len(raw)))
            client.endheaders(raw)
            response=client.getresponse()
            status=response.status
            result=json.loads(response.read())
            client.close()
            return status,result
        raw=self.report()
        self.assertEqual(request("/v1/nodes/report",raw)[0],200)
        self.assertEqual(request("/v1/nodes/report",raw)[1]["duplicate"],True)
        self.assertEqual(request("/v1/nodes/report",raw,{"Origin":"https://evil.example"})[0],403)
        self.assertEqual(request("/v1/nodes/report",raw,{"Authorization":"Bearer bad"})[0],400)
        self.assertEqual(request("/v1/nodes/report",raw+b"tampered")[0],401)


    @unittest.skipUnless(os.geteuid()==0,"root-only telemetry collection fixture")
    def test_root_collection_durability_and_outbox_permissions(self):
        applied,inbox=self.policy()
        apply_path=self.root/"applied.json"
        apply_path.write_bytes(canonical(applied));apply_path.chmod(0o600)
        key_file=self.root/"device.pem"
        key_file.write_bytes(self.device_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()));key_file.chmod(0o600)
        state=self.root/"root-state";state.mkdir(mode=0o700)
        outbox=self.root/"outbox";outbox.mkdir(mode=0o750)
        for sequence in (1,2):
            result=collect(device="edge-69",address="192.168.7.69",state_dir=state,
                           outbox_dir=outbox,key_file=key_file,applied_path=apply_path,
                           inbox=inbox,trust_dir=self.policy_trust,dns_admin=self.root/"admin",
                           sender_group="root",
                           attest=lambda *_:True,probe=lambda *args,**kwargs:3)
            self.assertEqual(result["report_sequence"],sequence)
            raw=(outbox/"report.json").read_bytes()
            payload=verify_report(raw,expected_device="edge-69",
                                  expected_key_id=self.device_key_id,
                                  trust_dir=self.device_trust)
            self.assertEqual(payload["report_sequence"],sequence)
            self.assertEqual((outbox/"report.json").stat().st_mode & 0o777,0o640)


if __name__=="__main__":
    unittest.main()
