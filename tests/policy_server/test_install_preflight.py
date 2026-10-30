"""Read-only preflight and isolated source-copy tests; never provision the host."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / 'scripts/deploy/install_checks.py'


class InstallPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if FILE.exists():
            spec = importlib.util.spec_from_file_location('install_checks', FILE)
            cls.m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.m)
        else:
            cls.m = None

    def setUp(self):
        self.assertIsNotNone(self.m, 'installers lack shared account/path preflight and safe source copy')

    def test_wrong_account_identity_is_not_reused(self):
        user = SimpleNamespace(pw_name='aleph-policy-fetch', pw_uid=0, pw_gid=0,
                               pw_dir='/root', pw_shell='/bin/bash')
        with patch.object(self.m.pwd, 'getpwnam', return_value=user), self.assertRaises(ValueError):
            self.m.check_account('aleph-policy-fetch', '/var/lib/aleph-policy-fetch')

    def test_unrelated_group_is_not_adopted(self):
        group = SimpleNamespace(gr_gid=987, gr_mem=['another-user'])
        with patch.object(self.m.pwd, 'getpwnam', side_effect=KeyError), \
             patch.object(self.m.grp, 'getgrnam', return_value=group), self.assertRaises(ValueError):
            self.m.check_account('aleph-policy-fetch', '/var/lib/aleph-policy-fetch')

    def test_destination_symlink_and_writable_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real = base / 'real'
            real.mkdir()
            link = base / 'linked'
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.m.check_directory(link / 'future')
            real.chmod(0o777)
            with self.assertRaises(ValueError):
                self.m.check_directory(real / 'future')

    def test_existing_or_dangling_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'target'
            path.symlink_to(Path(tmp) / 'missing')
            with self.assertRaises(ValueError):
                self.m.require_absent(path)

    def test_copy_excludes_cached_bytecode_and_normalizes_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            (source / 'module.py').write_text('VALUE = 1\n')
            (source / 'module.py').chmod(0o777)
            (source / '__pycache__').mkdir()
            (source / '__pycache__/module.cpython-312.pyc').write_bytes(b'unreviewed bytecode')
            (source / 'orphan.pyc').write_bytes(b'unreviewed sourceless bytecode')
            output = Path(tmp) / 'output'
            self.m.copy_source(source, output)
            self.assertEqual((output / 'module.py').read_text(), 'VALUE = 1\n')
            self.assertFalse((output / '__pycache__').exists())
            self.assertFalse((output / 'orphan.pyc').exists())
            self.assertEqual((output / 'module.py').stat().st_mode & 0o777, 0o644)
            self.assertEqual(output.stat().st_mode & 0o777, 0o755)
            with self.assertRaises(ValueError):
                self.m.copy_source(source, output)

    def test_source_links_and_special_files_never_get_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            output = Path(tmp) / 'output'
            (source / 'module.py').symlink_to('/dev/null')
            with self.assertRaises(ValueError):
                self.m.copy_source(source, output)
            self.assertFalse(output.exists())
            (source / 'module.py').unlink()
            os.mkfifo(source / 'module.py')
            with self.assertRaises(ValueError):
                self.m.copy_source(source, output)
            self.assertFalse(output.exists())

    def test_read_only_preflight_precedes_every_installer_mutation(self):
        # Integration guard: the actual entrypoints must call the checked helper
        # before creating accounts or invoking the privileged DNS installer.
        for name, boundary in [('install-policy-server.sh', '  useradd --system'),
                               ('install-dns-server.sh', '# Reuse managed installer')]:
            script = (ROOT / 'scripts/deploy' / name).read_text()
            self.assertIn('install_checks.py" check', script)
            self.assertLess(script.index('install_checks.py" check'), script.index(boundary))
            self.assertNotIn('cp -a "$ROOT/apps/', script)
