"""캠페인 카탈로그 → 로컬 정책 계약 검증. 인터넷·DNS 서비스 불필요."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/build_campaign_policy.py'
CATALOG = ROOT / 'packages/policy-contract/campaigns/catalog.json'
FIXED = datetime(2030, 1, 1, tzinfo=timezone.utc)
spec = importlib.util.spec_from_file_location('build_campaign_policy', SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8'))


def command(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, timeout=6)


class CampaignPolicyTests(unittest.TestCase):
    def test_catalog_has_four_distinct_campaigns_and_eleven_synthetic_rules(self):
        groups = builder.load_catalog(CATALOG)
        self.assertEqual(len(groups), 4)
        self.assertEqual(sum(len(g['rules']) for g in groups), 11)
        self.assertEqual(len({g['id'] for g in groups}), 4)
        for group in groups:
            for rule in group['rules']:
                self.assertTrue(rule['domain'].endswith('.test'))
                self.assertNotIn('https://', rule['domain'])

    def test_generated_policy_matches_flat_contract(self):
        policy = builder.create_policy(builder.load_catalog(CATALOG), FIXED)
        self.assertEqual(set(policy), {'issued_at', 'expires_at', 'rules'})
        self.assertEqual(len(policy['rules']), 11)
        self.assertEqual([r['decision'] for r in policy['rules']].count('BLOCK'), 6)
        self.assertEqual([r['decision'] for r in policy['rules']].count('WARN'), 3)
        self.assertEqual([r['decision'] for r in policy['rules']].count('ALLOW'), 2)
        self.assertEqual(sum(r['decision'] == 'BLOCK' and r['approved'] for r in policy['rules']), 4)
        for rule in policy['rules']:
            self.assertEqual(set(rule), {'domain', 'decision', 'scope', 'approved',
                                         'expires_at', 'evidence'})
            self.assertEqual(rule['scope'], 'SUBTREE')
            self.assertTrue(rule['evidence'].startswith('synthetic-campaign:'))
        self.assertEqual(datetime.fromisoformat(policy['expires_at']), FIXED + timedelta(minutes=120))

    def test_campaign_subset_is_deterministic_and_no_silent_filtering(self):
        groups = builder.load_catalog(CATALOG)
        p1 = builder.create_policy(groups, FIXED, ('support-fraud',))
        p2 = builder.create_policy(groups, FIXED, ('support-fraud',))
        self.assertEqual(p1, p2)
        self.assertEqual(len(p1['rules']), 3)
        with self.assertRaises(builder.CatalogError):
            builder.create_policy(groups, FIXED, ('unknown-campaign',))
        with self.assertRaises(builder.CatalogError):
            builder.create_policy(groups, FIXED, ('support-fraud', 'support-fraud'))

    def test_cli_lists_and_compiles_to_stdout_without_writing(self):
        p = command('--list')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(p.stdout.strip().splitlines()), 4)
        p = command('--campaign', 'credential-impersonation',
                    '--issued-at', '2030-01-01T00:00:00Z')
        self.assertEqual(p.returncode, 0, p.stderr)
        payload = json.loads(p.stdout)
        self.assertEqual(len(payload['rules']), 3)
        self.assertEqual(payload['issued_at'], FIXED.isoformat())
        self.assertEqual(payload['expires_at'], (FIXED + timedelta(minutes=75)).isoformat())

    def test_invalid_catalog_rejected_atomically(self):
        base = catalog()
        def fails(changer):
            data = catalog()
            changer(data)
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / 'catalog.json'
                path.write_text(json.dumps(data), encoding='utf-8')
                result = command('--catalog', str(path))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, '')
        fails(lambda d: d.update(synthetic=False))
        fails(lambda d: d['campaigns'][0]['rules'][0].update(domain='bank.example.com'))
        fails(lambda d: d['campaigns'][0]['rules'][0].update(domain='x.test\nserver=1.1.1.1'))
        fails(lambda d: d['campaigns'][0]['rules'][0].update(approved=1))
        fails(lambda d: d['campaigns'][0]['rules'][0].update(ttl_minutes=2000))
        fails(lambda d: d['campaigns'][0]['rules'][0].update(decision='REDIRECT'))
        fails(lambda d: d['campaigns'][0]['rules'][0].update(unreviewed_field='oops'))
        fails(lambda d: d['campaigns'][0]['rules'].append(dict(d['campaigns'][0]['rules'][0])))
        fails(lambda d: d['campaigns'][1]['rules'][0].update(domain='account-session-verify.test'))
        fails(lambda d: d['campaigns'][1]['rules'][0].update(case_id='LAB-CRED-001'))
        fails(lambda d: d['campaigns'][1].update(id='credential-impersonation'))

    def test_duplicate_keys_and_nonfinite_values_rejected(self):
        for text in ('{"synthetic":true,"synthetic":true,"campaigns":[]}',
                     '{"synthetic":true,"campaigns":[NaN]}',
                     '{"synthetic":true,"campaigns":[]}',
                     '{"synthetic":true,"campaigns":{},"extra":0}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as d:
                path = Path(d) / 'bad.json'
                path.write_text(text)
                result = command('--catalog', str(path))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')

    def test_conflicting_approved_subtree_rules_rejected(self):
        data = catalog()
        new = dict(data['campaigns'][0]['rules'][0])
        new.update(domain='child.account-session-verify.test', decision='ALLOW',
                   case_id='LAB-CRED-999')
        data['campaigns'][0]['rules'].append(new)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'catalog.json'
            p.write_text(json.dumps(data))
            self.assertEqual(command('--catalog', str(p)).returncode, 2)

    def test_policy_size_limit_matches_dns_agent(self):
        source = builder.load_catalog(CATALOG)[0]
        expanded = [dict(source, rules=source['rules'] * 4000)]
        with self.assertRaisesRegex(builder.CatalogError, '10000'):
            builder.create_policy(expanded, FIXED)

    def test_bad_cli_time_or_unknown_group_has_no_partial_stdout(self):
        for args in (('--issued-at', '2030-01-01T00:00:00'),
                     ('--issued-at', 'nonsense'),
                     ('--campaign', 'no-such-id'),
                     ('--list', '--campaign', 'support-fraud')):
            result = command(*args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, '')

    def test_policy_parser_interoperability_when_repo_code_available(self):
        # In CI this path is always present; locally the generator can be tested standalone.
        source = ROOT / 'apps/dns-agent/src'
        if not source.exists():
            self.skipTest('DNS package unavailable in isolated local generator-only test')
        sys.path.insert(0, str(source))
        from dns_agent.policy import parse_policy, render_config
        payload = builder.create_policy(builder.load_catalog(CATALOG), FIXED)
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        policy = parse_policy(raw, now=FIXED)
        self.assertEqual(len(policy.rules), 11)
        self.assertEqual(len(policy.blocked(FIXED)), 4)
        self.assertEqual(len(policy.blocked(FIXED + timedelta(minutes=31))), 2)
        self.assertEqual(policy.blocked(FIXED + timedelta(minutes=121)), ())
        conf = render_config(policy.blocked(FIXED), port=35353, upstream='127.0.0.1',
                             upstream_port=35453)
        self.assertEqual(conf.count('address=/'), 4)
        self.assertNotIn('account-login-review.test', conf)  # unapproved BLOCK
        self.assertNotIn('account-help-notice.test', conf)  # WARN is not DNS block
        self.assertNotIn('invoice-help-reference.test', conf)  # ALLOW is not DNS block


if __name__ == '__main__':
    unittest.main()
