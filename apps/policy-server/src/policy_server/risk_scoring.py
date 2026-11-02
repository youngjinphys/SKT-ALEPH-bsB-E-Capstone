"""Standalone, non-enforcing DNS phishing-risk scoring proposal (v1.0).

This module is deliberately NOT imported by the current policy engine, CLI,
DNS agent, API adapters, approval process, or policy publisher. It performs NO
network, filesystem, or DNS operations. Nothing is deployed automatically.

The eight proposed criteria (NOT calibrated detection weights) are:
    R1 registered <= 7*24h ago                      10
    R2 registered > 7*24h and <= 30*24h ago         5
    R3 independently verified phishing report       15
    R4 approved security-agency suspicion list       30
    R5 live DNS A/AAAA equals verified bad IP        10
    R6 live CNAME equals verified bad domain          10
    R7 officially confirmed phishing incident        70
    R8 reviewed internal suspicion watchlist         55

Input is pre-verified, domain-scoped evidence supplied by a trusted caller.
A caller MUST validate source identity, authorization, incident identity,
current DNS observations, and the relevant provider's use conditions. Merely
setting status='MATCH' in a dict does NOT authenticate anything. In particular,
URL/path-level evidence must never be relabeled as host-level EXACT evidence.

API:
    score_domain(domain, registration=..., observations=..., now=...)

`registration` is either None (unknown), {'status':'UNAVAILABLE'|'STALE'}, or:
  { 'status':'OBSERVED', 'domain':'sample.example', 'scope':'EXACT',
    'source_id':'registry-rdap', 'origin_id':'rdap-sample.example',
    'observed_at':'2026-11-02T02:00:00Z',
    'valid_until':'2026-11-02T02:05:00Z',
    'created_at':'2026-10-30T02:00:00Z' }

`observations` maps any of R3,R4,R5,R6,R7,R8 to an evidence object:
  * Unknown: {'status':'UNAVAILABLE'} or {'status':'STALE'}; absent is unknown.
  * Complete negative check:
      {'status':'NO_MATCH', 'domain':'sample.example', 'scope':'EXACT',
       'source_id':'approved-provider', 'observed_at':'...Z',
       'valid_until':'...Z'}
  * Positive check:
      {'status':'MATCH', 'domain':'sample.example', 'scope':'EXACT',
       'source_id':'approved-provider', 'origin_id':'canonical-incident-123',
       'observed_at':'...Z', 'valid_until':'...Z',
       ... rule-specific fields ...}
      R3/R4/R7 additionally require 'event_at' within the past 30 days;
      R5 requires 'resolved_ip' and 'listed_ip' (same IPv4/IPv6 address);
      R6 requires 'cname_target' and 'listed_domain' (same exact hostname).

`origin_id` must identify the *original real-world observation*, not its copy
in different databases. When multiple rules share an origin_id, only the
highest-weight rule counts, even across groups. This is conservative only if
the trusted producer correctly canonicalizes origins. R1/R2 are exclusive.

Group caps: age<=10, incident/list<=70, infrastructure<=20, total<=100.
WARN_CANDIDATE requires a verified score FLOOR >=70 even when other evidence
is missing. LOW_CANDIDATE (<70) requires successful, unexpired observations
for registration and ALL six remaining rules; any unavailable/expired check
makes the verdict UNKNOWN. A stale MATCH never contributes points.

Results are NOT `engine.evaluate_policy` analysis payloads and CANNOT be
issued as DNS policies. Future integration requires an authenticated producer,
source allowlisting, evidence retention, and an explicitly reviewed adapter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ipaddress
import re
from typing import Any

from dns_agent.policy import PolicyError, domain_name, timestamp


class RiskInputError(ValueError):
    """Evidence input is structurally invalid or inconsistent."""


MODEL_VERSION = "risk-1.0"
WARN_THRESHOLD = 70
_WEIGHTS = {"R1": 10, "R2": 5, "R3": 15, "R4": 30,
            "R5": 10, "R6": 10, "R7": 70, "R8": 55}
_GROUPS = {"R1": "age", "R2": "age", "R3": "threat", "R4": "threat",
           "R5": "infrastructure", "R6": "infrastructure",
           "R7": "threat", "R8": "threat"}
_CAPS = {"age": 10, "threat": 70, "infrastructure": 20}
_SIGNALS = frozenset(("R3", "R4", "R5", "R6", "R7", "R8"))
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}\Z")
_RECENT_RULES = frozenset(("R3", "R4", "R7"))
_ONE_DAY = timedelta(days=1)
_THIRTY_DAYS = timedelta(days=30)
_MAX_FUTURE_SKEW = timedelta(seconds=60)


def _name(value: Any, label: str) -> str:
    try:
        return domain_name(value)
    except PolicyError as exc:
        raise RiskInputError(f"{label}: invalid exact hostname") from exc


def _stamp(value: Any, label: str) -> datetime:
    try:
        return timestamp(value, label)
    except PolicyError as exc:
        raise RiskInputError(f"{label}: invalid UTC-aware timestamp") from exc


def _id(value: Any, label: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise RiskInputError(f"{label}: invalid stable identifier")
    return value


def _keys(record: Any, wanted: frozenset[str] | set[str], label: str) -> dict:
    if type(record) is not dict or set(record) != set(wanted):
        raise RiskInputError(f"{label}: required fields do not match contract")
    return record


def _time_window(record: dict, label: str, now: datetime) -> tuple[bool, datetime]:
    seen = _stamp(record["observed_at"], f"{label}.observed_at")
    end = _stamp(record["valid_until"], f"{label}.valid_until")
    if seen > now + _MAX_FUTURE_SKEW or not seen < end <= seen + _ONE_DAY:
        raise RiskInputError(f"{label}: invalid observation validity interval")
    return end > now, end


def _scope(record: dict, domain: str, label: str) -> None:
    if record["scope"] != "EXACT" or _name(record["domain"], label) != domain:
        raise RiskInputError(f"{label}: requires EXACT evidence for the queried domain")
    _id(record["source_id"], f"{label}.source_id")


def _registration(raw: Any, domain: str, now: datetime):
    if raw is None:
        return None, None, None
    if type(raw) is not dict:
        raise RiskInputError("registration: expected an object")
    status = raw.get("status")
    if status in ("UNAVAILABLE", "STALE"):
        _keys(raw, {"status"}, "registration")
        return None, None, None
    if status != "OBSERVED":
        raise RiskInputError("registration: invalid status")
    _keys(raw, {"status", "domain", "scope", "source_id", "origin_id",
                "observed_at", "valid_until", "created_at"}, "registration")
    _scope(raw, domain, "registration")
    origin = _id(raw["origin_id"], "registration.origin_id")
    alive, end = _time_window(raw, "registration", now)
    created = _stamp(raw["created_at"], "registration.created_at")
    if created > now:
        raise RiskInputError("registration: creation date is in the future")
    if not alive:
        return None, None, None
    age = now - created
    rule = "R1" if age <= timedelta(days=7) else "R2" if age <= _THIRTY_DAYS else None
    return rule, origin, end


def _signal(rule: str, record: Any, domain: str, now: datetime):
    if record is None:
        return "UNKNOWN", None, None
    if type(record) is not dict:
        raise RiskInputError(f"{rule}: expected an evidence object")
    state = record.get("status")
    if state in ("UNAVAILABLE", "STALE"):
        _keys(record, {"status"}, rule)
        return "UNKNOWN", None, None
    base = {"status", "domain", "scope", "source_id", "observed_at", "valid_until"}
    if state == "NO_MATCH":
        _keys(record, base, rule)
    elif state == "MATCH":
        extra = {"origin_id"}
        if rule in _RECENT_RULES:
            extra |= {"event_at"}
        elif rule == "R5":
            extra |= {"resolved_ip", "listed_ip"}
        elif rule == "R6":
            extra |= {"cname_target", "listed_domain"}
        _keys(record, base | extra, rule)
    else:
        raise RiskInputError(f"{rule}: invalid status")
    _scope(record, domain, rule)
    alive, end = _time_window(record, rule, now)
    if state == "NO_MATCH":
        return ("CLEAR", None, end) if alive else ("UNKNOWN", None, None)
    origin = _id(record["origin_id"], f"{rule}.origin_id")
    if rule in _RECENT_RULES:
        event_at = _stamp(record["event_at"], f"{rule}.event_at")
        if event_at > now + _MAX_FUTURE_SKEW:
            raise RiskInputError(f"{rule}: future event timestamp")
        if not now - _THIRTY_DAYS <= event_at <= now:
            return "UNKNOWN", None, None  # old reports are not current positives
    elif rule == "R5":
        if type(record["resolved_ip"]) is not str or type(record["listed_ip"]) is not str:
            raise RiskInputError("R5: IP addresses must be text literals")
        try:
            resolved = ipaddress.ip_address(record["resolved_ip"])
            listed = ipaddress.ip_address(record["listed_ip"])
        except (ValueError, TypeError) as exc:
            raise RiskInputError("R5: invalid IP observation") from exc
        if resolved != listed:
            raise RiskInputError("R5: resolved and listed IP values disagree")
    elif rule == "R6":
        cname = _name(record["cname_target"], "R6.cname_target")
        listed = _name(record["listed_domain"], "R6.listed_domain")
        if cname != listed:
            raise RiskInputError("R6: CNAME target and listed domain disagree")
    return ("MATCH", origin, end) if alive else ("UNKNOWN", None, None)


def score_domain(domain: str, *, registration: dict | None = None,
                 observations: dict[str, dict] | None = None,
                 now: datetime | None = None) -> dict:
    """Compute a risk *proposal* from externally verified evidence; never enforce.

    On missing/expired data, returns UNKNOWN unless the verified score floor
    already reaches the WARN threshold. `risk_score` is None on UNKNOWN.
    `score_floor` is a diagnostic lower bound, NOT a low-risk decision.
    All results include traceable rule IDs but never raw provider secrets.
    Malformed evidence raises RiskInputError (do not silently ALLOW).
    """
    name = _name(domain, "domain")
    instant = datetime.now(timezone.utc) if now is None else now
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise RiskInputError("now: expected an aware datetime")
    instant = instant.astimezone(timezone.utc)
    if observations is None:
        observations = {}
    if type(observations) is not dict or not set(observations) <= _SIGNALS:
        raise RiskInputError("observations: only R3,R4,R5,R6,R7,R8 are allowed")

    age_rule, age_origin, age_end = _registration(registration, name, instant)
    positive: list[tuple[str, str, datetime]] = []
    unknown: list[str] = []
    ends: list[datetime] = []
    if age_end is None:
        unknown.append("REGISTRATION")
    else:
        ends.append(age_end)
        if age_rule is not None:
            positive.append((age_rule, age_origin, age_end))
    for rule in sorted(_SIGNALS):
        status, origin, expires = _signal(rule, observations.get(rule), name, instant)
        if status == "UNKNOWN":
            unknown.append(rule)
        else:
            if expires is not None:
                ends.append(expires)
            if status == "MATCH":
                positive.append((rule, origin, expires))

    # One original observation can contribute only once, across all groups.
    # The highest-weight signal is retained; ties are stable (rule ID order).
    counted: list[tuple[str, str, datetime]] = []
    duplicates: list[str] = []
    origins: set[str] = set()
    for candidate in sorted(positive, key=lambda x: (-_WEIGHTS[x[0]], x[0])):
        rule, origin, expires = candidate
        if origin in origins:
            duplicates.append(rule)
        else:
            counted.append(candidate)
            origins.add(origin)

    bucket = {name: 0 for name in _CAPS}
    for rule, _origin, _end in counted:
        bucket[_GROUPS[rule]] += _WEIGHTS[rule]
    group_scores = {group: min(_CAPS[group], total) for group, total in bucket.items()}
    floor = min(100, sum(group_scores.values()))
    complete = not unknown
    status = ("WARN_CANDIDATE" if floor >= WARN_THRESHOLD else
              "LOW_CANDIDATE" if complete else "UNKNOWN")
    # For partial high-risk outcomes, only the supporting MATCH observations
    # are relevant to this WARN proposal's expiry, not unfinished checks.
    relevant_ends = ([end for _rule, _origin, end in counted]
                     if not complete and status == "WARN_CANDIDATE" else ends)
    # Respect the proposal engine's maximum 24h observation lifetime, even
    # when a provider timestamps its observation up to 60 seconds ahead.
    expires = min(min(relevant_ends), instant + _ONE_DAY) if relevant_ends else None
    return {
        "domain": name,
        "scope": "EXACT",
        "model_version": MODEL_VERSION,
        "decision": status,
        "risk_score": floor if status != "UNKNOWN" else None,
        "score_floor": floor,
        "threshold": WARN_THRESHOLD,
        "coverage_complete": complete,
        "unknown_inputs": sorted(unknown),
        "matched_rules": sorted(rule for rule, _origin, _end in positive),
        "counted_rules": sorted(rule for rule, _origin, _end in counted),
        "deduplicated_rules": sorted(duplicates),
        "group_scores": group_scores,
        "checked_at": instant.isoformat(),
        "expires_at": expires.isoformat() if expires else None,
        "enforcement": "NONE",
    }
