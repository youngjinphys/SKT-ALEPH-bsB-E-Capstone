"""ALEPH signed policy distribution: sign, fetch and apply are separate roles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from .snapshot import (SnapshotError, _regular_read, canonical, device_id,
                       load_private_key, load_public_key, public_key_id,
                       sign_policy, strict_load, verify_envelope)
from .sync import SyncError, apply_once, atomic_private, fetch_once


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    signer = sub.add_parser("sign", help="sign an already approved policy; never publish")
    signer.add_argument("--policy", type=Path, required=True)
    signer.add_argument("--private-key", type=Path, required=True)
    signer.add_argument("--device-id", required=True)
    signer.add_argument("--sequence", type=int, required=True)
    signer.add_argument("--output", type=Path, required=True)
    signer.add_argument("--confirm-replacement", action="store_true")
    signer.add_argument("--confirm-empty", action="store_true")

    identify = sub.add_parser("key-id", help="show trust filename for an Ed25519 public key")
    identify.add_argument("--public-key", type=Path, required=True)

    check = sub.add_parser("verify", help="read-only signature and policy verification")
    check.add_argument("--snapshot", type=Path, required=True)
    check.add_argument("--device-id", required=True)
    check.add_argument("--trust-dir", type=Path, required=True)

    fetch = sub.add_parser("fetch", help="non-root HTTPS downloader (no DNS changes)")
    fetch.add_argument("--url", required=True)
    fetch.add_argument("--device-id", required=True)
    fetch.add_argument("--trust-dir", type=Path, required=True)
    fetch.add_argument("--inbox-dir", type=Path, required=True)
    fetch.add_argument("--ca-file", type=Path)
    fetch.add_argument("--token-file", type=Path)

    apply = sub.add_parser("apply", help="root signature verifier and ALEPH publisher (no networking)")
    apply.add_argument("--device-id", required=True)
    apply.add_argument("--trust-dir", type=Path, required=True)
    apply.add_argument("--inbox-dir", type=Path, required=True)
    apply.add_argument("--fetch-user", required=True)
    apply.add_argument("--state-dir", type=Path, required=True)
    apply.add_argument("--dns-admin", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "key-id":
            print(public_key_id(load_public_key(args.public_key)))
        elif args.command == "sign":
            if os.geteuid() == 0:
                raise SnapshotError("sign as an ordinary offline key custodian, not root")
            if not args.confirm_replacement:
                raise SnapshotError("signing a full policy replacement requires --confirm-replacement")
            policy = _regular_read(args.policy, 1024 * 1024, owner=os.geteuid())
            key = load_private_key(args.private_key)
            result = sign_policy(policy, key, target=args.device_id,
                                 sequence=args.sequence, confirm_empty=args.confirm_empty)
            if args.output.is_symlink() or args.output.exists():
                raise SnapshotError("refusing to replace an existing signed release")
            atomic_private(args.output, canonical(result) + b"\n", owner=os.geteuid())
            print(json.dumps({"result":"signed", "device":device_id(args.device_id),
                              "sequence":args.sequence, "key_id":result["key_id"]}))
        elif args.command == "verify":
            envelope = _regular_read(args.snapshot, 2 * 1024 * 1024)
            payload, policy = verify_envelope(envelope, expected_device=args.device_id,
                                              trust_dir=args.trust_dir)
            print(json.dumps({"verified":True,"device":payload["device_id"],
                              "sequence":payload["sequence"],"policy_sha256":policy.digest,
                              "rules":len(policy.rules),"expires_at":payload["valid_until"]}))
        elif args.command == "fetch":
            outcome = fetch_once(url=args.url, device=args.device_id,
                                 trust_dir=args.trust_dir, inbox_dir=args.inbox_dir,
                                 ca_file=args.ca_file, token_file=args.token_file)
            print(json.dumps({"fetch":outcome}))
        elif args.command == "apply":
            outcome = apply_once(device=args.device_id, trust_dir=args.trust_dir,
                                 inbox_dir=args.inbox_dir, fetch_user=args.fetch_user,
                                 state_dir=args.state_dir, dns_admin=args.dns_admin)
            print(json.dumps({"apply":outcome}))
        return 0
    except (SnapshotError, SyncError, OSError, ValueError, KeyError) as exc:
        # Do not print URLs, bearer tokens or policy body in logs.
        print("POLICY_SYNC_ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
