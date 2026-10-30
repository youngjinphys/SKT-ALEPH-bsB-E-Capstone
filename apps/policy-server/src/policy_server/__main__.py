"""Remote-only policy production; no suspect-site visits or automatic approval."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import sys
import tempfile

from . import intel


def _secret(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_mode & 0o077 or st.st_size > 1024):
            raise ValueError("API key file requires owner-only 0600 permissions")
        data = os.read(fd, 1025)
        if not 1 <= len(data) <= 1024:
            raise ValueError("API key file invalid")
        key = data.decode("ascii").strip()
        if not key or any(ord(char) <= 32 or ord(char) >= 127 for char in key):
            raise ValueError("API key file invalid")
        return key
    finally:
        os.close(fd)


def _private_dir(path: Path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError("pre-created private state directory required")
    st = path.stat()
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise ValueError("state directory must be owned by caller and 0700")


@contextmanager
def _refresh_lock(state_dir: Path):
    """Reject simultaneous manual/timer runs before sending duplicate API calls."""
    fd = os.open(state_dir / '.refresh.lock',
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
            raise ValueError('unsafe dataset refresh lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('dataset refresh already running') from None
        yield
    finally:
        os.close(fd)


def refresh(*, state_dir: Path, api_key_file: Path, source: str,
            accept_terms: bool, ack_disclosure: bool, ack_noncommercial: bool,
            limit=100, feed_file=None, fetch=None, now=None):
    """One serialized, all-or-nothing private dataset generation, never a policy."""
    if os.geteuid() == 0:
        raise ValueError("feed collection must run as a dedicated non-root account")
    intel.validate_limit(limit)
    if not (ack_disclosure is True and ack_noncommercial is True):
        raise ValueError("Google URL disclosure and non-commercial use must be acknowledged")
    if source == "openphish":
        if accept_terms is not True or feed_file is not None:
            raise ValueError("OpenPhish terms acknowledgement required")
    elif source != "local-openphish" or feed_file is None:
        raise ValueError("only an explicit local OpenPhish fixture is supported here")
    _private_dir(state_dir)
    with _refresh_lock(state_dir):
        key = _secret(api_key_file)
        remote = intel.get_https if fetch is None else fetch
        fetched = (remote(intel.OPENPHISH) if source == 'openphish'
                   else intel.read_file(feed_file, intel.MAX_FEED_BYTES))
        instant = intel.as_utc(now or datetime.now(timezone.utc))
        collected = intel.collect_urls(fetched, source=source, fetched_at=instant, limit=limit)
        verified = intel.verify_collected(collected, key, checked_at=instant, fetch=remote)
        template = intel.review_template(verified)
        runs = state_dir / "runs"
        runs.mkdir(mode=0o700, exist_ok=True)
        _private_dir(runs)
        staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=runs))
        try:
            intel.write_json(staging / "collected.json", collected)
            intel.write_json(staging / "verified.json", verified)
            intel.write_json(staging / "review-template.json", template)
            name = instant.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(5)
            destination = runs / name
            os.rename(staging, destination)
            dir_fd = os.open(runs, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            summary = {"run": name, "verified": len(verified["entries"]),
                       "review_proposals": len(template["reviews"])}
            intel.write_json(state_dir / "latest.json", summary)
            return {"run_dir": str(destination), "verified": summary["verified"],
                    "review_proposals": summary["review_proposals"]}
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate", help="non-enforcing exact-QNAME score proposal")
    evaluate.add_argument("domain")
    evaluate.add_argument("--config", type=Path, required=True)
    evaluate.add_argument("--data", type=Path)
    evaluate.add_argument("--analysis-path", help="optional nested mapping, e.g. payload.scan")
    refresh_cmd = sub.add_parser("refresh", help="OpenPhish -> GSB v5 -> private dataset")
    refresh_cmd.add_argument("--state-dir", type=Path, required=True)
    refresh_cmd.add_argument("--api-key-file", type=Path, required=True)
    refresh_cmd.add_argument("--source", choices=("openphish", "local-openphish"), default="openphish")
    refresh_cmd.add_argument("--feed-file", type=Path)
    refresh_cmd.add_argument("--limit", type=int, default=100)
    refresh_cmd.add_argument("--accept-openphish-terms", action="store_true")
    refresh_cmd.add_argument("--ack-url-disclosure", action="store_true")
    refresh_cmd.add_argument("--ack-noncommercial-use", action="store_true")
    build = sub.add_parser("build", help="human-reviewed GSB evidence -> DNS full snapshot")
    build.add_argument("--verified", type=Path, required=True)
    build.add_argument("--reviews", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--confirm-replacement", action="store_true")
    build.add_argument("--acknowledge-user-notice", action="store_true")
    release = sub.add_parser("promote", help="signature-verified root-only HTTPS feed promotion")
    release.add_argument("--release", type=Path, required=True)
    release.add_argument("--feed-root", type=Path, default=Path("/srv/aleph-policy-feed"))
    release.add_argument("--trust-dir", type=Path, default=Path("/etc/aleph-policy-sync/trust"))
    release.add_argument("--device-id", required=True)
    release.add_argument("--apply", action="store_true")
    release.add_argument("--ack-withdrawals", action="store_true")
    release.add_argument("--ack-key-rotation", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            from .engine import compile_policy, evaluate_policy
            from .data_adapter import adapt_data
            snapshot = compile_policy(intel.read_json(args.config))
            raw = intel.read_json(args.data) if args.data else {}
            data = adapt_data(raw, {"analysis": args.analysis_path} if args.analysis_path else None)
            value = evaluate_policy(args.domain, data=data, config=snapshot)
        elif args.command == "refresh":
            value = refresh(state_dir=args.state_dir, api_key_file=args.api_key_file,
                            source=args.source, feed_file=args.feed_file, limit=args.limit,
                            accept_terms=args.accept_openphish_terms,
                            ack_disclosure=args.ack_url_disclosure,
                            ack_noncommercial=args.ack_noncommercial_use)
        elif args.command == "build":
            from dns_agent.policy import parse_policy
            if not (args.confirm_replacement and args.acknowledge_user_notice):
                raise ValueError("explicit replacement and user-notice acknowledgements required")
            reviewed = intel.build_policy(intel.read_json(args.verified), intel.read_json(args.reviews),
                                          acknowledge_replacement=True, acknowledge_notice=True)
            parse_policy(json.dumps(reviewed).encode())
            intel.write_json(args.output, reviewed)
            value = {"output": str(args.output), "rules": len(reviewed["rules"]), "published": False}
        else:
            from .promote import promote
            value = promote(release=args.release, feed_root=args.feed_root,
                            trusted_keys=args.trust_dir, device=args.device_id,
                            apply=args.apply, acknowledge_withdrawals=args.ack_withdrawals,
                            acknowledge_key_rotation=args.ack_key_rotation)
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print("POLICY_SERVER_ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
