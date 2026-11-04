#!/usr/bin/env python3
"""Prepare a real local DNS node for this project's Vercel dashboard.

Default is read-only preflight. --apply creates/reuses the DEVICE key locally,
installs/configures outbound reporting, and writes a public enrollment JSON.
Never changes DHCP, DNS policy, firewall, upstream resolver or replay counters.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
for component in ('dns-agent','policy-sync'):
    sys.path.insert(0,str(ROOT/'apps'/component/'src'))
from aleph_policy_sync.snapshot import load_private_key,public_key_id,device_id
from aleph_policy_sync.telemetry import private_ipv4,probe_upstream_ipv4
from aleph_policy_sync.system_metrics import interface_name
from aleph_policy_sync.enrollment import make_enrollment
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

URL='https://skt-aleph-capstone.vercel.app/v1/nodes/report'
BASE=Path('/opt/aleph-policy-code')
SECRETS=Path('/root/aleph-ops-secrets')

def command(args,**kwargs):
    return subprocess.run(args,check=True,text=True,timeout=45,**kwargs)

def secure_directory(path):
    spec=importlib.util.spec_from_file_location('checks',ROOT/'scripts/deploy/install_checks.py')
    checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
    checks.check_directory(path)
    return checks

def atomic(path,data,mode=0o600):
    secure_directory(path.parent)
    if path.exists() or path.is_symlink():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_nlink!=1 or info.st_mode & 0o022:
            raise ValueError('Unsafe existing output path: '+str(path))
    fd,tmp=tempfile.mkstemp(prefix='.ops-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),mode);f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device-id',required=True)
    p.add_argument('--listen-ip',required=True)
    p.add_argument('--interface',required=True)
    p.add_argument('--label',default='ALEPH DNS node')
    p.add_argument('--probe-upstream')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args(argv)
    device_id(a.device_id);private_ipv4(a.listen_ip);interface_name(a.interface)
    probe_upstream_ipv4(a.probe_upstream,a.listen_ip)
    if not 2<=len(a.label)<=64 or a.label!=a.label.strip() or any(ord(x)<32 or ord(x)==127 for x in a.label):
        raise ValueError('Invalid display label')
    if os.geteuid()!=0:
        raise ValueError('Run this preflight with sudo; it never exports the device private key')
    checks=secure_directory(BASE)
    checks.verify_runtime(ROOT,BASE,role='dns')
    ip='/usr/sbin/ip' if Path('/usr/sbin/ip').exists() else '/usr/bin/ip'
    addresses=json.loads(command([ip,'-j','-4','address','show','dev',a.interface],capture_output=True).stdout)
    if not any(info.get('local')==a.listen_ip for dev in addresses for info in dev.get('addr_info',[])):
        raise ValueError('The supplied address is not assigned to the supplied local interface')
    installed=Path('/etc/systemd/system/aleph-ops-collect.service').is_file()
    if installed:
        units=command(['/usr/bin/systemctl','cat','aleph-ops-collect.service','aleph-ops-send.service'],capture_output=True).stdout
        import re
        for flag,wanted in (('device-id',a.device_id),('listen-ip',a.listen_ip)):
            existing=re.findall(r'--'+flag+r'\s+([^\s]+)',units)
            if not existing or any(x!=wanted for x in existing):
                raise ValueError('Existing device identity differs; do not silently replace registered identity')
        if not Path('/etc/aleph-ops/status.pem').is_file():
            raise ValueError('Existing telemetry key is missing; do not regenerate or reset counters')
    print('Device:',a.device_id,'DNS:',a.listen_ip,'NIC:',a.interface)
    print('Report endpoint:',URL)
    print('Metrics: host counters + selected NIC; fixed example.org UDP/TCP quality probes')
    if not a.apply:
        print('Preview only. Repeat this command with --apply after checking the device identity.')
        return 0
    secure_directory(SECRETS);SECRETS.mkdir(mode=0o700,exist_ok=True)
    if SECRETS.stat().st_mode & 0o077:
        raise ValueError('Private-key directory must have mode 0700')
    key_path=Path('/etc/aleph-ops/status.pem') if installed else SECRETS/'device-status.pem'
    if not key_path.exists() and not key_path.is_symlink():
        key=Ed25519PrivateKey.generate()
        raw=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        fd=os.open(key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    key=load_private_key(key_path)
    public=SECRETS/'device-status.pub'
    atomic(public,key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo),0o644)
    keyid=public_key_id(key.public_key())
    if not installed:
        args=['/usr/bin/bash',str(ROOT/'scripts/deploy/install-dns-telemetry.sh'),
              '--device-id',a.device_id,'--listen-ip',a.listen_ip,'--report-url',URL,
              '--private-key',str(key_path),'--public-key',str(public),
              '--metrics-interface',a.interface,'--quality-probes','--apply']
        if a.probe_upstream:args+=['--probe-upstream',a.probe_upstream]
        command(args)
    else:
        command(['/usr/bin/systemctl','stop','aleph-ops-collect.timer','aleph-ops-send.timer','aleph-ops-collect.service','aleph-ops-send.service'])
        # Both commands contain only validated tokens and fixed paths, not labels.
        common='/usr/bin/python3 -B -m aleph_policy_sync.telemetry '
        collect=(common+'collect --device-id '+a.device_id+' --listen-ip '+a.listen_ip+
                 ' --private-key /etc/aleph-ops/status.pem --state-dir /var/lib/aleph-ops-root'+
                 ' --outbox-dir /var/lib/aleph-ops-outbox --sender-group aleph-ops-sender'+
                 ' --metrics-interface '+a.interface+' --quality-probes')
        if a.probe_upstream:collect+=' --probe-upstream '+a.probe_upstream
        if '--cache-metrics' in units:collect+=' --cache-metrics'
        send=(common+'send --url '+URL+' --device-id '+a.device_id+' --key-id '+keyid+
              ' --trust-dir /etc/aleph-ops/trust --report-file /var/lib/aleph-ops-outbox/report.json')
        for service,line in (('collect',collect),('send',send)):
            folder=Path('/etc/systemd/system')/('aleph-ops-'+service+'.service.d')
            secure_directory(folder);folder.mkdir(mode=0o755,exist_ok=True)
            atomic(folder/'90-dashboard.conf',('[Service]\nExecStart=\nExecStart='+line+'\n').encode(),0o644)
        command(['/usr/bin/systemctl','daemon-reload'])
        command(['/usr/bin/systemctl','enable','--now','aleph-ops-collect.timer','aleph-ops-send.timer'])
    descriptor=make_enrollment(key,a.device_id,a.listen_ip,a.label)
    output=SECRETS/'node-enrollment.json'
    atomic(output,(json.dumps(descriptor,indent=2,ensure_ascii=False)+'\n').encode())
    print('Public enrollment file:',output)
    print('Compare this public fingerprint in the dashboard:',keyid)
    print('Open https://skt-aleph-capstone.vercel.app/dashboard -> 배포 현황 -> 노드 연결 파일 등록')
    print('Upload ONLY node-enrollment.json; never upload *.pem private keys.')
    print('After registration: sudo systemctl start aleph-ops-collect.service aleph-ops-send.service')
    print('No DHCP, firewall, DNS policy or replay counter was reset.')
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print('NODE_CONNECT_ERROR: '+str(exc)[:250],file=sys.stderr);raise SystemExit(2)
