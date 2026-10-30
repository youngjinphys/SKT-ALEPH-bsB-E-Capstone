#!/usr/bin/env python3
"""Print a 15-minute site-blocking policy for an isolated DNS test.

This generates data only. It neither installs nor publishes a policy, and these
domains are examples of legitimate sites, not claims of malicious activity.
"""
from datetime import datetime, timedelta, timezone
import json


def main():
    issued = datetime.now(timezone.utc).replace(microsecond=0)
    expires = (issued + timedelta(minutes=15)).isoformat()
    policy = {
        'issued_at': issued.isoformat(),
        'expires_at': expires,
        'rules': [
            {'domain': domain, 'decision': 'BLOCK', 'scope': 'SUBTREE',
             'approved': True, 'expires_at': expires,
             'evidence': 'manual-lab-test-not-threat-intelligence'}
            for domain in ('naver.com', 'daum.net', 'google.com')
        ],
    }
    print(json.dumps(policy, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
