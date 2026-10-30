import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SRC=Path(__file__).resolve().parents[1]/'src'

def cli(*args,cwd=None):
    return subprocess.run([sys.executable,'-m','dns_agent',*map(str,args)],
                          cwd=cwd,env={**os.environ,'PYTHONPATH':str(SRC)},
                          capture_output=True,text=True,timeout=5)

class CliTests(unittest.TestCase):
    def test_no_command_does_not_run_service(self):
        with tempfile.TemporaryDirectory() as d:
            p=cli(cwd=d);self.assertNotEqual(p.returncode,0)
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_example_validate_render_need_no_resolver(self):
        with tempfile.TemporaryDirectory() as d:
            p=cli('example',cwd=d);self.assertEqual(p.returncode,0,p.stderr)
            path=Path(d)/'policy.json';path.write_text(p.stdout)
            checked=cli('validate',path);self.assertEqual(checked.returncode,0,checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['active_blocks'],1)
            rendered=cli('render',path,'--upstream','127.0.0.1','--upstream-port','35453')
            self.assertEqual(rendered.returncode,0,rendered.stderr)
            self.assertIn('address=/blocked.test/',rendered.stdout)
            self.assertNotIn('address=/warn.test/',rendered.stdout)
            self.assertEqual([p.name for p in Path(d).iterdir()],['policy.json'])
    def test_real_domain_validates_without_special_mode(self):
        with tempfile.TemporaryDirectory() as d:
            policy = json.loads(cli('example').stdout)
            policy['rules'][0]['domain'] = 'reviewed.example.org'
            path = Path(d)/'public.json'; path.write_text(json.dumps(policy))
            checked = cli('validate', path)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['active_blocks'], 1)
            rendered = cli('render', path, '--upstream', '127.0.0.1', '--upstream-port', '35453')
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn('address=/reviewed.example.org/', rendered.stdout)
            rejected = cli('validate', path, '--allow-public-domains')
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('unrecognized arguments', rejected.stderr)

    def test_http_notice_render_requires_explicit_ack(self):
        with tempfile.TemporaryDirectory() as d:
            obj=json.loads(cli('example').stdout)
            path=Path(d)/'policy.json'
            path.write_text(json.dumps(obj))
            missing=cli('render',path,'--upstream','127.0.0.1',
                        '--upstream-port','35453','--http-sink-ip','127.0.0.1')
            self.assertEqual(missing.returncode,2)
            self.assertIn('ack-http-sinkhole',missing.stderr)
            ok=cli('render',path,'--upstream','127.0.0.1',
                   '--upstream-port','35453','--http-sink-ip','127.0.0.1',
                   '--ack-http-sinkhole')
            self.assertEqual(ok.returncode,0,ok.stderr)
            self.assertIn('address=/blocked.test/127.0.0.1',ok.stdout)
            self.assertIn('address=/warn.test/127.0.0.1',ok.stdout)
            self.assertNotIn('address=/good.test/127.0.0.1',ok.stdout)

    def test_unknown_scope_fails_with_no_output_or_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            obj=json.loads(cli('example').stdout);obj['rules'][0]['scope']='EXACT'
            path=Path(d)/'bad.json';path.write_text(json.dumps(obj))
            p=cli('render',path,'--upstream','127.0.0.1')
            self.assertEqual(p.returncode,2);self.assertEqual(p.stdout,'')

if __name__=='__main__':unittest.main()
