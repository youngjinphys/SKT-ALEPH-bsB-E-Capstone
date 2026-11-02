"""Manual-only bridge between risk_scoring v1.0 and the existing v0.8 engine.

This file does NOT alter the project entry point, DNS daemon, threat feeds,
admin approvals, signing, publication, or any existing configuration. Nothing
imports this adapter automatically. It does not authenticate evidence sources.

Only a trusted, upstream evidence-verifying caller may use the resulting
proposal. In particular, arbitrary JSON saying status=MATCH, or naming an
allowlisted score source, is NOT proof that a security provider supplied it.
Do not attach this to production ingest without source verification and review.

Example in a controlled, offline test:

    from policy_server.risk_adapter import evaluate_risk_evidence
    preview = evaluate_risk_evidence(
        'example.test', config=trusted_config, score_source='lab-scanner',
        registration=verified_registration,
        observations=verified_observations,
    )
    # preview['policy_result']['action'] is a *proposal*, not a DNS response.

Risk scoring weights, 70-point boundary, score contracts, and the decision
engine remain owned by risk_scoring.py and engine.py respectively.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .engine import Snapshot, compile_policy, evaluate_policy
from .risk_scoring import WARN_THRESHOLD, score_domain


class RiskAdapterError(ValueError):
    """Trusted configuration or adapter prerequisites are inconsistent."""


def _time_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise RiskAdapterError("now must be a timezone-aware datetime")
    return now.astimezone(timezone.utc)


def _policy(config: Snapshot | dict[str, Any]) -> Snapshot:
    return config if isinstance(config, Snapshot) else compile_policy(config)


def evaluate_risk_evidence(
    domain: str,
    *,
    config: Snapshot | dict[str, Any],
    score_source: str,
    registration: dict | None = None,
    observations: dict[str, dict] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute and map a non-enforcing risk proposal, without touching DNS.

    Inputs `registration` and `observations` MUST ALREADY be checked by a
    trusted upstream for provenance, authorization, domain scope, canonical
    incident identities, feed freshness, and DNS origin. The scorer validates
    their *shape*, not their real-world authenticity. `score_source` identifies
    the caller's approved scorer and does not constitute authentication.

    - A config threshold mismatch fails closed rather than silently changing
      the meaning of WARN_CANDIDATE/LOW_CANDIDATE.
    - A missing or incomplete low-risk check never turns into ALLOW: an explicit
      `analysis: None` makes the original engine respond UNKNOWN.
    - Existing admin/approved BLOCK is left to the original engine; it wins
      even when no risk evidence is available. Risk scoring is skipped then.
    - No DNS policy, signature, disk file or automatic deployment is produced.

    Returns: `scoring`, `engine_data`, `policy_result`, `mode`.
    The `engine_data` field is shaped for existing evaluate_policy(data=...),
    but is NOT self-authenticating. Do NOT trust it from untrusted callers.
    """
    instant = _time_now(now)
    policy = _policy(config)
    if policy.threshold != WARN_THRESHOLD:
        raise RiskAdapterError(
            "warning threshold mismatch: risk scoring and policy engine must agree"
        )
    if type(score_source) is not str or score_source not in policy.score_sources:
        raise RiskAdapterError("score_source is not in the trusted policy allowlist")

    # Respect the original engine's existing explicit BLOCK priority. We do
    # not need a risky external score calculation for an already approved block.
    block = evaluate_policy(domain, data={"analysis": None}, config=policy, now=instant)
    if block["action"] == "BLOCK":
        return {
            "scoring": None,
            "engine_data": None,
            "policy_result": block,
            "mode": "MANUAL_PREVIEW_ONLY",
        }

    scoring = score_domain(
        domain, registration=registration, observations=observations, now=instant
    )
    if scoring["threshold"] != policy.threshold:
        raise RiskAdapterError("risk scoring result threshold mismatch")

    # The existing engine accepts EXACTLY these six analysis properties.
    # Missing evidence must force UNKNOWN, never a fabricated low score.
    if scoring["decision"] == "UNKNOWN":
        data: dict[str, Any] = {"analysis": None}
    else:
        if scoring["decision"] not in ("WARN_CANDIDATE", "LOW_CANDIDATE"):
            raise RiskAdapterError("unexpected risk scoring decision")
        if scoring["risk_score"] is None or scoring["expires_at"] is None:
            raise RiskAdapterError("incomplete risk score cannot be adapted")
        data = {"analysis": {
            "domain": scoring["domain"],
            "risk_score": scoring["risk_score"],
            "source": score_source,
            "model_version": scoring["model_version"],
            "checked_at": scoring["checked_at"],
            "expires_at": scoring["expires_at"],
        }}

    proposal = evaluate_policy(domain, data=data, config=policy, now=instant)
    if scoring["decision"] == "UNKNOWN":
        if proposal["action"] != "UNKNOWN":
            raise RiskAdapterError("incomplete scoring was not rejected")
    else:
        expected = "WARN" if scoring["decision"] == "WARN_CANDIDATE" else "ALLOW"
        if proposal["action"] != expected:
            raise RiskAdapterError("risk score was rejected by the original policy engine")

    return {
        "scoring": scoring,
        "engine_data": data,
        "policy_result": proposal,
        "mode": "MANUAL_PREVIEW_ONLY",
    }
