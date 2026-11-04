"""Offline SUBTREE boundary check using a reviewed, pinned full PSL snapshot.

Source: https://publicsuffix.org/list/public_suffix_list.dat
Upstream publicsuffix/list commit: 73f8cc701c084fe07d888ec552b2f0b53281a674
The bundled MPL-2.0 data includes ICANN and PRIVATE rules. Updating it requires
reviewing the snapshot and updating its digest, never a runtime network fetch.
"""
from functools import lru_cache
import hashlib
from pathlib import Path

PSL_PATH = Path(__file__).with_name('public_suffix_list.dat')
PSL_SHA256 = '2f43816a521cab39333ba60714665fe045b8089159816791371e77c5ebb3d4e8'


@lru_cache(maxsize=1)
def _rules():
    raw = PSL_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PSL_SHA256:
        raise ValueError('Public suffix snapshot integrity check failed')
    exact, wildcard, exceptions = set(), set(), set()
    for line in raw.decode('utf-8').splitlines():
        value = line.strip()
        if not value or value.startswith('//'):
            continue
        target = exact
        if value.startswith('!'):
            target, value = exceptions, value[1:]
        elif value.startswith('*.'):
            target, value = wildcard, value[2:]
        target.add(value.encode('idna').decode('ascii').lower())
    # A SUBTREE rule at an ancestor of a delegated namespace would also cross
    # registrant boundaries, even when that ancestor is not itself a PSL match.
    # Example: *.kawasaki.jp makes kawasaki.jp unsafe for SUBTREE blocking.
    boundaries=set()
    for suffix in exact|wildcard:
        labels=suffix.split('.')
        boundaries.update('.'.join(labels[index:]) for index in range(len(labels)))
    return exact, wildcard, exceptions, boundaries


def is_public_suffix(name: str) -> bool:
    """Implement longest PSL match, wildcard and exception precedence.

    Callers provide a canonical ASCII hostname. A PSL exception removes its
    leftmost label from the public suffix; unmatched TLDs use the PSL '*' rule.
    """
    exact, wildcard, exceptions, _ = _rules()
    labels = name.split('.')
    size = 1
    for index in range(len(labels)):
        suffix = '.'.join(labels[index:])
        if suffix in exceptions:
            return False  # An exception and its descendants are registrable.
        if suffix in exact:
            size = max(size, len(labels) - index)
        if index > 0 and suffix in wildcard:
            size = max(size, len(labels) - index + 1)
    return len(labels) <= size


def is_subtree_boundary(name: str) -> bool:
    return name in _rules()[3] or is_public_suffix(name)
