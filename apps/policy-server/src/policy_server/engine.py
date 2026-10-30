"""Hardened v0.8 proposal engine, adapted from the team's attached ZIP.

This is a remote *decision proposal* for one exact QNAME, not an ALEPH DNS
policy. The DNS SUBTREE contract is intentionally NOT emitted by this module.
Threat-feed matches are not numeric risk scores, and no score can self-approve
or bypass the existing reviewed/Ed25519-signed publishing workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re

from dns_agent.policy import PolicyError, domain_name, timestamp

_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SOURCE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_REQUIRED = frozenset({"policy_version", "warn_threshold", "admin_blocked_domains",
                       "approved_malicious_domains", "official_domains", "score_sources"})
_MAX_NAMES = 10000


class ProposalError(ValueError):
    """An untrusted or inconsistent proposal input was rejected."""


@dataclass(frozen=True)
class Snapshot:
    version: str
    threshold: float
    admin_blocked: frozenset[str]
    approved_malicious: frozenset[str]
    official: frozenset[str]
    score_sources: frozenset[str]


def _names(raw: object, field: str) -> frozenset[str]:
    if not isinstance(raw, list) or len(raw) > _MAX_NAMES:
        raise ProposalError(f"{field}: expected a bounded array")
    names: set[str] = set()
    for item in raw:
        try:
            name = domain_name(item)  # same strict ASCII contract as the DNS agent
        except PolicyError as exc:
            raise ProposalError(f"{field}: invalid domain") from exc
        if name in names:
            raise ProposalError(f"{field}: duplicate canonical name")
        names.add(name)
    return frozenset(names)


def compile_policy(config: object) -> Snapshot:
    if type(config) is not dict or set(config) != _REQUIRED:
        raise ProposalError("complete trusted policy configuration required; no unknown keys")
    version = config["policy_version"]
    threshold = config["warn_threshold"]
    sources = config["score_sources"]
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ProposalError("invalid policy_version")
    if type(threshold) not in (float, int) or not 0 <= threshold <= 100 or not math.isfinite(threshold):
        raise ProposalError("warn_threshold must be a finite number in [0,100]")
    if not isinstance(sources, list) or len(sources) > 32 or any(
        not isinstance(s, str) or not _SOURCE.fullmatch(s) for s in sources
    ) or len(set(sources)) != len(sources):
        raise ProposalError("score_sources must be a unique bounded source allowlist")
    admin = _names(config["admin_blocked_domains"], "admin_blocked_domains")
    malicious = _names(config["approved_malicious_domains"], "approved_malicious_domains")
    official = _names(config["official_domains"], "official_domains")
    if official & (admin | malicious):
        raise ProposalError("official and blocked domain lists conflict")
    return Snapshot(version, float(threshold), admin, malicious, official, frozenset(sources))


def _result(name: str, version: str, action: str, reason: str, *, score=None,
            source=None, checked_at=None, expires_at=None):
    return {"domain": name, "scope": "EXACT", "action": action,
            "reason_code": reason, "risk_score": score, "score_source": source,
            "checked_at": checked_at, "expires_at": expires_at,
            "policy_version": version}


def evaluate_policy(domain: object, *, data: object = None, config: Snapshot | object = None,
                    now: datetime | None = None) -> dict:
    """Return a non-enforcing exact-name proposal and explicit UNKNOWN reasons.

    Scores require trusted producer identity and bounded observation freshness;
    even a valid LOW score is only an ALLOW *proposal*, not a safety claim.
    """
    version = config.version if isinstance(config, Snapshot) else "unverified"
    if not isinstance(domain, str):
        return _result("<invalid-domain>", version, "UNKNOWN", "INVALID_DOMAIN")
    try:
        name = domain_name(domain)
    except PolicyError:
        return _result(domain[:253], version, "UNKNOWN", "INVALID_DOMAIN")
    try:
        policy = config if isinstance(config, Snapshot) else compile_policy(config)
    except ProposalError:
        return _result(name, version, "UNKNOWN", "INVALID_POLICY_CONFIG")
    version = policy.version
    if name in policy.admin_blocked:
        return _result(name, version, "BLOCK", "ADMIN_BLOCKED")
    if name in policy.approved_malicious:
        return _result(name, version, "BLOCK", "APPROVED_MALICIOUS_DOMAIN")
    if data is None:
        data = {}
    if type(data) is not dict or set(data) - {"analysis"}:
        return _result(name, version, "UNKNOWN", "UNTRUSTED_POLICY_DATA")
    observation = data.get("analysis")
    if "analysis" in data and observation is None:
        return _result(name, version, "UNKNOWN", "INVALID_ANALYSIS")
    if observation is not None:
        if type(observation) is not dict or set(observation) != {
            "domain", "risk_score", "source", "model_version", "checked_at", "expires_at"
        }:
            return _result(name, version, "UNKNOWN", "INVALID_ANALYSIS")
        try:
            observed_name = domain_name(observation["domain"])
        except PolicyError:
            observed_name = None
        if observed_name != name:
            return _result(name, version, "UNKNOWN", "ANALYSIS_DOMAIN_MISMATCH")
        score, source = observation["risk_score"], observation["source"]
        model = observation["model_version"]
        if type(score) not in (int, float) or not 0 <= score <= 100 or not math.isfinite(score):
            return _result(name, version, "UNKNOWN", "INVALID_SCORE")
        if not isinstance(source, str) or source not in policy.score_sources or not isinstance(model, str) or not _VERSION.fullmatch(model):
            return _result(name, version, "UNKNOWN", "UNTRUSTED_SCORE_SOURCE")
        try:
            checked = timestamp(observation["checked_at"], "checked_at")
            expires = timestamp(observation["expires_at"], "expires_at")
        except PolicyError:
            return _result(name, version, "UNKNOWN", "INVALID_SCORE_TIME")
        instant = now or datetime.now(timezone.utc)
        if (checked > instant + timedelta(seconds=60) or expires <= instant
                or not checked < expires <= checked + timedelta(days=1)):
            return _result(name, version, "UNKNOWN", "STALE_OR_FUTURE_SCORE")
        return _result(name, version, "WARN" if score >= policy.threshold else "ALLOW",
                       "RISK_SCORE_HIGH" if score >= policy.threshold else "BELOW_WARN_THRESHOLD",
                       score=score, source=f"{source}:{model}",
                       checked_at=checked.isoformat(), expires_at=expires.isoformat())
    if name in policy.official:
        return _result(name, version, "ALLOW", "OFFICIAL_DOMAIN_MATCH")
    return _result(name, version, "UNKNOWN", "INSUFFICIENT_DATA")
