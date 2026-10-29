"""Run only inside a fresh network namespace, invoked by test_firewall_guard."""
import importlib.util
from pathlib import Path
import subprocess

path = Path(__file__).resolve().parents[2] / 'infra' / 'edge' / 'firewall_guard.py'
spec = importlib.util.spec_from_file_location('guard', path)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
c = {'token': '0' * 32, 'listen': '192.168.44.10', 'interface': 'eth0',
     'subnet': '192.168.44.0/24'}
def nft(*args):
    return subprocess.run(['/usr/sbin/nft', *args], check=True, capture_output=True, text=True).stdout

def refuse(fn):
    try: fn()
    except (RuntimeError, OSError, subprocess.CalledProcessError): return
    raise AssertionError('unsafe operation succeeded')

# Foreign table is untouched on apply/remove.
nft('add', 'table', 'inet', 'aleph_dns')
nft('add', 'chain', 'inet', 'aleph_dns', 'foreign')
before = nft('-a', 'list', 'table', 'inet', 'aleph_dns')
refuse(lambda: g.apply(c)); refuse(lambda: g.remove(c))
assert before == nft('-a', 'list', 'table', 'inet', 'aleph_dns')
nft('delete', 'table', 'inet', 'aleph_dns')
# First creation, idempotent restart, and refusal of foreign additions.
g.apply(c)
before = nft('-a', 'list', 'table', 'inet', 'aleph_dns')
g.apply(c)
assert before == nft('-a', 'list', 'table', 'inet', 'aleph_dns')
nft('add', 'rule', 'inet', 'aleph_dns', 'input', 'counter')
before = nft('-a', 'list', 'table', 'inet', 'aleph_dns')
refuse(lambda: g.apply(c)); refuse(lambda: g.remove(c))
assert before == nft('-a', 'list', 'table', 'inet', 'aleph_dns')
nft('delete', 'table', 'inet', 'aleph_dns')
# Table/chain comments are foreign metadata even when old nft JSON omits them.
for kind in ('table', 'chain'):
    rules = g.render(c)
    if kind == 'table':
        rules = rules.replace('create table inet aleph_dns', 'create table inet aleph_dns { comment "foreign"; }', 1)
    else:
        rules = rules.replace('policy accept; }', 'policy accept; comment "foreign"; }', 1)
    g.run_nft(['-f', '/dev/stdin'], input=rules, capture_output=True)
    before = nft('-a', 'list', 'table', 'inet', 'aleph_dns')
    refuse(lambda: g.apply(c)); refuse(lambda: g.remove(c))
    assert before == nft('-a', 'list', 'table', 'inet', 'aleph_dns')
    nft('delete', 'table', 'inet', 'aleph_dns')
# Conditional deletion rejects an extra rule added after validation.
g.apply(c)
gen, entries = g.snapshot(); handle = g.checked_handle(c, entries)
g.require_generation_guard(gen)
nft('add', 'rule', 'inet', 'aleph_dns', 'input', 'counter')
before = nft('-a', 'list', 'table', 'inet', 'aleph_dns')
refuse(lambda: g.delete_with_generation(gen, handle))
assert before == nft('-a', 'list', 'table', 'inet', 'aleph_dns')
nft('delete', 'table', 'inet', 'aleph_dns')
# Same-name replacement must survive a stale deletion.
g.apply(c)
gen, entries = g.snapshot(); handle = g.checked_handle(c, entries)
nft('delete', 'table', 'inet', 'aleph_dns')
nft('add', 'table', 'inet', 'aleph_dns')
nft('add', 'chain', 'inet', 'aleph_dns', 'replacement')
before = nft('-a', 'list', 'table', 'inet', 'aleph_dns')
refuse(lambda: g.delete_with_generation(gen, handle))
assert before == nft('-a', 'list', 'table', 'inet', 'aleph_dns')
nft('delete', 'table', 'inet', 'aleph_dns')
# Unrelated ruleset changes also invalidate a snapshot.
g.apply(c)
gen, entries = g.snapshot(); handle = g.checked_handle(c, entries)
nft('add', 'table', 'inet', 'unrelated')
refuse(lambda: g.delete_with_generation(gen, handle))
g.remove(c)
assert 'unrelated' in nft('list', 'tables')
assert 'aleph_dns' not in nft('list', 'tables')
refuse(lambda: g.require_generation_guard(0))
# Simulate a kernel ignoring the generation attribute by replacing it with 0.
# The probe must fail closed and its create/delete batch must leave no table.
real_socket = g.netlink_socket
class IgnoreGeneration:
    def __enter__(self):
        self.sock = real_socket()
        return self
    def __exit__(self, *args): self.sock.close()
    def send(self, request):
        request = bytearray(request)
        request[24:28] = bytes(4)
        return self.sock.send(request)
    def recv(self, size): return self.sock.recv(size)
current_gen = g.generation()
g.netlink_socket = IgnoreGeneration
try:
    refuse(lambda: g.require_generation_guard(current_gen))
finally:
    g.netlink_socket = real_socket
assert 'aleph_probe_' not in nft('list', 'tables')
c['subnet'] = '192.168.44.10/32'
g.apply(c); g.apply(c); g.remove(c)
print('isolated nft ownership and generation scenarios passed')
