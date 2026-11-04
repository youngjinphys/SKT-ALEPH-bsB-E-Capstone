"""Privilege-separated on-demand threat intelligence refresh over a local Unix socket.

Only the data collector owns the GSB credential and raw OpenPhish feed. The
operator console may request one fixed refresh and obtain a verified snapshot
through an authenticated local IPC channel; it cannot choose URLs or commands.
No request approves DNS rules, signs policies, or publishes a release.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import struct
import threading

from aleph_policy_sync.snapshot import _regular_read, strict_load
from . import intel

MAX_REQUEST = 2048
MAX_RESPONSE = intel.MAX_ARTIFACT_BYTES + 4096
RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{10}\Z")
COOLDOWN = timedelta(minutes=5)


class BridgeError(ValueError):
    """The local collector boundary rejected an operation."""


def _read_private(path, limit=intel.MAX_ARTIFACT_BYTES):
    raw = _regular_read(Path(path), limit, forbidden=0o077, owner=os.geteuid())
    return intel.parse_json(raw)


def _utc():
    return datetime.now(timezone.utc)


class RefreshClient:
    """The sole operation console capability; no arbitrary HTTP requests."""
    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.is_absolute() or ".." in self.path.parts:
            raise BridgeError("refresh socket must be an absolute fixed path")

    def request(self, action, **fields):
        if action not in ("status", "start", "snapshot"):
            raise BridgeError("unsupported collector request")
        if fields and (action != "snapshot" or set(fields) != {"run"}):
            raise BridgeError("unsupported collector options")
        if action == "snapshot" and (not isinstance(fields["run"], str)
                                    or not RUN_ID.fullmatch(fields["run"])):
            raise BridgeError("invalid collection run identifier")
        payload = json.dumps({"action": action, **fields}, sort_keys=True).encode()
        if len(payload) > MAX_REQUEST:
            raise BridgeError("collector request too large")
        try:
            info = self.path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_mode & 0o007:
                raise BridgeError("collector socket has unsafe permissions")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
                channel.settimeout(8)
                channel.connect(str(self.path))
                channel.sendall(payload)
                channel.shutdown(socket.SHUT_WR)
                chunks, total = [], 0
                while True:
                    chunk = channel.recv(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_RESPONSE:
                        raise BridgeError("collector response too large")
                    chunks.append(chunk)
        except (OSError, TimeoutError) as exc:
            raise BridgeError("collector is unavailable; check its systemd socket/service") from exc
        try:
            reply = strict_load(b"".join(chunks), limit=MAX_RESPONSE)
        except (OSError, ValueError) as exc:
            raise BridgeError("collector returned invalid bounded JSON") from exc
        if type(reply) is not dict:
            raise BridgeError("invalid collector response")
        if "error" in reply:
            raise BridgeError(str(reply["error"])[:120])
        return reply


class RefreshServer:
    """Runs as aleph-policy-server; socket peer credentials pin its GUI caller."""
    def __init__(self, state_dir: Path, api_key: Path, console_uid: int, *, refresher=None):
        from .__main__ import _private_dir, refresh
        self.state_dir = Path(state_dir)
        _private_dir(self.state_dir)
        self.api_key = Path(api_key)
        if type(console_uid) is not int or console_uid <= 0:
            raise BridgeError("console peer must be a dedicated non-root account")
        self.console_uid = console_uid
        self.refresher = refresher or refresh
        self.lock = threading.RLock()
        self.running = False
        self.status_file = self.state_dir / "gui-refresh-state.json"
        self.state = self._load_state()

    def _load_state(self):
        try:
            data = _read_private(self.status_file, 4096)
        except FileNotFoundError:
            data = {"state": "IDLE", "requested_at": None,
                    "completed_at": None, "error_code": None}
        if (type(data) is not dict or set(data) !=
                {"state", "requested_at", "completed_at", "error_code"}
                or data["state"] not in ("IDLE", "RUNNING", "SUCCESS", "ERROR", "INTERRUPTED")
                or any(data[x] is not None and not isinstance(data[x], str) for x in
                       ("requested_at", "completed_at", "error_code"))):
            raise BridgeError("collector status file is invalid; inspect private state")
        for field in ("requested_at", "completed_at"):
            if data[field] is not None:
                intel.parse_time(data[field])
        if data["state"] == "RUNNING":
            data["state"] = "INTERRUPTED"
            data["error_code"] = "COLLECTOR_RESTARTED"
            self._save_state(data)
        return data

    def _save_state(self, state):
        intel.write_json(self.status_file, state)

    def _latest(self, *, with_snapshot=False):
        try:
            summary = _read_private(self.state_dir / "latest.json", 4096)
        except FileNotFoundError:
            return None
        if (type(summary) is not dict or set(summary) !=
                {"run", "verified", "review_proposals"}
                or not isinstance(summary["run"], str)
                or not RUN_ID.fullmatch(summary["run"])
                or any(type(summary[k]) is not int or not 0 <= summary[k] <= intel.MAX_URLS
                        for k in ("verified", "review_proposals"))):
            raise BridgeError("collector latest record is invalid")
        runs = self.state_dir / "runs"
        from .__main__ import _private_dir
        _private_dir(runs)
        folder = runs / summary["run"]
        _private_dir(folder)
        verified = _read_private(folder / "verified.json")
        template = intel.review_template(verified)
        if (len(verified["entries"]) != summary["verified"]
                or len(template["reviews"]) != summary["review_proposals"]):
            raise BridgeError("collector record is inconsistent")
        result = {"run": summary["run"], "checked_at": verified["checked_at"],
                  "verified": summary["verified"],
                  "review_proposals": summary["review_proposals"],
                  "unassigned_expressions": verified["unassigned_expressions"],
                  "fingerprint": template["verification_sha256"]}
        if with_snapshot:
            result["verified_snapshot"] = verified
        return result

    def status(self):
        with self.lock:
            state = {**self.state}
        result = {**state, "latest": None, "cooldown_seconds": 0}
        try:
            result["latest"] = self._latest()
        except (OSError, ValueError):
            result["latest_error"] = "LATEST_RECORD_INVALID"
        if state["requested_at"]:
            delay = COOLDOWN - (_utc() - intel.parse_time(state["requested_at"]))
            result["cooldown_seconds"] = max(0, int(delay.total_seconds()) + (1 if delay.microseconds else 0))
        if self.running:
            result["state"] = "RUNNING"
        return result

    def _run(self):
        try:
            self.refresher(
                state_dir=self.state_dir, api_key_file=self.api_key,
                source="openphish", accept_terms=True,
                ack_disclosure=True, ack_noncommercial=True, limit=100)
            result = "SUCCESS"
            code = None
        except Exception:
            # No provider URLs, request headers or API credentials in status.
            result = "ERROR"
            code = "COLLECTION_FAILED"
        with self.lock:
            self.state = {**self.state, "state": result,
                          "completed_at": intel.iso(_utc()), "error_code": code}
            try:
                self._save_state(self.state)
            finally:
                # A failed status write must not pin the in-memory RUNNING flag.
                self.running = False

    def start(self):
        with self.lock:
            if self.running:
                return {"state": "RUNNING", "accepted": False}
            now = _utc()
            if self.state["requested_at"]:
                remaining = COOLDOWN - (now - intel.parse_time(self.state["requested_at"]))
                if remaining > timedelta(0):
                    return {"state": "COOLDOWN", "accepted": False,
                            "retry_after_seconds": max(1, int(remaining.total_seconds()) + 1)}
            self.state = {**self.state, "state": "RUNNING",
                          "requested_at": intel.iso(now), "completed_at": None,
                          "error_code": None}
            self._save_state(self.state)
            self.running = True
            worker = threading.Thread(target=self._run, name="aleph-intel-refresh", daemon=True)
            try:
                worker.start()
            except RuntimeError:
                self.running = False
                self.state = {**self.state, "state": "ERROR", "error_code": "WORKER_UNAVAILABLE"}
                self._save_state(self.state)
                raise BridgeError("collector worker could not start") from None
        return {"state": "RUNNING", "accepted": True}

    def handle(self, data: bytes, *, peer_uid: int):
        if peer_uid != self.console_uid:
            raise BridgeError("unauthorized local collector peer")
        if len(data) > MAX_REQUEST:
            raise BridgeError("collector request exceeds limit")
        obj = intel.parse_json(data)
        if type(obj) is not dict or not isinstance(obj.get("action"), str):
            raise BridgeError("invalid collector command")
        action = obj["action"]
        if action in ("start", "status") and set(obj) == {"action"}:
            return self.start() if action == "start" else self.status()
        if action == "snapshot" and set(obj) == {"action", "run"}:
            if type(obj["run"]) is not str or not RUN_ID.fullmatch(obj["run"]):
                raise BridgeError("invalid requested run")
            snapshot = self._latest(with_snapshot=True)
            if snapshot is None or snapshot["run"] != obj["run"]:
                raise BridgeError("requested run is not current; refresh the preview")
            return snapshot
        raise BridgeError("unsupported collector command")


def serve(server: RefreshServer, listener: socket.socket):
    if listener.family != socket.AF_UNIX or listener.type & socket.SOCK_STREAM != socket.SOCK_STREAM:
        raise BridgeError("systemd must pass a Unix stream socket")
    while True:
        conn, _ = listener.accept()
        with conn:
            conn.settimeout(5)
            try:
                uid = struct.unpack("3i", conn.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[1]
                raw = bytearray()
                while True:
                    piece = conn.recv(min(1024, MAX_REQUEST + 1 - len(raw)))
                    if not piece:
                        break
                    raw.extend(piece)
                    if len(raw) > MAX_REQUEST:
                        raise BridgeError("collector request exceeds limit")
                answer = server.handle(bytes(raw), peer_uid=uid)
            except (OSError, ValueError, KeyError, TypeError):
                answer = {"error": "collector request rejected"}
            response = json.dumps(answer, sort_keys=True, separators=(",", ":")).encode()
            if len(response) > MAX_RESPONSE:
                response = b'{"error":"collector response exceeds limit"}'
            try:
                conn.sendall(response)
            except OSError:
                # A closed client does not invalidate the worker or next request.
                continue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("serve",))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--console-user", default="aleph-ops-console")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("collector must not run as root")
    if os.environ.get("LISTEN_FDS") != "1" or os.environ.get("LISTEN_PID") != str(os.getpid()):
        parser.error("use the dedicated systemd Unix socket; direct port binding prohibited")
    try:
        user = pwd.getpwnam(args.console_user)
        server = RefreshServer(args.state_dir, args.api_key_file, user.pw_uid)
        listener = socket.socket(fileno=3)
        serve(server, listener)
    except (ValueError, OSError, KeyError) as exc:
        parser.error("collector bridge failed; inspect private service logs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
