"""Independent examples pin the contract; no resolver required."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from dns_agent.policy import PolicyError, parse_policy, render_config

NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)

def sample():
    return {
        'issued_at': '2030-01-01T00:00:00Z',
        'expires_at': '2030-01-01T01:00:00Z',
        'rules': [dict(domain='blocked.test', decision='BLOCK', scope='SUBTREE',
                       approved=True, expires_at='2030-01-01T00:30:00Z',
                       evidence='isolated-test')],
    }

def parse(obj, **kw):
    return parse_policy(json.dumps(obj).encode(), now=NOW, **kw)

class PolicyTests(unittest.TestCase):
    def test_valid_block_and_canonical_domain(self):
        p = sample(); p['rules'][0]['domain'] = 'Blocked.TEST.'
        policy = parse(p)
        self.assertEqual(policy.blocked(NOW), ('blocked.test',))
        self.assertEqual(policy.blocked(NOW + timedelta(minutes=31)), ())

    def test_default_is_lab_names_only(self):
        p = sample(); p['rules'][0]['domain'] = 'example.org'
        with self.assertRaises(PolicyError): parse(p)
        self.assertEqual(parse(p, allow_public=True).blocked(NOW), ('example.org',))

    def test_decisions_are_not_risk_score_thresholds(self):
        for decision in ('WARN', 'ALLOW'):
            p = sample(); p['rules'][0]['decision'] = decision
            self.assertEqual(parse(p).blocked(NOW), ())
        p = sample(); p['rules'][0]['score'] = 99
        with self.assertRaises(PolicyError): parse(p)

    def test_unapproved_does_not_block(self):
        p = sample(); p['rules'][0]['approved'] = False
        self.assertEqual(parse(p).blocked(NOW), ())
        p['rules'][0]['approved'] = 1
        with self.assertRaises(PolicyError): parse(p)

    def test_exact_is_rejected_not_silently_broadened(self):
        p = sample(); p['rules'][0]['scope'] = 'EXACT'
        with self.assertRaisesRegex(PolicyError, 'SUBTREE'): parse(p)

    def test_bad_domains_are_rejected(self):
        for domain in ('https://x.test/login', 'x.test\nserver=1.1.1.1',
                       'x.test#comment', '127.0.0.1', '::1', '2130706433',
                       'x.123', 'x..test', 'x.test..', '*.x.test', '-x.test',
                       'x-.test', 'a'*64 + '.test', 'x.test ', '한글.test',
                       'x/_test', 'x\\test', 'x.capstone.test', 'capstone.test'):
            with self.subTest(domain=domain), self.assertRaises(PolicyError):
                p = sample(); p['rules'][0]['domain'] = domain; parse(p)

    def test_duplicate_and_conflicting_rules(self):
        p = sample(); p['rules'].append(copy.deepcopy(p['rules'][0]))
        with self.assertRaises(PolicyError): parse(p)
        p = sample(); r = copy.deepcopy(p['rules'][0]); r.update(domain='child.blocked.test',decision='ALLOW'); p['rules'].append(r)
        with self.assertRaisesRegex(PolicyError, 'conflict'): parse(p)
        p['rules'][1]['decision'] = 'BLOCK'
        self.assertEqual(parse(p).blocked(NOW), ('blocked.test','child.blocked.test'))

    def test_bad_json_and_legacy_blocklist_are_not_guessed(self):
        for raw in (b'[]', b'{', b'{"issued_at":1,"issued_at":2}', b'{"x":NaN}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(PolicyError):
                parse_policy(raw, now=NOW)
        with self.assertRaises(PolicyError):
            parse_policy(b' ' * (1024 * 1024 + 1), now=NOW)

    def test_time_validation_and_snapshot_expiry(self):
        for field, value in [('issued_at','2030-01-02T00:00:00Z'),
                             ('issued_at','2030-01-01T00:00:00'),
                             ('issued_at','2030-W01-2T00:00:00Z'),
                             ('issued_at','2030-01-01T00:00:00-00:00'),
                             ('expires_at','2029-01-01T00:00:00Z'),
                             ('expires_at','9999-12-31T23:59:59-23:59'),
                             ('issued_at','0001-01-01T00:00:00+23:59')]:
            with self.subTest(field=field,value=value), self.assertRaises(PolicyError):
                p = sample(); p[field]=value; parse(p)
        self.assertEqual(parse(sample()).blocked(NOW + timedelta(hours=2)), ())
        p=sample(); p['rules'][0]['expires_at']='2030-01-02T00:00:00Z'
        with self.assertRaises(PolicyError): parse(p)

    def test_disabled_invalid_rule_is_still_rejected(self):
        p=sample(); p['rules'][0].update(approved=False,domain='x.test\nserver=bad')
        with self.assertRaises(PolicyError): parse(p)

    def test_json_escaping_expansion_is_bounded_before_persistence(self):
        obj = sample()
        obj['rules'] = [
            dict(domain=f'bad{i}.test', decision='BLOCK', scope='SUBTREE',
                 approved=True, expires_at='2030-01-01T00:30:00Z',
                 evidence='가' * 256)
            for i in range(750)
        ]
        raw = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.assertLess(len(raw), 1024 * 1024)
        with self.assertRaisesRegex(PolicyError, 'canonical policy exceeds'):
            parse_policy(raw, now=NOW)

    def test_limit_rules_and_unknown_fields(self):
        p=sample(); p['unknown']='silent semantics'
        with self.assertRaises(PolicyError): parse(p)
        p=sample(); p['rules']=[p['rules'][0]]*10001
        with self.assertRaises(PolicyError): parse(p)

    def test_explicit_system_dns_configuration(self):
        config = render_config(('blocked.test',), port=53, upstream='9.9.9.9',
                               upstream_port=53, listen_address='192.168.44.10',
                               system_dns=True)
        self.assertIn('listen-address=192.168.44.10', config)
        self.assertIn('port=53', config)
        self.assertIn('address=/blocked.test/', config)
        for kwargs in (
            dict(port=53, upstream='9.9.9.9', upstream_port=53),
            dict(port=53, upstream='9.9.9.9', upstream_port=53,
                 listen_address='0.0.0.0', system_dns=True),
            dict(port=53, upstream='9.9.9.9', upstream_port=53,
                 listen_address='8.8.8.8', system_dns=True),
            dict(port=53, upstream='192.168.44.10', upstream_port=53,
                 listen_address='192.168.44.10', system_dns=True),
            dict(port=35353, upstream='9.9.9.9', upstream_port=53,
                 listen_address='192.168.44.10'),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(PolicyError):
                render_config((), **kwargs)

    def test_config_is_isolated_and_contains_no_remote_code(self):
        config=render_config(('blocked.test',), port=35353, upstream='127.0.0.1', upstream_port=35453)
        for line in ('listen-address=127.0.0.1','port=35353','no-resolv','no-hosts','cache-size=0',
                     'server=127.0.0.1#35453','address=/blocked.test/'):
            self.assertIn(line+'\n', config)
        for forbidden in ('conf-dir=', 'log-queries', '/etc/', 'dhcp-range=', '0.0.0.0'):
            self.assertNotIn(forbidden, config)
        with self.assertRaises(PolicyError): render_config((),port=35353,upstream='fe80::1%\nconf-file=/tmp/x',upstream_port=53)
        with self.assertRaises(PolicyError): render_config((),port=53,upstream='127.0.0.1',upstream_port=35453)
        with self.assertRaises(PolicyError): render_config((),port=35353,upstream='127.0.0.1',upstream_port=35353)

if __name__ == '__main__': unittest.main()
