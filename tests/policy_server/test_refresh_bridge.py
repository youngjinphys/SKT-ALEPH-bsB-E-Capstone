"""Offline proof that GUI refresh never receives the Google credential or signs DNS."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import os
import socket
from pathlib import Path
import tempfile
import threading
import time
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/"apps/policy-server/src"), str(ROOT/"apps/dns-agent/src"),
                str(ROOT/"apps/policy-sync/src")]

from policy_server import intel
from policy_server.console import ConsoleConflict, ConsoleError, ConsoleService, handler_for
from policy_server.refresh_bridge import BridgeError, RefreshServer, RefreshClient, RUN_ID, serve


URL = "https://confirmed-malicious-test.example.org/phish"
GSB = json.dumps({"threats":[{"url":URL,"threatTypes":["SOCIAL_ENGINEERING"]}],
                  "cacheDuration":"300s"}).encode()


def verified_evidence(now=None):
    now = now or datetime.now(timezone.utc)
    urls = intel.collect_urls((URL+"\n").encode(), source="openphish", fetched_at=now)
    return intel.verify_collected(urls,"fake-gsb-key",checked_at=now,
                                   fetch=lambda *a,**k:GSB)


class FakeCollector:
    def __init__(self, verified):
        self.verified = verified
        self.latest = {"run":"20261103T000000Z-0123456789",
                       "fingerprint":intel.verification_fingerprint(verified),
                       "verified":1, "review_proposals":1,
                       "checked_at":verified["checked_at"],
                       "unassigned_expressions":0}
        self.calls=[]

    def request(self, action, **kwargs):
        self.calls.append((action, kwargs))
        if action=="status":
            return {"state":"SUCCESS","latest":self.latest,
                    "requested_at":None,"completed_at":None,
                    "cooldown_seconds":0,"error_code":None}
        if action=="start":
            return {"state":"RUNNING","accepted":True}
        if action=="snapshot":
            if kwargs["run"]!=self.latest["run"]:
                raise BridgeError("not latest")
            return {**self.latest,"verified_snapshot":self.verified}
        raise AssertionError(action)


class CollectorGuiTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.state=self.root/"collector"
        self.state.mkdir(mode=0o700)
        self.workspace=self.root/"reviewer"
        self.workspace.mkdir(mode=0o700)
        self.token=self.root/"token"
        self.token.write_text("c"*48)
        self.token.chmod(0o600)
        self.key=self.state/"google-key"
        self.key.write_text("secret-test-gsb-key")
        self.key.chmod(0o600)
        self.verified=verified_evidence()
        self.client=FakeCollector(self.verified)
        self.gui=ConsoleService(self.workspace,self.token,refresh_client=self.client)

    def import_request(self, confirm="IMPORT_VERIFIED", revision="NOT_PRESENT", fingerprint=None):
        return {"confirm":confirm,"run":self.client.latest["run"],
                "fingerprint":fingerprint or self.client.latest["fingerprint"],
                "review_revision":revision,
                "context_revision":self.gui.intel_status().get("context_revision")}


    def test_import_preview_binds_evidence_even_without_review_changes(self):
        # Simulate a second operator replacing only verified.json while the
        # first operator is confirming a preview. Reviews remain absent.
        intel.write_json(self.workspace/"verified.json", self.verified)
        preview = self.gui.intel_status()
        pending = self.import_request()
        # The public preview must expose a combined evidence+reviews token.
        self.assertIn("context_revision", preview)
        pending["context_revision"] = preview["context_revision"]
        replacement = verified_evidence(datetime.now(timezone.utc)+timedelta(seconds=1))
        intel.write_json(self.workspace/"verified.json", replacement)
        before = (self.workspace/"verified.json").read_bytes()
        with self.assertRaises(ConsoleConflict):
            self.gui.adopt_intel(pending)
        self.assertEqual((self.workspace/"verified.json").read_bytes(), before)
        self.assertFalse((self.workspace/"reviews.json").exists())

    def test_client_rejects_world_readable_or_non_socket_endpoints(self):
        path=self.root/"fake-refresh.sock"
        path.write_text("not an IPC endpoint")
        client=RefreshClient(path)
        with self.assertRaises(BridgeError):
            client.request("status")
        path.unlink()
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            os.chmod(path,0o666)
            with self.assertRaisesRegex(BridgeError,"unsafe permissions"):
                client.request("status")
        with self.assertRaises(BridgeError):
            RefreshClient(Path("../relative.sock"))

    @unittest.skipIf(os.geteuid()==0,"Unix socket SO_PEERCRED integration needs non-root caller")
    def test_real_unix_socket_uses_kernel_authenticated_console_uid(self):
        path=self.root/"collector.sock"
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            os.chmod(path,0o660)
            listener.listen(4)
            worker=RefreshServer(self.state,self.key,os.geteuid(),
                                 refresher=lambda **kw:None)
            task=threading.Thread(target=lambda:serve(worker,listener),daemon=True)
            task.start()
            client=RefreshClient(path)
            result=client.request("status")
            self.assertEqual(result["state"],"IDLE")
            self.assertIsNone(result["latest"])
            rejected=None
            try:
                client.request("shell")
            except BridgeError as exc:
                rejected=exc
            self.assertIsNotNone(rejected)
            accepted=client.request("start")
            self.assertTrue(accepted["accepted"])
            for _ in range(100):
                if client.request("status")["state"]=="SUCCESS":break
                time.sleep(.01)
            self.assertEqual(client.request("status")["state"],"SUCCESS")
            self.assertFalse(client.request("start")["accepted"])

    def test_refresher_pins_peer_identity_and_rejects_arbitrary_operations(self):
        completed=threading.Event()
        def collector(*,state_dir,api_key_file,source,limit,accept_terms,
                      ack_disclosure,ack_noncommercial):
            self.assertEqual(api_key_file,self.key)
            self.assertEqual(source,"openphish")
            self.assertEqual(limit,100)
            self.assertTrue(accept_terms and ack_disclosure and ack_noncommercial)
            runs=state_dir/"runs"
            runs.mkdir(mode=0o700,exist_ok=True)
            name="20261103T000000Z-0123456789"
            dest=runs/name
            dest.mkdir(mode=0o700)
            verified=verified_evidence()
            template=intel.review_template(verified)
            intel.write_json(dest/"verified.json",verified)
            intel.write_json(dest/"review-template.json",template)
            intel.write_json(state_dir/"latest.json",{
                "run":name, "verified":len(verified["entries"]),
                "review_proposals":len(template["reviews"])})
            completed.set()
            return {"run_dir":str(dest)}
        server=RefreshServer(self.state,self.key,console_uid=12345,refresher=collector)
        with self.assertRaises(BridgeError):
            server.handle(b'{"action":"start"}',peer_uid=12346)
        for invalid in (b'{"action":"start","source":"https://evil.invalid"}',
                        b'{"action":"shell"}',b'{"action":"snapshot","run":"../secret"}'):
            with self.assertRaises(BridgeError):
                server.handle(invalid,peer_uid=12345)
        result=server.handle(b'{"action":"start"}',peer_uid=12345)
        self.assertTrue(result["accepted"])
        self.assertFalse(server.handle(b'{"action":"start"}',peer_uid=12345)["accepted"])
        self.assertTrue(completed.wait(3))
        for _ in range(100):
            if server.status()["state"]=="SUCCESS":break
            time.sleep(.01)
        self.assertEqual(server.status()["state"],"SUCCESS")
        preview=server.handle(b'{"action":"status"}',peer_uid=12345)
        self.assertEqual(preview["latest"]["review_proposals"],1)
        self.assertNotIn(URL,json.dumps(preview))
        raw=server.handle(b'{"action":"snapshot","run":"20261103T000000Z-0123456789"}',
                          peer_uid=12345)
        self.assertEqual(raw["verified_snapshot"]["entries"][0]["url"],URL)
        self.assertEqual(raw["fingerprint"],
                         intel.verification_fingerprint(raw["verified_snapshot"]))
        self.assertFalse(server.start()["accepted"])
        self.assertEqual(server.start()["state"],"COOLDOWN")
        self.assertEqual(self.key.read_text(),"secret-test-gsb-key")
        recovered=RefreshServer(self.state,self.key,console_uid=12345,refresher=collector)
        self.assertEqual(recovered.status()["state"],"SUCCESS")
        self.assertGreater(recovered.status()["cooldown_seconds"],0)

    def test_failed_provider_does_not_discard_previous_verified_record(self):
        saved=verified_evidence()
        intel.write_json(self.workspace/"verified.json",saved)
        def broken(**_):
            raise RuntimeError("GSB unavailable or malformed")
        server=RefreshServer(self.state,self.key,console_uid=12345,refresher=broken)
        self.assertTrue(server.start()["accepted"])
        for _ in range(100):
            if server.status()["state"]=="ERROR":break
            time.sleep(.01)
        self.assertEqual(server.status()["state"],"ERROR")
        self.assertEqual(server.status()["error_code"],"COLLECTION_FAILED")
        self.assertNotIn("malformed",json.dumps(server.status()))
        self.assertEqual(intel.read_json(self.workspace/"verified.json"),saved)
        self.assertEqual(self.gui.intel_status()["state"],"SUCCESS")

    def test_import_resets_approvals_only_after_confirmation_with_private_backup(self):
        self.assertEqual(self.gui.intel_status()["latest"]["verified"],1)
        self.assertNotIn(URL,json.dumps(self.gui.intel_status()))
        with self.assertRaises(ConsoleError):
            self.gui.start_intel_refresh({"accept_openphish_terms":True})
        result=self.gui.start_intel_refresh({
            "accept_openphish_terms":True,"ack_url_disclosure":True,
            "ack_noncommercial":True})
        self.assertTrue(result["accepted"])
        self.assertEqual(self.gui.reviews()["missing"],True)
        first=self.gui.adopt_intel(self.import_request())
        self.assertTrue(first["imported"])
        state=self.gui.reviews()
        self.assertFalse(state["missing"])
        self.assertEqual(state["items"][0]["approved"],False)
        self.assertFalse(first["published"])
        self.assertFalse((self.workspace/"private-policy-key").exists())
        # After explicit human approval, the next imported run must not reuse it.
        item=state["items"][0]
        self.gui.update_review({"id":item["id"],"revision":item["revision"],
                                "fingerprint":state["fingerprint"],
                                "approved":True, "acknowledge_subtree":True,
                                "reviewer":"reviewer-1",
                                "reason":"Independent review of domain-level blocking scope"})
        approved=self.gui.reviews()
        self.assertTrue(approved["items"][0]["approved"])
        with self.assertRaises(ConsoleConflict):
            self.gui.adopt_intel(self.import_request(revision="NOT_PRESENT"))
        self.client.verified=verified_evidence(now=datetime.now(timezone.utc)+timedelta(seconds=1))
        self.client.latest["run"]="20261103T000001Z-0123456789"
        self.client.latest["fingerprint"]=intel.verification_fingerprint(self.client.verified)
        second=self.gui.adopt_intel(self.import_request(revision=approved["review_set_revision"]))
        self.assertTrue(second["imported"])
        self.assertFalse(self.gui.reviews()["items"][0]["approved"])
        archive=list((self.workspace/"evidence-archive").iterdir())
        self.assertTrue(archive)
        self.assertTrue(any((folder/"reviews.json").exists() for folder in archive))
        self.assertTrue(any(intel.read_json(folder/"reviews.json")["reviews"][0]["approved"]
                            for folder in archive if (folder/"reviews.json").exists()))
        self.assertEqual((self.workspace/"verified.json").stat().st_mode & 0o777,0o600)
        self.assertFalse(any((self.workspace/"drafts").iterdir()))

    def test_stale_snapshot_and_change_conflicts_preserve_operator_records(self):
        intel.write_json(self.workspace/"verified.json",self.verified)
        before=(self.workspace/"verified.json").read_bytes()
        with self.assertRaises(ConsoleError):
            self.gui.adopt_intel(self.import_request(confirm="yes"))
        with self.assertRaises(ConsoleConflict):
            self.gui.adopt_intel(self.import_request(revision="stale"))
        self.client.latest["fingerprint"]="f"*64
        with self.assertRaises(ConsoleError):
            self.gui.adopt_intel(self.import_request())
        self.assertEqual((self.workspace/"verified.json").read_bytes(),before)

    def test_authenticated_http_endpoint_never_discloses_candidate_urls(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),
            handler_for(self.gui,"http://127.0.0.1:8765"))
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        self.addCleanup(worker.join,2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def req(method,path,body=None,headers=None):
            conn=HTTPConnection("127.0.0.1",server.server_port,timeout=2)
            head={"Host":"127.0.0.1:8765",**(headers or {})}
            raw=json.dumps(body).encode() if body is not None else None
            conn.putrequest(method,path,skip_host=True)
            for k,v in head.items():conn.putheader(k,v)
            if raw is not None:
                conn.putheader("Content-Type","application/json")
                conn.putheader("Content-Length",str(len(raw)))
            conn.endheaders(raw)
            response=conn.getresponse()
            status,content=response.status,response.read()
            conn.close()
            return status,content
        auth={"Authorization":"Bearer "+self.gui.token}
        self.assertEqual(req("GET","/api/intel")[0],401)
        status,body=req("GET","/api/intel",headers=auth)
        self.assertEqual(status,200)
        self.assertNotIn(URL,body.decode())
        self.assertEqual(req("POST","/api/intel/refresh",{
            "accept_openphish_terms":True,"ack_url_disclosure":True,"ack_noncommercial":True
        },auth)[0],403)
        self.assertEqual(req("POST","/api/intel/refresh",{
            "accept_openphish_terms":True,"ack_url_disclosure":True,"ack_noncommercial":True
        },{**auth,"Origin":"http://127.0.0.1:8765"})[0],202)
        self.assertEqual(req("POST","/api/intel/import",{
            **self.import_request()
        },{**auth,"Origin":"http://127.0.0.1:8765"})[0],200)
        self.assertNotIn(URL,req("GET","/api/intel",headers=auth)[1].decode())


if __name__ == "__main__":
    unittest.main()
