"""Read-only install preflight and bounded, cache-free source installation.

Called by both server installers before their first system mutation. This is not
an upgrade tool or a signature verification of the operator-selected checkout.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import os
from pathlib import Path
import pwd
import shutil
import stat
import tempfile


def require_absent(path):
    if os.path.lexists(path):
        raise ValueError(f'existing installation path; preserve and inspect: {path}')


def check_directory(path):
    path = Path(path).absolute()
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.geteuid())
                or info.st_mode & 0o022 and not sticky_root):
            raise ValueError(f'unsafe install directory or ancestor: {current}')


def check_account(name, home):
    try:
        account = pwd.getpwnam(name)
    except KeyError:
        try:
            grp.getgrnam(name)
        except KeyError:
            return
        raise ValueError(f'unrelated existing service group: {name}') from None
    if (account.pw_uid == 0 or account.pw_gid == 0 or account.pw_dir != home
            or account.pw_shell not in ('/sbin/nologin', '/usr/sbin/nologin')):
        raise ValueError(f'unsafe existing service account: {name}')
    try:
        group = grp.getgrnam(name)
    except KeyError:
        raise ValueError(f'missing dedicated primary group: {name}') from None
    if (group.gr_gid != account.pw_gid or set(group.gr_mem) - {name}
            or any(p.pw_name != name and (p.pw_uid == account.pw_uid or p.pw_gid == account.pw_gid)
                   for p in pwd.getpwall())):
        raise ValueError(f'service identity or group is shared: {name}')


def check_install(role, device):
    if os.geteuid() != 0:
        raise ValueError('system installation preflight requires root')
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', device):
        raise ValueError('invalid device ID')
    directories = ['/opt', '/var/lib', '/etc/systemd/system', '/etc/aleph-policy-sync/trust']
    absent = ['/opt/aleph-policy-code', '/etc/aleph-policy-sync/trust/.incoming.pem']
    if role == 'remote':
        check_account('aleph-policy-server', '/var/lib/aleph-policy-server')
        directories += ['/etc/nginx/snippets', '/srv/aleph-policy-feed']
        absent += ['/var/lib/aleph-policy-server', f'/srv/aleph-policy-feed/{device}',
                   '/etc/nginx/snippets/aleph-policy-feed.conf']
        units = ['aleph-policy-refresh.service', 'aleph-policy-refresh.timer']
    elif role == 'dns':
        check_account('aleph-policy-fetch', '/var/lib/aleph-policy-fetch')
        absent += ['/var/lib/aleph-policy-fetch', '/var/lib/aleph-policy-apply']
        units = [f'aleph-policy-{kind}.{suffix}' for kind in ('fetch', 'apply')
                 for suffix in ('service', 'timer')]
    else:
        raise ValueError('unknown installer role')
    for directory in directories:
        check_directory(directory)
    for path in absent:
        check_directory(Path(path).parent)
        require_absent(path)
    for unit in units:
        for base in ('/etc/systemd/system', '/usr/lib/systemd/system', '/lib/systemd/system'):
            require_absent(Path(base) / unit)
            require_absent(Path(base) / (unit + '.d'))


def copy_source(source, destination):
    """Stage only source (.py/.json); do not install untracked Python bytecode."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('source directory must not be a symlink')
    for entry in source.rglob('*'):
        mode = entry.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError('source contains a symlink or special file')
    check_directory(destination.parent)
    require_absent(destination)

    def ignore(folder, names):
        return [name for name in names if name.startswith('.') or name == '__pycache__'
                or ((Path(folder) / name).is_file() and Path(name).suffix not in ('.py', '.json'))]

    def copy_file(src, dst):
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('source file changed during install')
            with os.fdopen(os.dup(fd), 'rb') as file:
                data = file.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError('runtime source file exceeds 2 MiB')
        finally:
            os.close(fd)
        with open(dst, 'xb') as file:
            file.write(data)
            os.fchmod(file.fileno(), 0o644)
        return dst

    staging = Path(tempfile.mkdtemp(prefix='.aleph-source-', dir=destination.parent))
    try:
        tree = staging / 'src'
        shutil.copytree(source, tree, ignore=ignore, copy_function=copy_file)
        for entry in (tree, *tree.rglob('*')):
            entry.chmod(0o755 if entry.is_dir() else 0o644)
        require_absent(destination)
        os.rename(tree, destination)
    finally:
        shutil.rmtree(staging)




