import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/build_site_test_policy.py'
sys.path.insert(0, str(ROOT / 'apps/dns-agent/src'))
from dns_agent.policy import parse_policy, utcnow


class SiteTestPolicyTests(unittest.TestCase):
    def test_generator_outputs_three_active_short_lived_block_rules(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], text=True,
                                capture_output=True, check=True, timeout=5)
        policy = parse_policy(result.stdout.encode())
        self.assertEqual(policy.blocked(utcnow()), ('daum.net', 'google.com', 'naver.com'))
        self.assertEqual(len(policy.rules), 3)
        self.assertEqual((policy.expires_at - policy.issued_at).total_seconds(), 900)
        self.assertTrue(all(rule.evidence == 'manual-lab-test-not-threat-intelligence'
                            for rule in policy.rules))


if __name__ == '__main__':
    unittest.main()
