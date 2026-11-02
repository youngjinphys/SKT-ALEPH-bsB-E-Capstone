"""Manual, local-only command for previewing the eight-rule risk proposal.

This is deliberately a separate entry point. The normal policy_server CLI,
DNS daemon, OpenPhish/Google ingestion, approval, signing, and publishing code
never imports this module. No network requests or policy writes occur.

Evidence files are NOT authenticated by this command. A JSON field that says
MATCH does not prove a real-world incident. The output is a diagnostic policy
proposal, never a DNS warning, active BLOCK rule, or authorization to publish.

Run from the repository root with the policy-server and dns-agent source roots
on PYTHONPATH:

    python -m policy_server.risk_cli --domain example.test \
        --config apps/policy-server/src/policy_server/proposal-example.json \
        --demo

Manual preview from a local evidence JSON object:

    python -m policy_server.risk_cli --domain example.test \
        --config apps/policy-server/src/policy_server/proposal-example.json \
        --score-source lab-scanner --evidence-file evidence.json --json

Evidence schema (the scorer validates the internal shapes separately):
    {"registration": null, "observations": {"R7": { ... }}}
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from .engine import ProposalError
from .risk_adapter import RiskAdapterError, evaluate_risk_evidence
from .risk_scoring import RiskInputError

_CONFIG_MAX_BYTES = 4 * 1024 * 1024
_EVIDENCE_MAX_BYTES = 256 * 1024


class RiskCliError(ValueError):
    """Unsafe or unsupported manual-preview input."""


def _pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise RiskCliError("JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise RiskCliError("JSON contains a non-finite value")


def _read_json(path: Path, *, limit: int) -> dict:
    # Keep this manual preview from accidentally reading large provider feeds or
    # following an obvious symlink. This is NOT an OS-level trust boundary.
    if path.is_symlink():
        raise RiskCliError("symlink input is not supported by the manual preview")
    if not path.is_file():
        raise RiskCliError("input must be a regular file")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise RiskCliError("input JSON exceeds the permitted size")
    try:
        loaded = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_pairs_unique,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RiskCliError("input is not valid UTF-8 JSON") from exc
    if type(loaded) is not dict:
        raise RiskCliError("input JSON must be an object")
    return loaded


def _demo_evidence(domain: str, now: datetime) -> dict:
    # Completely synthetic R7 evidence; ONLY allowed for .test hostnames.
    if not isinstance(domain, str) or not domain.lower().endswith(".test"):
        raise RiskCliError("--demo can only use a .test hostname")
    event = {
        "status": "MATCH",
        "domain": domain,
        "scope": "EXACT",
        "source_id": "lab-fixture",
        "origin_id": "synthetic-demo-incident-001",
        "observed_at": now.isoformat(),
        "valid_until": (now + timedelta(minutes=5)).isoformat(),
        "event_at": (now - timedelta(days=1)).isoformat(),
    }
    return {"registration": None, "observations": {"R7": event}}


def _input_evidence(raw: dict) -> dict:
    if set(raw) != {"registration", "observations"}:
        raise RiskCliError("evidence requires exactly registration and observations")
    return raw


def _summary(result: dict, *, demo: bool) -> dict:
    proposal = result["policy_result"]
    scoring = result["scoring"]
    return {
        "mode": "MANUAL_PREVIEW_ONLY",
        "evidence_kind": "SYNTHETIC_DEMO" if demo else "USER_SUPPLIED_UNAUTHENTICATED",
        "domain": proposal["domain"],
        "risk_score": scoring["risk_score"] if scoring is not None else None,
        "score_floor": scoring["score_floor"] if scoring is not None else None,
        "counted_rules": scoring["counted_rules"] if scoring is not None else [],
        "unknown_inputs": scoring["unknown_inputs"] if scoring is not None else [],
        "proposal_action": proposal["action"],
        "reason_code": proposal["reason_code"],
        "dns_applied": False,
        "published": False,
        "source_authenticated": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-only risk score preview; never applies DNS policy")
    parser.add_argument("--domain", required=True, help="exact hostname to evaluate")
    parser.add_argument("--config", required=True, type=Path, help="trusted local proposal config JSON")
    parser.add_argument("--score-source", default="lab-scanner", help="source ID allowlisted in config (not authentication)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="synthetic R7 claim for .test domain only")
    group.add_argument("--evidence-file", type=Path, help="local JSON containing registration and observations")
    parser.add_argument("--json", action="store_true", help="machine-readable preview output")
    args = parser.parse_args(argv)

    try:
        config = _read_json(args.config, limit=_CONFIG_MAX_BYTES)
        now = datetime.now(timezone.utc)
        evidence = (_demo_evidence(args.domain, now) if args.demo else
                    _input_evidence(_read_json(args.evidence_file, limit=_EVIDENCE_MAX_BYTES)))
        result = evaluate_risk_evidence(
            args.domain,
            config=config,
            score_source=args.score_source,
            registration=evidence["registration"],
            observations=evidence["observations"],
            now=now,
        )
        summary = _summary(result, demo=args.demo)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        else:
            print(f"위험도: {summary['risk_score'] if summary['risk_score'] is not None else '미확정'}")
            print(f"정책 제안: {summary['proposal_action']} ({summary['reason_code']})")
            print(f"적용된 지표: {', '.join(summary['counted_rules']) or '없음'}")
            print(f"입력 유형: {summary['evidence_kind']}")
            print("실행 모드: MANUAL_PREVIEW_ONLY (DNS 변경·정책 발행 없음)")
            print("주의: 입력 근거의 실제 출처는 이 명령에서 인증하지 않습니다.")
        return 0
    except (OSError, ValueError) as exc:
        # Avoid echoing raw evidence, API tokens, or file contents in errors.
        msg = str(exc)
        if not isinstance(exc, (RiskCliError, RiskInputError, RiskAdapterError, ProposalError)):
            msg = "manual-preview input could not be processed"
        print(f"RISK_PREVIEW_ERROR: {msg}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
