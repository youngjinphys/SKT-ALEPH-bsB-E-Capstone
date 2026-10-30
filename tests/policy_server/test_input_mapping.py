"""An explicit external field mapping must not silently fall back to other data."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'apps/policy-server/src')]
from policy_server.data_adapter import adapt_data


class MappingTests(unittest.TestCase):
    def test_missing_mapped_analysis_is_an_error_not_top_level_fallback(self):
        raw = {'analysis': {'domain': 'host.test', 'risk_score': 0}, 'payload': {}}
        with self.assertRaises(ValueError):
            adapt_data(raw, {'analysis': 'payload.scan'})

    def test_explicit_null_is_preserved_for_unknown_result(self):
        raw = {'analysis': {'domain': 'host.test', 'risk_score': 0}, 'payload': {'scan': None}}
        self.assertEqual(adapt_data(raw, {'analysis': 'payload.scan'}), {'analysis': None})

    def test_mapped_value_exclusively_wins_and_is_independent_copy(self):
        raw = {'analysis': {'risk_score': 0}, 'payload': {'scan': {'risk_score': 90}}}
        result = adapt_data(raw, {'analysis': 'payload.scan'})
        raw['payload']['scan']['risk_score'] = 0
        self.assertEqual(result, {'analysis': {'risk_score': 90}})
