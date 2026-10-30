"""Exercise the documented installed-code validation without writing bytecode."""
import os
import hashlib
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def inventory(root):
    return {str(path.relative_to(root)):
            ('directory' if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest(),
             path.stat().st_mode & 0o777)
            for path in root.rglob('*')}


class DocumentedValidationTests(unittest.TestCase):
    def test_installed_validation_commands_leave_installed_tree_unchanged(self):
        guide = (ROOT / 'infra/edge/README.md').read_text(encoding='utf-8')
        commands = [line.strip() for line in guide.splitlines()
                    if '/opt/aleph-dns/src' in line
                    and ' -m dns_agent validate ' in line]
        self.assertGreaterEqual(len(commands), 1, 'no installed validation command found')
        with tempfile.TemporaryDirectory() as work:
            policy = Path(work) / 'policy.json'
            with policy.open('wb') as out:
                subprocess.run(['python3', str(ROOT/'scripts/build_site_test_policy.py')],
                               stdout=out, check=True)
            for index, line in enumerate(commands):
                with self.subTest(command=line):
                    copied = Path(work) / f'src-{index}'
                    shutil.copytree(ROOT / 'apps/dns-agent/src', copied,
                                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
                    before = inventory(copied)
                    command = shlex.split(line)
                    self.assertEqual(command[:2], ['sudo', 'env'])
                    command = command[1:]
                    command = ['PYTHONPATH='+str(copied) if part.startswith('PYTHONPATH=')
                               else part for part in command]
                    command[-1] = str(policy)
                    env = dict(os.environ)
                    env.pop('PYTHONDONTWRITEBYTECODE', None)
                    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(inventory(copied), before,
                                     'documented command changed installed code or created bytecode')
