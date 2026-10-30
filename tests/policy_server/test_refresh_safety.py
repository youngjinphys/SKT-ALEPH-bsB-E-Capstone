"""Refresh concurrency and preflight failures must not contact external APIs."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'apps/policy-server/src'), str(ROOT/'apps/dns-agent/src')]
from policy_server.__main__ import refresh


@unittest.skipIf(os.geteuid() == 0, 'collector must run as non-root')
class RefreshSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root/'state'
        self.state.mkdir(mode=0o700)
        self.key = self.root/'api-key'
        self.key.write_text('offline-key')
        self.key.chmod(0o600)
        self.params = dict(state_dir=self.state, api_key_file=self.key, source='openphish',
                           accept_terms=True, ack_disclosure=True, ack_noncommercial=True,
                           now=datetime(2030, 1, 1, tzinfo=timezone.utc))

    def test_reject_limit_before_any_network_request(self):
        for value in (True, 0, 151, 1.5):
            remote = Mock(side_effect=AssertionError('unexpected network'))
            with self.subTest(value=value), self.assertRaises(ValueError):
                refresh(**self.params, fetch=remote, limit=value)
            remote.assert_not_called()

    def test_concurrent_refresh_refused_before_key_or_network(self):
        path = self.state/'.refresh.lock'
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            remote = Mock(side_effect=AssertionError('unexpected network'))
            with self.assertRaisesRegex(ValueError, 'already running'):
                refresh(**self.params, fetch=remote)
            remote.assert_not_called()
        finally:
            os.close(fd)

    def test_symlink_refresh_lock_cannot_modify_target(self):
        target = self.root/'do-not-touch'
        target.write_text('unchanged')
        (self.state/'.refresh.lock').symlink_to(target)
        remote = Mock(side_effect=AssertionError('unexpected network'))
        with self.assertRaises((ValueError, OSError)):
            refresh(**self.params, fetch=remote)
        self.assertEqual(target.read_text(), 'unchanged')
        remote.assert_not_called()

    def test_success_and_provider_failure_preserve_last_good_run(self):
        candidate = 'https://malicious-example-domain.online/login'
        calls = []
        def remote(url, **kwargs):
            calls.append(url)
            if url.endswith('/feed.txt'):
                return (candidate+'\n').encode()
            self.assertEqual(kwargs['headers']['x-goog-api-key'], 'offline-key')
            return json.dumps({'threats':[{'url':candidate, 'threatTypes':['SOCIAL_ENGINEERING']}],
                               'cacheDuration':'300s'}).encode()
        result = refresh(**self.params, fetch=remote)
        self.assertEqual(result['review_proposals'], 1)
        self.assertEqual(len(calls), 2)
        current = (self.state/'latest.json').read_bytes()
        with self.assertRaises(ValueError):
            refresh(**self.params, fetch=Mock(side_effect=ValueError('provider failure')))
        self.assertEqual((self.state/'latest.json').read_bytes(), current)
        self.assertEqual(len(list((self.state/'runs').iterdir())), 1)
        # A failed call released its lock: the next complete run succeeds.
        refresh(**self.params, fetch=remote)
        self.assertEqual(len(list((self.state/'runs').iterdir())), 2)

    def test_invalid_secret_rejected_before_network(self):
        self.key.chmod(0o644)
        remote = Mock(side_effect=AssertionError('unexpected network'))
        with self.assertRaises(ValueError):
            refresh(**self.params, fetch=remote)
        remote.assert_not_called()


if __name__ == '__main__':
    unittest.main()
