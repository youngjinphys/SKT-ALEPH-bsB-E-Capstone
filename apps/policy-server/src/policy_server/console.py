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
from .nodes import Nodes, NodeError, NodeConflict
from .refresh_bridge import RefreshClient, BridgeError, RUN_ID
from aleph_policy_sync.telemetry import MAX_REPORT_BYTES

_DRAFT = re.compile(r"policy-\d{8}T\d{6}Z-[0-9a-f]{12}\.json\Z")
_LIMIT = 65536


class ConsoleError(ValueError):
    """An operator operation was rejected without changing the live DNS service."""


class ConsoleConflict(ConsoleError):
    """An on-screen edit was based on an older review revision."""


def _revision(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":"), allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


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


def _evidence_state(item: dict, now: datetime) -> tuple[bool, bool, str]:
    """Match the real compiler's evidence clock, without implying DNS protection."""
    observed = intel.parse_time(item["checked_at"])
    expires = intel.parse_time(item["valid_until"])
    fresh = (observed <= now + timedelta(seconds=60) and
             expires > now and now - observed < timedelta(minutes=30))
    if intel.is_protected(item["domain"]):
        return fresh, False, "SHARED_HOSTING_BOUNDARY"
    if observed > now + timedelta(seconds=60):
        return False, False, "EVIDENCE_FROM_FUTURE"
    if expires <= now:
        return False, False, "EVIDENCE_EXPIRED"
    if now - observed >= timedelta(minutes=30):
        return False, False, "EVIDENCE_TOO_OLD"
    return True, True, "REVIEWABLE"


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
                 device: str | None = None, trust_dir: Path | None = None,
                 node_trust_dir: Path | None = None,
                 refresh_socket: Path | None = None, refresh_client=None):
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
        self.nodes = Nodes(self.workspace, node_trust_dir)
        self.refresh_client = (refresh_client if refresh_client is not None else
                               RefreshClient(refresh_socket) if refresh_socket is not None else None)

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


    def _review_revision(self):
        try:
            existing = _json_read(self.workspace / "reviews.json")
        except FileNotFoundError:
            return "NOT_PRESENT"
        return _revision(existing)

    def intel_status(self):
        """Read-only preview: never deliver suspect URLs to the browser."""
        if self.refresh_client is None:
            return {"state": "NOT_CONFIGURED", "latest": None, "review_revision": None,
                    "message": "Optional local collector bridge is not installed"}
        try:
            data = self.refresh_client.request("status")
        except (BridgeError, OSError):
            return {"state": "UNAVAILABLE", "latest": None, "review_revision": None,
                    "message": "Collector socket/service unavailable"}
        if type(data) is not dict or type(data.get("state")) is not str:
            raise ConsoleError("invalid collector status response")
        from .evidence_store import _context
        # Read both tokens under one workspace lock. Review-only binding misses
        # an independently replaced verified.json, including first-time imports.
        with self.locked():
            context, _ = _context(self)
            review = self._review_revision()
        return {**data, "review_revision": review, "context_revision": context}

    def start_intel_refresh(self, data: dict):
        if (type(data) is not dict or set(data) !=
                {"accept_openphish_terms", "ack_url_disclosure", "ack_noncommercial"}
                or any(data[key] is not True for key in data)):
            raise ConsoleError("explicit OpenPhish terms, Google URL disclosure and non-commercial acknowledgements required")
        if self.refresh_client is None:
            raise ConsoleError("local collector bridge is not configured")
        result = self.refresh_client.request("start")
        if (type(result) is not dict or result.get("state") not in
                ("RUNNING", "COOLDOWN") or type(result.get("accepted")) is not bool):
            raise ConsoleError("invalid collector acknowledgement")
        _audit(self.workspace / "audit.jsonl", "intel_refresh_requested",
               accepted=result["accepted"], outcome=result["state"])
        return result

    def adopt_intel(self, data: dict):
        """Explicitly stage one newest verified snapshot; old reviews archived first.

        A new GSB observation never inherits an older approval. Neither this
        operation nor the collection command signs, promotes or applies policy.
        """
        if (type(data) is not dict or set(data) !=
                {"run", "fingerprint", "review_revision", "context_revision", "confirm"}
                or data["confirm"] != "IMPORT_VERIFIED"
                or type(data["run"]) is not str or not RUN_ID.fullmatch(data["run"])
                or type(data["fingerprint"]) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", data["fingerprint"])):
            raise ConsoleError("explicit run-bound verified-evidence import required")
        if self.refresh_client is None:
            raise ConsoleError("local collector bridge is not configured")
        # The collector owns the verified snapshot; only its latest run may
        # cross the socket. Browser GET endpoints expose metadata, not URLs.
        remote = self.refresh_client.request("snapshot", run=data["run"])
        if (type(remote) is not dict or remote.get("run") != data["run"]
                or remote.get("fingerprint") != data["fingerprint"]
                or type(remote.get("verified_snapshot")) is not dict):
            raise ConsoleConflict("collector evidence changed; reload the preview")
        verified = remote["verified_snapshot"]
        template = intel.review_template(verified)
        if template["verification_sha256"] != data["fingerprint"]:
            raise ConsoleError("collector verification fingerprint mismatch")
        if any(entry["source"] != "openphish" for entry in verified["entries"]):
            raise ConsoleError("GUI import accepts only the official OpenPhish-to-GSB collection")
        from .evidence_store import adopt, EvidenceConflict
        try:
            outcome = adopt(self, verified, data["fingerprint"],
                            context_revision=data["context_revision"],
                            review_revision=data["review_revision"])
        except EvidenceConflict as exc:
            raise ConsoleConflict(str(exc)) from exc
        if outcome["imported"]:
            _audit(self.workspace / "audit.jsonl", "verified_intel_imported",
                   run=data["run"], fingerprint=data["fingerprint"][:16], reviews_reset=True)
        return {**outcome, "run": data["run"]}

    def capabilities(self):
        return {"mode": "local", "direct_refresh": self.refresh_client is not None,
                "evidence_upload": False, "signed_publication": False,
                "independent_signer": True}

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
        originals = {_identity(item): item for item in template["reviews"]}
        if len(originals) != len(template["reviews"]):
            raise ConsoleError("duplicate identities in verification template")
        seen = set()
        required = {"domain", "url_sha256", "checked_at", "reviewer", "reason",
                    "approved", "acknowledge_subtree"}
        for actual in reviewed["reviews"]:
            if type(actual) is not dict or set(actual) != required:
                raise ConsoleError("invalid or unbound review record; refuse policy generation")
            ref = _identity(actual)
            original = originals.get(ref)
            if (ref in seen or original is None or
                    any(actual[key] != original[key]
                        for key in ("domain", "url_sha256", "checked_at"))
                    or type(actual["approved"]) is not bool
                    or type(actual["acknowledge_subtree"]) is not bool):
                raise ConsoleError("duplicate or unbound review record; refuse policy generation")
            seen.add(ref)
        return verified, reviewed, template

    def reviews(self):
        verified, reviewed, template = self._verified_reviews()
        if verified is None:
            return {"missing": True, "fingerprint": None, "review_set_revision": None,
                    "verified_at": None, "items": []}
        by_ref = {(e["domain"], e["url_sha256"], e["checked_at"]): e
                  for e in intel._verification_entries(verified)}
        items = []
        now = datetime.now(timezone.utc)
        for review in reviewed["reviews"]:
            matched = by_ref[(review["domain"], review["url_sha256"], review["checked_at"])]
            fresh, eligible, code = _evidence_state(matched, now)
            items.append({**review, "id": _identity(review),
                          "revision": _revision(review),
                          "threat_types": matched["threat_types"],
                          "valid_until": matched["valid_until"],
                          "fresh": fresh, "eligible": eligible,
                          "eligibility_reason": code, "source": matched["source"],
                          "status": matched["status"]})
        return {"missing": False, "fingerprint": template["verification_sha256"],
                "review_set_revision": _revision(reviewed),
                "verified_at": verified["checked_at"], "items": items}

    def update_review(self, data: dict):
        if set(data) != {"id", "fingerprint", "revision", "approved",
                         "acknowledge_subtree", "reviewer", "reason"}:
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
            verified, reviews, template = self._verified_reviews()
            if reviews is None or template["verification_sha256"] != data["fingerprint"]:
                raise ConsoleError("stale evidence fingerprint; reload and review again")
            target = next((x for x in reviews["reviews"] if _identity(x) == data["id"]), None)
            if target is None:
                raise ConsoleError("review candidate no longer exists")
            if (not isinstance(data["revision"], str)
                    or not hmac.compare_digest(data["revision"], _revision(target))):
                raise ConsoleConflict("Review changed in another tab; reload before saving")
            if data["approved"]:
                by_ref = {(entry["domain"], entry["url_sha256"], entry["checked_at"]): entry
                          for entry in intel._verification_entries(verified)}
                matched = by_ref[(target["domain"], target["url_sha256"], target["checked_at"])]
                if not _evidence_state(matched, datetime.now(timezone.utc))[1]:
                    raise ConsoleError("stale or protected evidence cannot receive a new approval")
            target.update(reviewer=reviewer, reason=reason, approved=data["approved"],
                          acknowledge_subtree=data["acknowledge_subtree"] if data["approved"] else False)
            intel.write_json(self.workspace / "reviews.json", reviews)
            _audit(self.workspace / "audit.jsonl", "review_updated",
                   reference=data["id"][:16], approved=target["approved"])
        return {"saved": True}

    def reset_context(self) -> dict:
        """Read-only reset precondition, even if a stored review is from an older run."""
        verified = _json_read(self.workspace / "verified.json")
        template = intel.review_template(verified)
        try:
            existing = _json_read(self.workspace / "reviews.json")
        except FileNotFoundError:
            existing = template
        return {"fingerprint": template["verification_sha256"],
                "review_set_revision": _revision(existing),
                "out_of_sync": (existing.get("verification_sha256") !=
                                template["verification_sha256"])}

    def reset_reviews(self, data: dict):
        if (not isinstance(data, dict) or set(data) !=
                {"confirm", "fingerprint", "review_set_revision"} or
                data["confirm"] != "RESET_REVIEWS"):
            raise ConsoleError("explicit bound RESET_REVIEWS confirmation required")
        with self.locked():
            context = self.reset_context()
            if (data["fingerprint"] != context["fingerprint"] or
                    data["review_set_revision"] != context["review_set_revision"]):
                raise ConsoleConflict("Review set changed; reload before resetting")
            verified = _json_read(self.workspace / "verified.json")
            template = intel.review_template(verified)
            intel.write_json(self.workspace / "reviews.json", template)
            _audit(self.workspace / "audit.jsonl", "reviews_reset",
                   fingerprint=template["verification_sha256"][:16])
        return {"reset": True}

    def build(self, data: dict):
        required = {"fingerprint", "confirm_replacement", "acknowledge_user_notice"}
        if (set(data) not in (required, required | {"review_set_revision"})
                or data["confirm_replacement"] is not True
                or data["acknowledge_user_notice"] is not True):
            raise ConsoleError("full replacement and user-notice acknowledgement required")
        with self.locked():
            verified, reviews, template = self._verified_reviews()
            if verified is None or data["fingerprint"] != template["verification_sha256"]:
                raise ConsoleError("stale or missing verification evidence")
            if "review_set_revision" in data and data["review_set_revision"] != _revision(reviews):
                raise ConsoleConflict("Review approvals changed; reload before building")
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

    def draft_impact(self, name: str) -> dict:
        """Preview differences against a currently verified local signer feed.

        This only compares files and is never evidence of actual DNS application.
        """
        proposed = parse_policy(self.download(name))
        baseline = self.deployment(include_rules=True)
        result = {
            "draft": name, "draft_sha256": proposed.digest,
            "draft_expires_at": proposed.expires_at.isoformat(),
            "draft_rules": len(proposed.rules),
            "baseline_state": baseline["state"], "dns_applied": None,
            "comparison_available": baseline["state"] == "SIGNED_FILE_VERIFIED",
            "message": "Full replacement preview against a locally signed feed, not live DNS"
        }
        if not result["comparison_available"]:
            result["message"] = "No currently verified signed local feed; withdrawals cannot be assessed"
            return result
        instant = datetime.now(timezone.utc)
        before = {r["domain"]: intel.parse_time(r["expires_at"])
                  for r in baseline["rules"]
                  if r["decision"] == "BLOCK" and r["approved"]
                  and intel.parse_time(r["expires_at"]) > instant}
        after = {r.domain: r.expires_at for r in proposed.rules
                 if r.decision == "BLOCK" and r.approved and r.expires_at > instant}
        added = sorted(after.keys() - before.keys())
        withdrawn = sorted(before.keys() - after.keys())
        shortened = sorted(name for name in before.keys() & after.keys()
                           if after[name] < before[name])
        result.update(
            baseline_sequence=baseline["sequence"],
            baseline_sha256=baseline["policy_sha256"],
            added_count=len(added), withdrawn_count=len(withdrawn),
            shortened_count=len(shortened),
            added_sample=added[:20], withdrawn_sample=withdrawn[:20],
            shortened_sample=shortened[:20],
            requires_withdrawal_ack=bool(withdrawn or shortened))
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

    def deployment(self, *, include_rules=False, device=None, now=None):
        target = device_id(device) if device is not None else self.device
        if self.feed_root is None:
            return {"state": "NOT_CONFIGURED", "device": target, "dns_applied": None,
                    "message": "No publisher feed and trust directory configured"}
        instant = now or datetime.now(timezone.utc)
        try:
            raw = _regular_read(Path(self.feed_root) / target / "current.json",
                                2 * 1024 * 1024)
        except FileNotFoundError:
            return {"state": "NO_PUBLISHED_FILE", "device": target,
                    "dns_applied": None}
        except OSError:
            return {"state": "VERIFICATION_FAILED", "device": target,
                    "dns_applied": None, "message": "Publication could not be verified"}
        try:
            payload, parsed = verify_envelope(
                raw, expected_device=target, trust_dir=Path(self.trust_dir), now=instant)
            state = "SIGNED_FILE_VERIFIED"
            message = ("Signed local feed file verified; HTTPS delivery and "
                       "edge DNS apply not attested")
        except (ValueError, OSError):
            # A bad signature and an authentic but expired snapshot must not
            # look the same. allow_expired still rejects future dates and
            # invalid signatures, so only a genuinely signed past window
            # reaches PUBLICATION_EXPIRED.
            try:
                payload, parsed = verify_envelope(
                    raw, expected_device=target, trust_dir=Path(self.trust_dir),
                    now=instant, allow_expired=True)
            except (ValueError, OSError):
                return {"state": "VERIFICATION_FAILED", "device": target,
                        "dns_applied": None, "message": "Publication could not be verified"}
            if intel.parse_time(payload["valid_until"]) > instant:
                return {"state": "VERIFICATION_FAILED", "device": target,
                        "dns_applied": None, "message": "Publication could not be verified"}
            state = "PUBLICATION_EXPIRED"
            message = ("Signed publication is authentic but past valid_until; "
                       "it is not a current feed and DNS application is not attested")
        body = {"state": state, "device": target,
                "sequence": payload["sequence"], "key_id": json.loads(raw)["key_id"],
                "policy_sha256": parsed.digest, "rules": len(parsed.rules),
                "active_blocks": len(parsed.blocked(instant)),
                "expires_at": payload["valid_until"], "dns_applied": None,
                "message": message}
        if include_rules:
            body["rules"] = [{"domain": r.domain, "decision": r.decision,
                              "approved": r.approved, "scope": "SUBTREE",
                              "expires_at": r.expires_at.isoformat()}
                             for r in parsed.rules]
        return body

    def analytics(self):
        return self.nodes.analytics(lambda dev: self.deployment(device=dev))

    def node_states(self):
        return self.nodes.states(lambda dev: self.deployment(device=dev))

    def register_node(self, data):
        value = self.nodes.register(data)
        _audit(self.workspace / "audit.jsonl", "node_registered", device=value["device_id"])
        return value

    def unregister_node(self, data):
        value = self.nodes.unregister(data)
        _audit(self.workspace / "audit.jsonl", "node_unregistered", device=value["device_id"])
        return value

    def receive_node_report(self, raw):
        return self.nodes.receive(raw)

    def audit(self):
        """Bounded tail read, so a long-running console doesn't exceed its log reader."""
        path = self.workspace / "audit.jsonl"
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return []
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                    or st.st_mode & 0o077):
                raise ConsoleError("unsafe audit log")
            bound = 256 * 1024
            start = max(0, st.st_size - bound)
            os.lseek(fd, start, os.SEEK_SET)
            raw = os.read(fd, min(st.st_size, bound))
            if start:
                raw = raw.partition(b"\n")[2]
            return [json.loads(line) for line in raw.splitlines()[-100:]]
        finally:
            os.close(fd)

    def overview(self):
        """Isolate broken evidence, node registry, and draft storage from one another.

        Unavailable observations are null rather than deceptive zero counts.
        Publication remains a separate cryptographically verified file state.
        """
        evidence_error = False
        try:
            state = self.reviews()
        except (OSError, ValueError):
            evidence_error = True
            state = {"verified_at": None, "missing": False, "items": []}
        items = state["items"]
        active_expirations = [intel.parse_time(x["valid_until"]) for x in items if x["fresh"]]
        nodes_error = False
        try:
            nodes = self.node_states()
            node_summary = {
                "registered": len(nodes),
                "local_attested": sum(item["dns_applied"] is True for item in nodes),
                "dns_correlated": sum(item["state"] == "LOCAL_DNS_VERIFIED" for item in nodes),
                "needs_verification": sum(item["state"] != "LOCAL_DNS_VERIFIED" for item in nodes)
            }
        except (OSError, ValueError):
            nodes_error = True
            node_summary = {key: None for key in
                            ("registered", "local_attested", "dns_correlated",
                             "needs_verification")}
        drafts_error = False
        try:
            draft_count = len(self.drafts())
        except (OSError, ValueError):
            drafts_error = True
            draft_count = None
        return {"observed_at": datetime.now(timezone.utc).isoformat(),
                "verified_at": state["verified_at"], "evidence_missing": state["missing"],
                "evidence_error": evidence_error, "nodes_error": nodes_error,
                "drafts_error": drafts_error,
                "candidates": None if evidence_error else len(items),
                "approved": None if evidence_error else sum(x["approved"] for x in items),
                "fresh": None if evidence_error else sum(x["fresh"] for x in items),
                "eligible": None if evidence_error else sum(x["eligible"] for x in items),
                "approved_eligible": None if evidence_error else
                                    sum(x["approved"] and x["eligible"] for x in items),
                "next_expiry": (min(active_expirations).isoformat()
                                if active_expirations else None),
                "drafts": draft_count, "deployment": self.deployment(),
                "nodes": node_summary}


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Bound concurrent request handlers; reject excess connections immediately."""

    daemon_threads = True
    block_on_close = False

    def __init__(self, address, handler, *, max_handlers=32):
        if type(max_handlers) is not int or not 1 <= max_handlers <= 256:
            raise ValueError("invalid maximum handler count")
        self._slots = threading.BoundedSemaphore(max_handlers)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


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

        def setup(self):
            super().setup()
            # Prevent idle/partial localhost requests from occupying threads indefinitely.
            self.connection.settimeout(10)

        def log_message(self, *args):
            # Do not log operator-supplied domains or bearer tokens.
            pass

        def _headers(self, code, mime, length, *, filename=None):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.close_connection = True
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
            if (len(self.headers.get_all("Content-Length", [])) != 1
                    or self.headers.get("Transfer-Encoding") is not None):
                raise HttpError(400, "Ambiguous request framing")
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
                    if path == "/api/capabilities":
                        return self._json(200, service.capabilities())
                    if path == "/api/analytics":
                        return self._json(200, service.analytics())
                    if path == "/api/overview":
                        return self._json(200, service.overview())
                    if path == "/api/intel":
                        return self._json(200, service.intel_status())
                    if path == "/api/reviews":
                        return self._json(200, service.reviews())
                    if path == "/api/reviews/reset-context":
                        return self._json(200, service.reset_context())
                    if path == "/api/drafts":
                        return self._json(200, service.drafts())
                    if path == "/api/engine":
                        return self._json(200, service.engine_config())
                    if path == "/api/deployment":
                        return self._json(200, service.deployment(include_rules=True))
                    match = re.fullmatch(r"/api/deployment/([A-Za-z0-9][A-Za-z0-9_.-]{0,63})", path)
                    if match:
                        return self._json(200, service.deployment(include_rules=True, device=match[1]))
                    if path == "/api/nodes":
                        return self._json(200, service.node_states())
                    if path == "/api/audit":
                        return self._json(200, service.audit())
                    if path.startswith("/api/drafts/") and path.endswith("/impact"):
                        name = path[len("/api/drafts/"):-len("/impact")].strip("/")
                        return self._json(200, service.draft_impact(name))
                    if path.startswith("/api/drafts/") and path.endswith("/download"):
                        name = path[len("/api/drafts/"):-len("/download")].strip("/")
                        return self._send(200, service.download(name),
                                          "application/json; charset=utf-8", filename=name)
                else:
                    body = self._body()
                    if path == "/api/intel/refresh":
                        return self._json(202, service.start_intel_refresh(body))
                    if path == "/api/intel/import":
                        return self._json(200, service.adopt_intel(body))
                    if path == "/api/reviews/save":
                        return self._json(200, service.update_review(body))
                    if path == "/api/reviews/reset":
                        return self._json(200, service.reset_reviews(body))
                    if path == "/api/build":
                        if "review_set_revision" not in body:
                            raise ConsoleConflict("Reload the draft review summary before building")
                        return self._json(201, service.build(body))
                    if path == "/api/engine":
                        return self._json(200, service.configure_engine(body))
                    if path == "/api/evaluate":
                        return self._json(200, service.evaluate(body))
                    if path == "/api/nodes/register":
                        return self._json(201, service.register_node(body))
                    if path == "/api/nodes/unregister":
                        return self._json(200, service.unregister_node(body))
                raise HttpError(404, "Unknown API route")
            except HttpError as exc:
                self._json(exc.status, {"error": str(exc)})
            except (ConsoleConflict, NodeConflict) as exc:
                self._json(409, {"error": str(exc)})
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
            if self.path == "/v1/nodes/report":
                try:
                    if (len(self.headers.get_all("Host", [])) != 1
                            or self.headers.get("Host") != expected_host):
                        raise HttpError(400, "Invalid Host header")
                    if self.headers.get_all("Origin", []):
                        raise HttpError(403, "Browser origins are not accepted on node endpoint")
                    if self.headers.get("Authorization"):
                        raise HttpError(400, "Bearer tokens are not accepted on signed endpoint")
                    if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                        raise HttpError(415, "JSON content type required")
                    if (len(self.headers.get_all("Content-Length", [])) != 1
                            or self.headers.get("Transfer-Encoding") is not None):
                        raise HttpError(400, "Ambiguous request framing")
                    try:
                        length = int(self.headers["Content-Length"])
                    except (ValueError, TypeError):
                        raise HttpError(400, "Invalid content length") from None
                    if not 0 < length <= MAX_REPORT_BYTES:
                        raise HttpError(413, "Report size exceeded")
                    ack = service.receive_node_report(self.rfile.read(length))
                    return self._json(200, ack)
                except HttpError as exc:
                    return self._json(exc.status, {"error": str(exc)})
                except NodeConflict:
                    return self._json(409, {"error": "Out-of-order or conflicting report"})
                except (NodeError, ValueError, KeyError, TypeError):
                    # Do not reveal which devices or keys are installed.
                    return self._json(401, {"error": "Invalid signed device report"})
                except OSError:
                    return self._json(500, {"error": "Report storage unavailable"})
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
    parser.add_argument("--node-trust-dir", type=Path,
                        help="root-provisioned Ed25519 device public keys; separate from policy keys")
    parser.add_argument("--refresh-socket", type=Path,
                        default=Path(os.environ["ALEPH_INTEL_REFRESH_SOCKET"])
                        if os.environ.get("ALEPH_INTEL_REFRESH_SOCKET") else None,
                        help="operator-authorized Unix socket for non-root OpenPhish/GSB collector")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the console as a dedicated unprivileged reviewer, never root")
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024-65535")
    service = ConsoleService(args.workspace, args.token_file, feed_root=args.feed_root,
                             device=args.device_id, trust_dir=args.trust_dir,
                             node_trust_dir=args.node_trust_dir,
                             refresh_socket=args.refresh_socket)
    origin = args.origin or "http://127.0.0.1:" + str(args.port)
    server = BoundedThreadingHTTPServer(("127.0.0.1", args.port), handler_for(service, origin))
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