RUNTIME_PATHS = tuple(
    Path("apps") / app / "src" for app in ("dns-agent", "policy-sync", "policy-server")
)


def _runtime_inventory(root, *, installed):
    """Read only canonical source files. Reject stale extras or writable installed code."""
    root = Path(root)
    paths = {}
    expected_owner = 0 if os.geteuid() == 0 else os.geteuid()
    for folder in RUNTIME_PATHS:
        directory = root / folder
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"runtime component unavailable: {folder}")
        if installed:
            # This also covers the package/src parents, not only leaf files.
            check_directory(directory)
        for entry in directory.rglob("*"):
            rel = entry.relative_to(root)
            info = entry.lstat()
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError(f"runtime contains symlink or special file: {rel}")
            if installed and (info.st_uid != expected_owner or info.st_mode & 0o022):
                raise ValueError(f"installed runtime is not owned and protected: {rel}")
            if stat.S_ISDIR(info.st_mode):
                if installed and entry.name == "__pycache__":
                    raise ValueError("unreviewed bytecode directory in installed runtime")
                continue
            excluded = any(x.startswith(".") or x == "__pycache__" for x in rel.parts)
            if excluded or entry.suffix not in (".py", ".json"):
                if installed:
                    raise ValueError(f"extra unexpected installed code/data: {rel}")
                continue
            fd = os.open(entry, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024 * 1024
                        or installed and (info.st_nlink != 1 or info.st_uid != expected_owner
                                          or info.st_mode & 0o022)):
                    raise ValueError(f"untrusted runtime file: {rel}")
                with os.fdopen(os.dup(fd), "rb") as stream:
                    data = stream.read(2 * 1024 * 1024 + 1)
            finally:
                os.close(fd)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError(f"runtime source too large: {rel}")
            paths[rel.as_posix()] = hashlib.sha256(data).digest()
    return paths


def verify_runtime(source_root, installed_root, *, role=None):
    """Ensure installed Python modules match the operator-reviewed checkout.

    This compares content, not commit provenance. Always select a trusted SHA
    and inspect local modifications before privileged deployment.
    """
    if role not in (None, "policy", "dns"):
        raise ValueError("invalid runtime role")
    source_root, installed_root = Path(source_root), Path(installed_root)
    if installed_root.is_symlink() or not installed_root.is_dir():
        raise ValueError("installed runtime root must be a directory")
    check_directory(installed_root)
    if role is not None:
        dns_admin = installed_root / "infra/edge/system_dns.py"
        if (dns_admin.is_file()) != (role == "dns"):
            raise ValueError("installed runtime role mismatch")
        if role == "dns":
            for name in ("system_dns.py", "firewall_guard.py"):
                rel = Path("infra/edge") / name
                src, dst = source_root / rel, installed_root / rel
                if dst.is_symlink() or not dst.is_file() or src.read_bytes() != dst.read_bytes():
                    raise ValueError(f"installed DNS administration source differs: {rel}")
                info = dst.stat()
                owner = 0 if os.geteuid() == 0 else os.geteuid()
                if info.st_uid != owner or info.st_mode & 0o022:
                    raise ValueError(f"unsafe installed DNS administration code: {rel}")
    source = _runtime_inventory(source_root, installed=False)
    installed = _runtime_inventory(installed_root, installed=True)
    if source != installed:
        delta = sorted(set(source) ^ set(installed))
        mismatched = sorted(x for x in set(source) & set(installed) if source[x] != installed[x])
        sample = (delta + mismatched)[:4]
        raise ValueError("installed Python runtime differs from checked-out code; "
                         "run an approved code-only upgrade first: " + ", ".join(sample))
    return len(installed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check')
    check.add_argument('role', choices=('remote', 'dns'))
    check.add_argument('--device-id', required=True)
    copy = sub.add_parser('copy-source')
    copy.add_argument('source', type=Path)
    copy.add_argument('destination', type=Path)
    verify = sub.add_parser('verify-runtime')
    verify.add_argument('source_root', type=Path)
    verify.add_argument('installed_root', type=Path)
    verify.add_argument('--role', choices=('policy', 'dns'))
    args = parser.parse_args(argv)
    try:
        if args.command == 'check':
            check_install(args.role, args.device_id)
        elif args.command == 'copy-source':
            copy_source(args.source, args.destination)
        else:
            count = verify_runtime(args.source_root, args.installed_root, role=args.role)
            print(f'VERIFIED_RUNTIME_FILES={count}')
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f'INSTALL_PREFLIGHT_ERROR: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
