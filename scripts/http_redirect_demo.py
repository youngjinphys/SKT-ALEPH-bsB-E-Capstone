#!/usr/bin/env python3
"""Plain-HTTP comparison fixture; two loopback listeners, no DNS integration.

The redirect destination is fixed at startup. Request Host, path, query, cookies,
and body never become the redirect target or a portal identifier. This does not
intercept HTTPS or change DNS, routing, firewall rules, or a browser's settings.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import threading

ROOT = Path(__file__).resolve().parents[1]
PORTAL = ROOT / "apps" / "warning-portal" / "public"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/phishing-block.html": ("phishing-block.html", "text/html; charset=utf-8"),
    "/phishing-warning-continue.html": (
        "phishing-warning-continue.html", "text/html; charset=utf-8"
    ),
    "/portal.css": ("portal.css", "text/css; charset=utf-8"),
    "/portal.js": ("portal.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
CSP = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; form-action 'none'; connect-src 'none'; "
    "script-src 'self'; style-src 'self'; img-src 'self'; font-src 'none'"
)


def lab_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("lab port must be 1024..65535")
    return port


class QuietHandler(BaseHTTPRequestHandler):
    server_version = "ALEPH-Lab"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        # Do not collect visited paths, URL tokens, cookies, or client identities.
        pass

    def respond(self, code, body=b"", content_type="text/plain; charset=utf-8",
                *, location=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Connection", "close")
        if location is not None:
            self.send_header("Location", location)
        if code == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        self.close_connection = True
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler normally reflects details of malformed requests.
        self.respond(code, b"Request rejected by the local demonstration.\n")

    def do_POST(self):
        self.respond(405, b"This demonstration does not accept submissions.\n")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST
    do_CONNECT = do_POST


def redirect_handler(portal_port: int):
    # Construct only from a validated port, never from a request header or URL.
    portal_port = lab_port(str(portal_port))
    destination = f"http://127.0.0.1:{portal_port}/phishing-block.html"

    class RedirectHandler(QuietHandler):
        def do_GET(self):
            self.respond(302, location=destination)

        do_HEAD = do_GET

    return RedirectHandler


def portal_handler():
    # Only explicit public assets are served: no arbitrary paths or directories.
    assets = {
        route: ((PORTAL / filename).read_bytes(), mime)
        for route, (filename, mime) in ASSETS.items()
    }

    class PortalHandler(QuietHandler):
        def do_GET(self):
            route = self.path.split("?", 1)[0]
            asset = assets.get(route)
            if asset is None:
                self.respond(404, b"Unknown demonstration page.\n")
                return
            body, mime = asset
            self.respond(200, body, mime)

        do_HEAD = do_GET

    return PortalHandler


class LabServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(3)
        return connection, address


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redirect-port", type=lab_port, default=38080)
    parser.add_argument("--portal-port", type=lab_port, default=35173)
    args = parser.parse_args(argv)
    if args.redirect_port == args.portal_port:
        parser.error("redirect and portal ports must differ")

    stopped = threading.Event()
    previous_signals = {}
    try:
        with ExitStack() as stack:
            # Bind both listeners before starting either. Partial startup closes
            # already-open sockets instead of leaving a misleading live fixture.
            portal = stack.enter_context(
                LabServer(("127.0.0.1", args.portal_port), portal_handler())
            )
            redirect = stack.enter_context(
                LabServer(("127.0.0.1", args.redirect_port), redirect_handler(args.portal_port))
            )
            for server in (portal, redirect):
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                stack.callback(worker.join, 2)
                stack.callback(server.shutdown)
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous_signals[sig] = signal.signal(sig, lambda *_: stopped.set())
            print(
                f"HTTP comparison only: http://127.0.0.1:{args.redirect_port}/\n"
                f"302 destination: http://127.0.0.1:{args.portal_port}/phishing-block.html\n"
                "No DNS policy or HTTPS interception is connected. Ctrl+C stops both listeners.",
                flush=True,
            )
            stopped.wait()
    except OSError as exc:
        parser.exit(2, f"Cannot start loopback HTTP demonstration: {exc}\n")
    finally:
        for sig, handler in previous_signals.items():
            signal.signal(sig, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
