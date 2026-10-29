"""Real loopback HTTP checks; no remote sites, DNS, or privileged ports."""
import argparse
from contextlib import contextmanager
import http.client
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("http_redirect_demo", ROOT / "scripts/http_redirect_demo.py")
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


@contextmanager
def running(handler):
    with demo.LabServer(("127.0.0.1", 0), handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            worker.join(2)


def request(port, method="GET", path="/", headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, path, headers=headers or {}, body=body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class RedirectDemoTests(unittest.TestCase):
    def test_cli_starts_and_stops_both_listeners(self):
        with socket.socket() as first, socket.socket() as second:
            first.bind(("127.0.0.1", 0))
            second.bind(("127.0.0.1", 0))
            redirect_port, portal_port = first.getsockname()[1], second.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts/http_redirect_demo.py"),
             "--redirect-port", str(redirect_port), "--portal-port", str(portal_port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while True:
                if process.poll() is not None:
                    self.fail(f"fixture exited before readiness: {process.communicate()}")
                try:
                    status, _, _ = request(redirect_port)
                    if status == 302:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    self.fail("fixture did not become ready")
                time.sleep(0.05)
            self.assertEqual(request(portal_port, path="/phishing-block.html")[0], 200)
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn("No DNS policy or HTTPS interception is connected", stdout)
            for port in (redirect_port, portal_port):
                with socket.socket() as check:
                    check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    check.bind(("127.0.0.1", port))
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def test_real_redirect_reaches_existing_block_portal(self):
        with running(demo.portal_handler()) as portal:
            with running(demo.redirect_handler(portal)) as redirect:
                status, headers, body = request(redirect)
                self.assertEqual(status, 302)
                self.assertEqual(headers["Location"], f"http://127.0.0.1:{portal}/phishing-block.html")
                self.assertEqual(body, b"")
                status, _, page = request(portal, path="/phishing-block.html")
                self.assertEqual(status, 200)
                self.assertEqual(page, (demo.PORTAL / "phishing-block.html").read_bytes())

    def test_host_path_query_and_referer_cannot_change_or_leak_to_destination(self):
        with running(demo.redirect_handler(35173)) as port:
            status, headers, body = request(
                port, path="//external.test/private?token=secret&next=https://external.test/",
                headers={"Host": "external.test", "Referer": "https://private.test/?session=secret"},
            )
            self.assertEqual(status, 302)
            self.assertEqual(headers["Location"], "http://127.0.0.1:35173/phishing-block.html")
            self.assertEqual(headers["Referrer-Policy"], "no-referrer")
            self.assertNotIn("secret", str(headers))
            self.assertEqual(body, b"")

    def test_head_keeps_location_without_response_body(self):
        with running(demo.redirect_handler(35173)) as port:
            status, headers, body = request(port, method="HEAD")
            self.assertEqual(status, 302)
            self.assertIn("Location", headers)
            self.assertEqual(body, b"")

    def test_post_is_rejected_without_redirect_or_echo(self):
        for handler in (demo.redirect_handler(35173), demo.portal_handler()):
            with running(handler) as port:
                status, headers, body = request(port, method="POST", body="private-submission")
                self.assertEqual(status, 405)
                self.assertEqual(headers["Allow"], "GET, HEAD")
                self.assertNotIn("Location", headers)
                self.assertNotIn(b"private-submission", body)

    def test_only_public_assets_can_be_read(self):
        with running(demo.portal_handler()) as port:
            for path in ("/../README.md", "/%2e%2e/README.md", "/.git/config", "/private/", "/not-found?secret=x"):
                status, _, body = request(port, path=path)
                self.assertEqual(status, 404, path)
                self.assertNotIn(path.encode(), body)
            status, headers, body = request(port, path="/portal.js?unused=secret")
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "text/javascript; charset=utf-8")
            self.assertEqual(body, (demo.PORTAL / "portal.js").read_bytes())

    def test_portal_headers_and_head_match_public_asset(self):
        with running(demo.portal_handler()) as port:
            status, headers, body = request(port, method="HEAD", path="/phishing-block.html")
            self.assertEqual(status, 200)
            self.assertEqual(int(headers["Content-Length"]), (demo.PORTAL / "phishing-block.html").stat().st_size)
            self.assertEqual(body, b"")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertIn("form-action 'none'", headers["Content-Security-Policy"])
            self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_cli_ports_are_bounded_and_separate(self):
        for value in ("53", "0", "65536", "invalid", "35173\r\nLocation: x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                demo.lab_port(value)
        self.assertEqual(demo.lab_port("35173"), 35173)
        with self.assertRaises(SystemExit) as result:
            demo.main(["--redirect-port", "35173", "--portal-port", "35173"])
        self.assertEqual(result.exception.code, 2)

    def test_bind_failure_leaves_no_partial_listener(self):
        with socket.socket() as occupied, socket.socket() as candidate:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            candidate.bind(("127.0.0.1", 0))
            portal_port = candidate.getsockname()[1]
            candidate.close()
            with self.assertRaises(SystemExit) as result:
                demo.main(["--redirect-port", str(occupied.getsockname()[1]), "--portal-port", str(portal_port)])
            self.assertEqual(result.exception.code, 2)
            with socket.socket() as check:
                check.bind(("127.0.0.1", portal_port))


if __name__ == "__main__":
    unittest.main()
