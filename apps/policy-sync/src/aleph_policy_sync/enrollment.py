"""Public-only, self-signed onboarding descriptor; operator approval is mandatory.

A self-signature demonstrates possession, not trusted ownership. The operator
must compare the fingerprint against the actual node over a trusted channel.
"""
import argparse
import base64
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .snapshot import canonical,device_id,public_key_id,load_private_key
from .telemetry import private_ipv4


def validate_enrollment(value):
    if type(value) is not dict or set(value)!={'payload','key_id','signature'}:
        raise ValueError('Invalid public enrollment descriptor')
    p=value['payload']
    if type(p) is not dict or set(p)!={'format','type','device_id','dns_address','label','public_key'}:
        raise ValueError('Invalid enrollment identity fields')
    if type(p['format']) is not int or p['format']!=1 or p['type']!='aleph-node-enrollment':
        raise ValueError('Unsupported enrollment format')
    device_id(p['device_id']);private_ipv4(p['dns_address'])
    label=p['label']
    if not isinstance(label,str) or not 2<=len(label)<=64 or label!=label.strip() or any(ord(x)<32 or ord(x)==127 for x in label):
        raise ValueError('Invalid node display name')
    pem=p['public_key']
    if not isinstance(pem,str) or len(pem)>1024 or 'PRIVATE' in pem or not pem.startswith('-----BEGIN PUBLIC KEY-----'):
        raise ValueError('Only an Ed25519 public key is accepted')
    key=serialization.load_pem_public_key(pem.encode('ascii'))
    if not isinstance(key,Ed25519PublicKey) or value['key_id']!=public_key_id(key):
        raise ValueError('Enrollment public-key fingerprint mismatch')
    sig=value['signature']
    if not isinstance(sig,str) or not re.fullmatch('[A-Za-z0-9_-]{86}',sig):
        raise ValueError('Invalid enrollment signature')
    try:key.verify(base64.urlsafe_b64decode(sig+'=='),canonical(p))
    except InvalidSignature as exc:raise ValueError('Enrollment signature verification failed') from exc
    return {k:p[k] for k in ('device_id','dns_address','label','public_key')} | {'key_id':value['key_id']}


def make_enrollment(key,device,address,label):
    pem=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
    payload={'format':1,'type':'aleph-node-enrollment','device_id':device,'dns_address':address,'label':label,'public_key':pem}
    result={'payload':payload,'key_id':public_key_id(key.public_key()),'signature':base64.urlsafe_b64encode(key.sign(canonical(payload))).decode().rstrip('=')}
    validate_enrollment(result)
    return result


def main():
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-key',required=True,type=Path)
    parser.add_argument('--device-id',required=True)
    parser.add_argument('--listen-ip',required=True)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    print(json.dumps(make_enrollment(load_private_key(args.private_key),args.device_id,args.listen_ip,args.label),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
