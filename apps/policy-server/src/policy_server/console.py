"""Loopback-only, authenticated operator console for reviewed DNS policy drafts.

The web account can review evidence and build *unsigned* drafts. It has no
private signing key, root publication privileges or DNS administration command.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
from urllib.parse import urlsplit

from dns_agent.policy import domain_name, parse_policy
from aleph_policy_sync.snapshot import _regular_read, device_id, verify_envelope
from . import intel
from .engine import compile_policy, evaluate_policy
from .console_assets import HTML, CSS, JS

_DRAFT = re.compile(r"policy-\d{8}T\d{6}Z-[0-9a-f]{12}\.json\Z")
_LIMIT = 65536


class ConsoleError(ValueError):
    """An operator operation was rejected without changing the live DNS service."""


def _private_dir(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ConsoleError("workspace must be a pre-created private directory")
    st = path.stat()
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise ConsoleError("workspace and drafts directories require caller ownership and mode 0700")


def _private_read(path: Path, limit: int = intel.MAX_ARTIFACT_BYTES) -> bytes:
    return _regular_read(path, limit, forbidden=0o077, owner=os.geteuid())


def _json_read(path: Path) -> dict:
    value = intel.parse_json(_private_read(path))
    if type(value) is not dict:
        raise ConsoleError("expected an object in private JSON artifact")
    return value


def _identity(review: dict) -> str:
    fields = [review[k] for k in ("domain", "url_sha256", "checked_at")]
    raw = json.dumps(fields, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def _text(value: object, low: int, high: int, label: str) -> str:
    if (not isinstance(value, str) or not low <= len(value) <= high
            or value != value.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ConsoleError(label + " has invalid length, whitespace or control characters")
    return value


def _audit(path: Path, operation: str, **fields) -> None:
    # A local operational convenience, NOT a tamper-proof approval or identity record.
    event = {"at": datetime.now(timezone.utc).isoformat(), "event": operation, **fields}
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise ConsoleError("unsafe audit log")
        os.write(fd, (json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


class ConsoleService:
    """Stateful, role-limited adapter around the real policy engines."""

    def __init__(self, workspace: Path, token_file: Path, *, feed_root: Path | None = None,
                 device: str | None = None, trust_dir: Path | None = None):
        self.workspace = Path(workspace)
        _private_dir(self.workspace)
        self.drafts_dir = self.workspace / "drafts"
        self.drafts_dir.mkdir(mode=0o700, exist_ok=True)
        _private_dir(self.drafts_dir)
        self.token = _private_read(Path(token_file), 1024).decode("ascii").strip()
        if not 32 <= len(self.token) <= 256 or any(
                ord(ch) <= 32 or ord(ch) > 126 for ch in self.token):
            raise ConsoleError("token file must hold a 32-256 character ASCII secret")
        self.feed_root, self.device, self.trust_dir = feed_root, device_id(device) if device is not None else None, trust_dir
        if any(x is not None for x in (feed_root, device, trust_dir)) and not all(
                x is not None for x in (feed_root, device, trust_dir)):
            raise ConsoleError("feed_root, device and trust_dir must be configured together")
        self.mutex = threading.RLock()

    @contextmanager
    def locked(self):
        with self.mutex:
            fd = os.open(self.workspace / ".console.lock",
                         os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
                    raise ConsoleError("unsafe console lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                os.close(fd)

    def _verified_reviews(self):
        try:
            verified = _json_read(self.workspace / "verified.json")
        except FileNotFoundError:
            return None, None, None
        template = intel.review_template(verified)
        try:
            reviewed = _json_read(self.workspace / "reviews.json")
        except FileNotFoundError:
            reviewed = template
        if (type(reviewed) is not dict or set(reviewed) != set(template) or
                any(reviewed[k] != template[k] for k in
                    ("kind", "format", "scope", "verification_sha256")) or
                not isinstance(reviewed["reviews"], list) or
                len(reviewed["reviews"]) != len(template["reviews"])):
            raise ConsoleError("review evidence changed: inspect the new dataset and explicitly reset reviews")
        for actual, original in zip(reviewed["reviews"], template["reviews"]):
            if (type(actual) is not dict or set(actual) != set(original)
                    or any(actual[key] != original[key]
                           for key in ("domain", "url_sha256", "checked_at"))
                    or type(actual["approved"]) is not bool
                    or type(actual["acknowledge_subtree"]) is not bool):
                raise ConsoleError("invalid or unbound review record; refuse policy generation")
        return verified, reviewed, template

    def reviews(self):
        verified, reviewed, template = self._verified_reviews()
        if verified is None:
            return {"missing": True, "fingerprint": None, "verified_at": None, "items": []}
        by_ref = {(e["domain"], e["url_sha256"], e["checked_at"]): e
                  for e in intel._verification_entries(verified)}
        items = []
        now = datetime.now(timezone.utc)
        for review in reviewed["reviews"]:
            matched = by_ref[(review["domain"], review["url_sha256"], review["checked_at"])]
            valid = (intel.parse_time(matched["valid_until"]) > now and
                     now - intel.parse_time(matched["checked_at"]) <
                     timedelta(minutes=30))
            items.append({**review, "id": _identity(review),
                          "threat_types": matched["threat_types"],
                          "valid_until": matched["valid_until"],
                          "fresh": valid, "source": matched["source"],
                          "status": matched["status"]})
        return {"missing": False, "fingerprint": template["verification_sha256"],
                "verified_at": verified["checked_at"], "items": items}

    def update_review(self, data: dict):
        if set(data) != {"id", "fingerprint", "approved", "acknowledge_subtree", "reviewer", "reason"}:
            raise ConsoleError("review update requires exact fields")
        if type(data["approved"]) is not bool or type(data["acknowledge_subtree"]) is not bool:
            raise ConsoleError("review approval fields must be booleans")
        reviewer = _text(data["reviewer"], 0, 80, "reviewer")
        reason = _text(data["reason"], 0, 400, "rationale")
        if data["approved"]:
            _text(reviewer, 2, 80, "reviewer")
            _text(reason, 15, 400, "rationale")
            if data["acknowledge_subtree"] is not True:
                raise ConsoleError("SUBTREE impact must be explicitly acknowledged")
        with self.locked():
            _, reviews, template = self._verified_reviews()
            if reviews is None or template["verification_sha256"] != data["fingerprint"]:
                raise ConsoleError("stale evidence fingerprint; reload and review again")
            target = next((x for x in reviews["reviews"] if _identity(x) == data["id"]), None)
            if target is None:
                raise ConsoleError("review candidate no longer exists")
            target.update(reviewer=reviewer, reason=reason, approved=data["approved"],
                          acknowledge_subtree=data["acknowledge_subtree"] if data["approved"] else False)
            intel.write_json(self.workspace / "reviews.json", reviews)
            _audit(self.workspace / "audit.jsonl", "review_updated",
                   reference=data["id"][:16], approved=target["approved"])
        return {"saved": True}

    def reset_reviews(self, data: dict):
        if data != {"confirm": "RESET_REVIEWS"}:
            raise ConsoleError("explicit RESET_REVIEWS confirmation required")
        with self.locked():
            verified = _json_read(self.workspace / "verified.json")
            template = intel.review_template(verified)
            intel.write_json(self.workspace / "reviews.json", template)
            _audit(self.workspace / "audit.jsonl", "reviews_reset",
                   fingerprint=template["verification_sha256"][:16])
        return {"reset": True}

    def build(self, data: dict):
        if (set(data) != {"fingerprint", "confirm_replacement", "acknowledge_user_notice"}
                or data["confirm_replacement"] is not True
                or data["acknowledge_user_notice"] is not True):
            raise ConsoleError("full replacement and user-notice acknowledgement required")
        with self.locked():
            verified, reviews, template = self._verified_reviews()
            if verified is None or data["fingerprint"] != template["verification_sha256"]:
                raise ConsoleError("stale or missing verification evidence")
            policy = intel.build_policy(
                verified, reviews, acknowledge_replacement=True, acknowledge_notice=True)
            parsed = parse_policy(json.dumps(policy, ensure_ascii=True).encode())
            name = datetime.now(timezone.utc).strftime("policy-%Y%m%dT%H%M%SZ-")
            name += secrets.token_hex(6) + ".json"
            intel.write_json(self.drafts_dir / name, policy)
            _audit(self.workspace / "audit.jsonl", "unsigned_policy_built",
                   draft=name, sha256=parsed.digest, rules=len(parsed.rules))
        return {"draft": name, "sha256": parsed.digest, "rules": len(parsed.rules),
                "expires_at": parsed.expires_at.isoformat(), "published": False, "signed": False}

    def drafts(self):
        result = []
        for path in sorted(self.drafts_dir.iterdir(), reverse=True)[:200]:
            if not _DRAFT.fullmatch(path.name):
                continue
            raw = _private_read(path)
            policy = parse_policy(raw)
            result.append({"name": path.name, "sha256": policy.digest,
                           "rules": len(policy.rules),
                           "expires_at": policy.expires_at.isoformat(),
                           "expired": policy.expires_at <= datetime.now(timezone.utc),
                           "signed": False, "published": False})
        return result

    def download(self, name: str) -> bytes:
        if not _DRAFT.fullmatch(name):
            raise ConsoleError("invalid draft identifier")
        raw = _private_read(self.drafts_dir / name)
        parse_policy(raw)
        return raw

    def engine_config(self):
        try:
            config = _json_read(self.workspace / "engine-config.json")
        except FileNotFoundError:
            return {"configured": False, "config": None}
        compile_policy(config)
        return {"configured": True, "config": config}

    def configure_engine(self, data: dict):
        snapshot = compile_policy(data)
        with self.locked():
            intel.write_json(self.workspace / "engine-config.json", data)
            _audit(self.workspace / "audit.jsonl", "proposal_config_updated",
                   version=snapshot.version)
        return {"configured": True, "version": snapshot.version, "enforcing": False}

    def evaluate(self, data: dict):
        if set(data) != {"domain"}:
            raise ConsoleError("evaluation requires exactly one domain")
        domain = domain_name(data["domain"])
        config = self.engine_config()["config"]
        if config is None:
            raise ConsoleError("save a proposal engine configuration first")
        result = evaluate_policy(domain, data={}, config=compile_policy(config))
        return {"proposal": result, "enforcing": False, "evidence_authenticated": False}

    def deployment(self, *, include_rules=False):
        if self.feed_root is None:
            return {"state": "NOT_CONFIGURED", "dns_applied": None,
                    "message": "No publisher feed and trust directory configured"}
        try:
            raw = _regular_read(Path(self.feed_root) / self.device / "current.json",
                                2 * 1024 * 1024)
            payload, parsed = verify_envelope(
                raw, expected_device=self.device, trust_dir=Path(self.trust_dir))
            return {"state": "SIGNED_FILE_VERIFIED", "device": self.device,
                    "sequence": payload["sequence"], "key_id": json.loads(raw)["key_id"], "policy_sha256": parsed.digest,
                    "rules": len(parsed.rules), "active_blocks":
                    len(parsed.blocked(datetime.now(timezone.utc))),
                    "expires_at": payload["valid_until"], "dns_applied": None,
                    "message": "Signed local feed file verified; HTTPS delivery and edge DNS apply not attested",
                    **({"rules": [{"domain": r.domain, "decision": r.decision,
                                    "approved": r.approved, "scope": "SUBTREE",
                                    "expires_at": r.expires_at.isoformat()}
                                   for r in parsed.rules]} if include_rules else {})}
        except FileNotFoundError:
            return {"state": "NO_PUBLISHED_FILE", "device": self.device,
                    "dns_applied": None}
        except (ValueError, OSError):
            return {"state": "VERIFICATION_FAILED", "device": self.device,
                    "dns_applied": None, "message": "Publication could not be verified"}

    def audit(self):
        try:
            raw = _private_read(self.workspace / "audit.jsonl", 4 * 1024 * 1024)
        except FileNotFoundError:
            return []
        return [json.loads(line) for line in raw.splitlines()[-100:]]

    def overview(self):
        state = self.reviews()
        return {"verified_at": state["verified_at"],
                "evidence_missing": state["missing"], "candidates": len(state["items"]),
                "approved": sum(bool(x["approved"]) for x in state["items"]),
                "fresh": sum(bool(x["fresh"]) for x in state["items"]),
                "drafts": len(self.drafts()), "deployment": self.deployment()}


def handler_for(service: ConsoleService, origin: str):
    target = urlsplit(origin)
    if (target.scheme not in ("http", "https") or not target.netloc
            or target.path not in ("", "/") or target.query or target.fragment
            or target.username or target.password):
        raise ConsoleError("origin must be an explicit http(s) URL without a path")
    if target.scheme == "http" and target.hostname not in ("127.0.0.1", "localhost"):
        raise ConsoleError("remote administration requires an HTTPS reverse proxy")
    expected_host = target.netloc

    class Handler(BaseHTTPRequestHandler):
        server_version = "ALEPH-Console"
        sys_version = ""

        def log_message(self, *args):
            # Do not log operator-supplied domains or bearer tokens.
            pass

        def _headers(self, code, mime, length, *, filename=None):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "img-src 'self' data:; connect-src 'self'; form-action 'none'; "
                             "base-uri 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
            self.end_headers()

        def _send(self, code, raw, mime="application/json; charset=utf-8", *, filename=None):
            self._headers(code, mime, len(raw), filename=filename)
            self.wfile.write(raw)

        def _json(self, code, data):
            self._send(code, (json.dumps(data, ensure_ascii=False, allow_nan=False) + "\n").encode())

        def _guard(self, write=False):
            if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") != expected_host:
                raise HttpError(400, "Invalid Host header")
            if self.headers.get("Origin") not in (None, origin):
                raise HttpError(403, "Cross-origin request rejected")
            if write and self.headers.get("Origin") != origin:
                raise HttpError(403, "Same-origin mutation required")
            if (len(self.headers.get_all("Authorization", [])) > 1
                    or len(self.headers.get_all("Origin", [])) > 1):
                raise HttpError(400, "Ambiguous authorization headers")
            authorization = self.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization, "Bearer " + service.token):
                raise HttpError(401, "Authentication required")

        def _body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                raise HttpError(415, "JSON content type required")
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                raise HttpError(400, "Invalid Content-Length") from None
            if not 0 < length <= _LIMIT:
                raise HttpError(413, "JSON payload exceeds allowed size")
            obj = intel.parse_json(self.rfile.read(length))
            if type(obj) is not dict:
                raise HttpError(400, "JSON request must be an object")
            return obj

        def _dispatch(self, write=False):
            path = urlsplit(self.path).path
            try:
                if not self.path.startswith("/api/") or "?" in self.path:
                    raise HttpError(404, "Unknown API route")
                self._guard(write)
                if not write:
                    if path == "/api/overview":
                        return self._json(200, service.overview())
                    if path == "/api/reviews":
                        return self._json(200, service.reviews())
                    if path == "/api/drafts":
                        return self._json(200, service.drafts())
                    if path == "/api/engine":
                        return self._json(200, service.engine_config())
                    if path == "/api/deployment":
                        return self._json(200, service.deployment(include_rules=True))
                    if path == "/api/audit":
                        return self._json(200, service.audit())
                    if path.startswith("/api/drafts/") and path.endswith("/download"):
                        name = path[len("/api/drafts/"):-len("/download")].strip("/")
                        return self._send(200, service.download(name),
                                          "application/json; charset=utf-8", filename=name)
                else:
                    body = self._body()
                    if path == "/api/reviews/save":
                        return self._json(200, service.update_review(body))
                    if path == "/api/reviews/reset":
                        return self._json(200, service.reset_reviews(body))
                    if path == "/api/build":
                        return self._json(201, service.build(body))
                    if path == "/api/engine":
                        return self._json(200, service.configure_engine(body))
                    if path == "/api/evaluate":
                        return self._json(200, service.evaluate(body))
                raise HttpError(404, "Unknown API route")
            except HttpError as exc:
                self._json(exc.status, {"error": str(exc)})
            except (ConsoleError, ValueError) as exc:
                self._json(422, {"error": str(exc)[:240]})
            except OSError:
                self._json(500, {"error": "Private file operation failed"})

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._dispatch()
            if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") != expected_host:
                return self._json(400, {"error": "Invalid Host header"})
            resources = {"/": (HTML, "text/html; charset=utf-8"),
                         "/console.css": (CSS, "text/css; charset=utf-8"),
                         "/console.js": (JS, "application/javascript; charset=utf-8")}
            if self.path not in resources:
                return self._json(404, {"error": "Not found"})
            content, mime = resources[self.path]
            self._send(200, content.encode("utf-8"), mime)

        def do_POST(self):
            self._dispatch(write=True)

    return Handler


class HttpError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path, help="existing 0700 reviewer-owned directory")
    parser.add_argument("--token-file", required=True, type=Path, help="0600 bearer token (32+ characters)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--origin", help="browser origin (use HTTPS via authenticated reverse proxy)")
    parser.add_argument("--feed-root", type=Path, help="optional local signed publisher feed root")
    parser.add_argument("--device-id", help="required with feed root")
    parser.add_argument("--trust-dir", type=Path, help="required with feed root")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the console as a dedicated unprivileged reviewer, never root")
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024-65535")
    service = ConsoleService(args.workspace, args.token_file, feed_root=args.feed_root,
                             device=args.device_id, trust_dir=args.trust_dir)
    origin = args.origin or "http://127.0.0.1:" + str(args.port)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(service, origin))
    print("ALEPH console bound to 127.0.0.1:" + str(args.port) + "; origin=" + origin, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
