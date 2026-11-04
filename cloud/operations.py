"""Small cloud-only imports; enforcement and policy signing remain independent."""
from datetime import datetime,timezone
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from aleph_policy_sync.snapshot import canonical,device_id,public_key_id,verify_envelope
from policy_server import intel
from policy_server.console import _audit

def preview_trust(work,data):
    if set(data)!={'role','public_key'} or data['role'] not in ('policy','node'):
        raise ValueError('Public key and explicit role required')
    pem=data['public_key']
    if not isinstance(pem,str) or len(pem)>4096 or 'PRIVATE KEY' in pem:
        raise ValueError('Only Ed25519 public keys are accepted')
    key=serialization.load_pem_public_key(pem.encode())
    if not isinstance(key,Ed25519PublicKey):raise ValueError('Ed25519 public key required')
    fingerprint=public_key_id(key)
    folder='policy-trust' if data['role']=='policy' else 'node-trust'
    other='node-trust' if folder=='policy-trust' else 'policy-trust'
    if (work.root/other/(fingerprint+'.pem')).exists():
        raise ValueError('Policy signing and node reporting must use independent keys')
    return {'role':data['role'],'key_id':fingerprint,'trusted':(work.root/folder/(fingerprint+'.pem')).exists()}

def trust_key(work,data):
    if set(data) not in ({'role','public_key','confirm'},{'role','public_key','confirm','expected_key_id'}) or data['confirm']!='TRUST_PUBLIC_KEY':
        raise ValueError('Explicit public-key trust acknowledgement required')
    preview=preview_trust(work,{'role':data['role'],'public_key':data['public_key']})
    fingerprint=preview['key_id']
    if 'expected_key_id' in data and data['expected_key_id']!=fingerprint:
        raise ValueError('Public key differs from previewed fingerprint')
    key=serialization.load_pem_public_key(data['public_key'].encode())
    folder='policy-trust' if data['role']=='policy' else 'node-trust'
    target=work.root/folder/(fingerprint+'.pem')
    value=key.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    if target.exists() and target.read_text()!=value:raise ValueError('Pinned trust key cannot be replaced')
    target.write_text(value);target.chmod(0o600)
    _audit(work.service.workspace/'audit.jsonl','cloud_public_key_trusted',key_id=fingerprint,role=data['role'])
    return {'key_id':fingerprint,'role':data['role'],'trusted':True}

def preview_evidence(work,data):
    if set(data)!={'verified'}:raise ValueError('One verified evidence snapshot is required')
    from policy_server.evidence_store import preview
    return preview(work.service,data['verified'])

def import_evidence(work,data):
    if set(data)!={'verified','confirm','context_revision','fingerprint'} or data['confirm']!='IMPORT_VERIFIED':
        raise ValueError('Preview-bound verified-evidence import required')
    from policy_server.evidence_store import adopt, EvidenceConflict
    from policy_server.console import ConsoleConflict
    try:
        result=adopt(work.service,data['verified'],data['fingerprint'],context_revision=data['context_revision'])
    except EvidenceConflict as exc:
        raise ConsoleConflict(str(exc)) from exc
    if result['imported']:
        _audit(work.service.workspace/'audit.jsonl','cloud_verified_evidence_imported',fingerprint=result['fingerprint'])
    return result

def publish(work,data,*,preview=False):
    if set(data)!={'device_id','envelope','expected_sequence','ack_withdrawals','ack_key_rotation'}:raise ValueError('Publication requires exact confirmation fields')
    device=device_id(data['device_id'])
    if type(data['expected_sequence']) is not int or data['expected_sequence']<0 or type(data['ack_withdrawals']) is not bool or type(data['ack_key_rotation']) is not bool:raise ValueError('Invalid publication confirmation')
    raw=canonical(data['envelope'])
    if len(raw)>2*1024*1024:raise ValueError('Policy envelope too large')
    now=datetime.now(timezone.utc)
    payload,parsed=verify_envelope(raw,expected_device=device,trust_dir=work.root/'policy-trust',now=now)
    target=work.root/'feed'/device/'current.json'
    before={};oldseq=0;oldkey=None
    if target.exists():
        older=target.read_bytes()
        prior,policy=verify_envelope(older,expected_device=device,trust_dir=work.root/'policy-trust',now=now,allow_expired=True)
        oldseq=prior['sequence'];oldkey=json.loads(older)['key_id']
        if parsed.issued_at <= policy.issued_at:raise ValueError('New policy issuance must be later than the published policy')
        before={r.domain:min(r.expires_at,policy.expires_at) for r in policy.rules if r.decision=='BLOCK' and r.approved and min(r.expires_at,policy.expires_at)>now}
    if oldseq!=data['expected_sequence']:
        from policy_server.console import ConsoleConflict
        raise ConsoleConflict('Published sequence changed; inspect and retry with current sequence')
    if payload['sequence']<=oldseq:raise ValueError('Policy sequence must increase monotonically')
    if not preview and oldkey is not None and oldkey!=data['envelope']['key_id'] and not data['ack_key_rotation']:raise ValueError('Signer rotation requires explicit acknowledgement')
    after={r.domain:min(r.expires_at,parsed.expires_at) for r in parsed.rules if r.decision=='BLOCK' and r.approved and min(r.expires_at,parsed.expires_at)>now}
    withdrawals=sorted(before.keys()-after.keys())
    shortened=sorted(d for d in before.keys() & after.keys() if after[d]<before[d])
    if not preview and (withdrawals or shortened) and not data['ack_withdrawals']:raise ValueError('Active block withdrawal or shorter lifetime requires acknowledgement')
    if preview:
        return {'preview':True,'published':False,'device':device,'sequence':payload['sequence'],
                'expected_sequence':oldseq,'policy_sha256':parsed.digest,'key_id':data['envelope']['key_id'],
                'added_count':len(after.keys()-before.keys()),'withdrawn_count':len(withdrawals),
                'shortened_count':len(shortened),'requires_withdrawals':bool(withdrawals or shortened),
                'requires_key_rotation':oldkey is not None and oldkey!=data['envelope']['key_id'],
                'expires_at':payload['valid_until'],'dns_applied':None}
    target.parent.mkdir(mode=0o700,exist_ok=True);target.write_bytes(raw);target.chmod(0o600)
    _audit(work.service.workspace/'audit.jsonl','cloud_signed_policy_published',device=device,sequence=payload['sequence'],sha256=parsed.digest)
    return {'published':True,'device':device,'sequence':payload['sequence'],'policy_sha256':parsed.digest,'withdrawn_count':len(withdrawals),'shortened_count':len(shortened),'dns_applied':None}
