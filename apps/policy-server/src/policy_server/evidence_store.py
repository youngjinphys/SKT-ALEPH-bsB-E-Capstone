"""Preview and explicitly replace private review evidence, without inheriting approval.

The local caller serializes with its workspace lock; cloud callers additionally
commit the exported workspace with a durable database revision. Fingerprints
bind content and operator intent, not the external provider's authenticity.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from aleph_policy_sync.snapshot import _regular_read
from . import intel


class EvidenceConflict(ValueError):
    """The state inspected by the operator changed before confirmation."""


def _read(service, name):
    try:
        return _regular_read(service.workspace/name, intel.MAX_ARTIFACT_BYTES,
                             forbidden=0o077, owner=os.geteuid())
    except FileNotFoundError:
        return None


def _context(service):
    raw = {name: _read(service, name) for name in ('verified.json', 'reviews.json')}
    hashes = {name: hashlib.sha256(blob).hexdigest() if blob is not None else None
              for name, blob in raw.items()}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return revision, raw


def _describe(verified, now):
    entries = intel._verification_entries(verified)
    fingerprint = intel.verification_fingerprint(verified)
    checked = intel.parse_time(verified['checked_at'])
    fresh = [row for row in entries if intel.parse_time(row['valid_until']) > now
             and checked <= now + timedelta(seconds=60)
             and now - checked < timedelta(minutes=30)]
    template = intel.review_template(verified)
    return {'fingerprint': fingerprint, 'checked_at': verified['checked_at'],
            'verified': len(entries), 'fresh': len(fresh),
            'review_proposals': len(template['reviews']),
            'protected': sum(intel.is_protected(x['domain']) for x in fresh),
            'unassigned_expressions': verified['unassigned_expressions'],
            'importable': bool(fresh), 'signed': False, 'published': False}


def preview(service, verified):
    description = _describe(verified, datetime.now(timezone.utc))
    with service.locked():
        revision, _ = _context(service)
    return {**description, 'context_revision': revision,
            'reason': None if description['importable'] else 'NO_CURRENT_EVIDENCE'}


def adopt(service, verified, fingerprint, *, context_revision=None, review_revision=None):
    """Replace a complete snapshot only after current-context confirmation.

    An interruption between the two file writes fails closed in the compiler.
    Repeating the confirmed import repairs that pair rather than claiming an
    already-current result solely from verified.json. Backups are not pruned.
    """
    with service.locked():
        description = _describe(verified, datetime.now(timezone.utc))
        if description['fingerprint'] != fingerprint:
            raise EvidenceConflict('Evidence changed; inspect the new preview')
        if not description['importable']:
            raise ValueError('Evidence is expired or future-dated; collect again')
        current_context, raw = _context(service)
        if context_revision is not None:
            if not isinstance(context_revision, str) or context_revision != current_context:
                raise EvidenceConflict('Evidence or reviews changed; reload the import preview')
        else:
            raise EvidenceConflict('A current evidence context is required')
        if review_revision is not None and review_revision != service._review_revision():
            raise EvidenceConflict('Review records changed; reload the import preview')
        previous = intel.parse_json(raw['verified.json']) if raw['verified.json'] else None
        reviews = intel.parse_json(raw['reviews.json']) if raw['reviews.json'] else None
        template = intel.review_template(verified)
        if previous is not None and intel.verification_fingerprint(previous) == fingerprint:
            # Preserve valid existing approvals. A half-written mismatched pair
            # must instead be reset by this explicitly confirmed import.
            try:
                _, valid_reviews, _ = service._verified_reviews()
            except (OSError, ValueError):
                valid_reviews = None
            if valid_reviews is not None:
                return {'imported': False, 'already_current': True, 'fingerprint': fingerprint,
                        'signed': False, 'published': False}
        if previous is not None or reviews is not None:
            archive = service.workspace/'evidence-archive'
            archive.mkdir(mode=0o700, exist_ok=True)
            from .__main__ import _private_dir
            _private_dir(archive)
            folder = archive/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(6))
            folder.mkdir(mode=0o700)
            for name, value in (('verified.json', previous), ('reviews.json', reviews)):
                if value is not None:
                    intel.write_json(folder/name, value)
        intel.write_json(service.workspace/'verified.json', verified)
        intel.write_json(service.workspace/'reviews.json', template)
        return {'imported': True, 'fingerprint': fingerprint,
                'verified': description['verified'], 'review_proposals': description['review_proposals'],
                'reviews_approved': 0, 'signed': False, 'published': False}
