"""Execute installer preflight code only, never root setup or network operations."""
from pathlib import Path
import os
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OptimizedPreflightTests(unittest.TestCase):
    def check(self, script, args):
        text = (ROOT/'scripts/deploy'/script).read_text()
        code = re.search(r"<<'PY'\n(.*?)\nPY\n", text, re.S).group(1)
        env = dict(os.environ, PYTHONPATH=str(ROOT/'apps/dns-agent/src'))
        return subprocess.run([sys.executable, '-O', '-', *args], input=code,
                              text=True, capture_output=True, env=env, timeout=10)

    def test_optimized_python_cannot_disable_dns_validation(self):
        valid = ['192.168.7.69', 'eth0', '192.168.7.0/24', '9.9.9.9',
                 'https://policy.example.org/v1/policies/edge-69/current.json', 'edge-69']
        self.assertEqual(self.check('install-dns-server.sh', valid).returncode, 0)
        for index, value in ((0, '8.8.8.8'), (2, '192.168.0.0/16'),
                             (3, '192.168.7.69'), (5, 'other-device')):
            args = valid.copy()
            args[index] = value
            with self.subTest(index=index):
                self.assertNotEqual(self.check('install-dns-server.sh', args).returncode, 0)

    def test_remote_hostname_uses_shared_dns_contract(self):
        self.assertEqual(self.check('install-policy-server.sh', ['policy.example.org']).returncode, 0)
        for host in ('a..b', 'policy.123', 'localhost', '-bad.example.org', 'policy.example.org/path'):
            with self.subTest(host=host):
                self.assertNotEqual(self.check('install-policy-server.sh', [host]).returncode, 0)


if __name__ == '__main__':
    unittest.main()
