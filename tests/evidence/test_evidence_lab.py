"""Evidence accounting must not turn missing or failed observations into success."""
import importlib.util
from pathlib import Path
import unittest
import os
import json
import shutil
import subprocess
import sys
import tempfile

MODULE = Path(__file__).resolve().parents[2] / 'scripts/evidence_lab.py'

class EvidenceAccountingTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'evidence laboratory implementation is missing')
        spec = importlib.util.spec_from_file_location('evidence_lab', MODULE)
        self.lab = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lab)

    @unittest.skipUnless(os.geteuid() != 0 and shutil.which('dnsmasq') and shutil.which('dig'),
                         'loopback integration requires non-root and installed binaries')
    def test_cli_works_without_inherited_pythonpath(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'evidence.json'
            env = dict(os.environ)
            env.pop('PYTHONPATH', None)
            result = subprocess.run([sys.executable, str(MODULE), '--rounds', '1',
                                     '--output', str(output)], env=env, capture_output=True,
                                    text=True, timeout=30, cwd=directory)
            report = json.loads(output.read_text())
            self.assertEqual(result.returncode, 0, report.get('error', result.stderr))
            self.assertTrue(report['passed'])
            self.assertEqual(report['summary']['attempted'], 80)

    def test_empty_sample_has_no_success_rate_or_latency(self):
        result = self.lab.summarize([])
        self.assertEqual(result['attempted'], 0)
        self.assertIsNone(result['match_rate'])
        self.assertIsNone(result['successful_query_ms_p95'])

    def test_timeout_remains_in_denominator(self):
        result = self.lab.summarize([
            {'ok': True, 'elapsed_ms': 2.0},
            {'ok': False, 'elapsed_ms': 1000.0},
        ])
        self.assertEqual(result['attempted'], 2)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['match_rate'], 0.5)
        self.assertEqual(result['successful_query_ms_p95'], 2.0)

    def test_noerror_without_expected_answer_is_not_restoration(self):
        result = self.lab.parse_reply(';; ->>HEADER<<- status: NOERROR, id: 1\n', 0, 'A')
        self.assertFalse(self.lab.matches(result, 'NOERROR', ['192.0.2.20'], 'blocked.test'))

    def test_timeout_or_process_failure_is_not_a_block(self):
        result = self.lab.parse_reply(';; ->>HEADER<<- status: NXDOMAIN, id: 1\n', 9, 'A')
        self.assertFalse(self.lab.matches(result, 'NXDOMAIN', [], 'blocked.test'))

    def test_positive_response_checks_address_and_type(self):
        raw = ';; ->>HEADER<<- status: NOERROR, id: 1\nblocked.test. 0 IN A 192.0.2.20\n'
        self.assertTrue(self.lab.matches(self.lab.parse_reply(raw, 0, 'A'), 'NOERROR', ['192.0.2.20'], 'blocked.test'))
        self.assertFalse(self.lab.matches(self.lab.parse_reply(raw, 0, 'AAAA'), 'NOERROR', ['2001:db8::20'], 'blocked.test'))

    def test_unrelated_owner_with_same_address_is_not_valid_evidence(self):
        # dig can include a matching address that belongs to an unrelated name.
        raw = (';; ->>HEADER<<- status: NOERROR, id: 1\n'
               'unrelated.test. 0 IN A 192.0.2.20\n')
        reply = self.lab.parse_reply(raw, 0, 'A')
        self.assertFalse(self.lab.matches(reply, 'NOERROR', ['192.0.2.20'], 'blocked.test'))

    def test_cname_chain_can_supply_expected_alias_address(self):
        raw = (';; ->>HEADER<<- status: NOERROR, id: 1\n'
               'alias.test. 0 IN CNAME blocked.test.\n'
               'blocked.test. 0 IN A 192.0.2.20\n')
        reply = self.lab.parse_reply(raw, 0, 'A')
        self.assertTrue(self.lab.matches(reply, 'NOERROR', ['192.0.2.20'], 'alias.test'))

    def test_unexpected_positive_answer_cannot_count_as_nxdomain(self):
        raw = ';; ->>HEADER<<- status: NXDOMAIN, id: 1\nblocked.test. 0 IN A 192.0.2.20\n'
        self.assertFalse(self.lab.matches(self.lab.parse_reply(raw, 0, 'A'), 'NXDOMAIN', [], 'blocked.test'))

if __name__ == '__main__':
    unittest.main()
