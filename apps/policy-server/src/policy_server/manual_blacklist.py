"""Operator-reviewed FQDN SUBTREE blocks, unsigned until independent signing."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os
from dns_agent.policy import domain_name,timestamp
from . import intel

MAX_RECORDS=150
FIELDS={'domain','reviewer','reason','expires_at','added_at','updated_at','acknowledge_subtree'}

def now():return datetime.now(timezone.utc)

def unsafe_boundary(domain):
    return intel.is_protected(domain)

def validate(entry,*,check_boundary=True):
    if type(entry) is not dict or set(entry)!=FIELDS:raise ValueError('Invalid manual FQDN record')
    domain=domain_name(entry['domain'])
    if domain!=entry['domain'] or (check_boundary and unsafe_boundary(domain)):
        raise ValueError('Protected, public-suffix or noncanonical FQDN')
    if (type(entry['reviewer']) is not str or not 2<=len(entry['reviewer'])<=80
       or type(entry['reason']) is not str or not 15<=len(entry['reason'])<=400
       or entry['acknowledge_subtree'] is not True):
        raise ValueError('Reviewer, detailed justification and SUBTREE acknowledgment required')
    if any(v!=v.strip() or any(ord(c)<32 or ord(c)==127 for c in v)
           for v in (entry['reviewer'],entry['reason'])):
        raise ValueError('Unsafe manual review text')
    added=timestamp(entry['added_at'],'added_at')
    changed=timestamp(entry['updated_at'],'updated_at')
    expiry=timestamp(entry['expires_at'],'expires_at')
    if changed<added or expiry<=added or expiry-added>timedelta(days=7,seconds=60):
        raise ValueError('Manual blacklist validity too long or inconsistent')
    return entry

def records(service):
    from .console import _json_read
    path=service.workspace/'manual-blacklist.json'
    if not path.exists():return {'format':1,'entries':[]}
    data=_json_read(path)
    if (type(data) is not dict or set(data)!={'format','entries'} or type(data['format']) is not int
        or data['format']!=1 or type(data['entries']) is not list or len(data['entries'])>MAX_RECORDS):
        raise ValueError('Invalid manual blacklist')
    names=set()
    for item in data['entries']:
        # Older records remain inspectable/removable after a boundary update.
        # New registrations and draft generation still enforce current safety.
        validate(item,check_boundary=False)
        if item['domain'] in names:raise ValueError('Duplicate manual FQDN')
        names.add(item['domain'])
    if data['entries']!=sorted(data['entries'],key=lambda x:x['domain']):
        raise ValueError('Unsorted manual blacklist')
    return data

def revision(value):
    from .console import _revision
    return _revision(value)

def list_rules(service,instant=None):
    data=records(service);instant=instant or now()
    return {'revision':revision(data),'scope':'SUBTREE','entries':[
        {**x,'expired':timestamp(x['expires_at'],'expires_at')<=instant,
         'unsafe_boundary':unsafe_boundary(x['domain'])}
        for x in data['entries']]}

def archive(service,item):
    """Retain the exact evidence preimage, never overwrite historical records."""
    from .console import _private_dir,_json_read
    validate(item,check_boundary=False)
    folder=service.workspace/'manual-evidence'
    try:relative=folder.resolve(strict=False).relative_to(intel.ROOT)
    except ValueError:pass
    else:
        if relative.parts[:2]!=('data','private'):
            raise ValueError('Private manual evidence must be outside the repository or in data/private/')
    folder.mkdir(mode=0o700,exist_ok=True)
    _private_dir(folder)
    path=folder/(revision(item)+'.json')
    raw=json.dumps(item,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()+b'\n'
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        existing=_json_read(path)
        if revision(existing)!=revision(item) or existing!=item:
            raise ValueError('Manual evidence archive mismatch')
        return
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(raw);output.flush();os.fsync(output.fileno())
        directory=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
    except BaseException:
        # A failed/partial archive never permits registry mutation. Leave the
        # artifact for inspection; a later mismatch fails closed as well.
        raise

def candidate(data,instant=None):
    expected={'domain','reviewer','reason','expires_at','acknowledge_subtree','expected_revision'}
    if type(data) is not dict or set(data)!=expected:raise ValueError('Exact manual FQDN fields required')
    instant=instant or now()
    item={'domain':domain_name(data['domain']),'reviewer':data['reviewer'],'reason':data['reason'],
          'expires_at':data['expires_at'],'added_at':intel.iso(instant),
          'updated_at':intel.iso(instant),'acknowledge_subtree':data['acknowledge_subtree']}
    validate(item)
    until=timestamp(item['expires_at'],'expires_at')
    if not instant+timedelta(minutes=5)<until<=instant+timedelta(days=7):
        raise ValueError('Manual expiry must be between 5 minutes and 7 days')
    key=data['expected_revision']
    if type(key) is not str or len(key)!=64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Bound manual FQDN revision required')
    return item

def preview(service,data):
    item=candidate(data)
    state=records(service);current=revision(state)
    if current!=data['expected_revision']:
        from .console import ConsoleConflict
        raise ConsoleConflict('Manual blacklist changed; reload before preview')
    return {'domain':item['domain'],'scope':'SUBTREE','expires_at':item['expires_at'],
            'reviewer':item['reviewer'],'reason':item['reason'],
            'replace_existing':any(x['domain']==item['domain'] for x in state['entries']),
            'expected_revision':current,'signed':False,'published':False,'enforcing':False}

def upsert(service,data):
    expected={'domain','reviewer','reason','expires_at','acknowledge_subtree','expected_revision','confirm'}
    if type(data) is not dict or set(data)!=expected or data['confirm']!='UPSERT_MANUAL_SUBTREE':
        raise ValueError('Explicit SUBTREE registration confirmation required')
    with service.locked():
        payload={k:v for k,v in data.items() if k!='confirm'}
        preview(service,payload)
        state=records(service);item=candidate(payload)
        prior=next((x for x in state['entries'] if x['domain']==item['domain']),None)
        if prior and timestamp(item['expires_at'],'expires_at')-timestamp(prior['added_at'],'added_at')<=timedelta(days=7):
            item['added_at']=prior['added_at']
        if prior is None and len(state['entries'])>=MAX_RECORDS:
            raise ValueError('Manual blacklist is full')
        if prior:archive(service,prior)
        archive(service,item)
        value={'format':1,'entries':sorted(
            [x for x in state['entries'] if x['domain']!=item['domain']]+[item],
            key=lambda x:x['domain'])}
        from .console import _audit
        intel.write_json(service.workspace/'manual-blacklist.json',value)
        _audit(service.workspace/'audit.jsonl','manual_subtree_block_saved',
               domain=item['domain'],revision=revision(value)[:16],
               expiry=item['expires_at'],replaced=bool(prior))
        return {'saved':True,'domain':item['domain'],'revision':revision(value),
                'replaced':bool(prior),'signed':False,'published':False}

def remove(service,data):
    if type(data) is not dict or set(data)!={'domain','expected_revision','confirm'} or data['confirm']!='REMOVE_MANUAL_BLOCK':
        raise ValueError('Explicit FQDN removal confirmation required')
    name=domain_name(data['domain'])
    with service.locked():
        state=records(service)
        if data['expected_revision']!=revision(state):
            from .console import ConsoleConflict
            raise ConsoleConflict('Manual blacklist changed; reload')
        if not any(x['domain']==name for x in state['entries']):
            raise ValueError('Manual FQDN not found')
        archive(service,next(x for x in state['entries'] if x['domain']==name))
        value={'format':1,'entries':[x for x in state['entries'] if x['domain']!=name]}
        from .console import _audit
        intel.write_json(service.workspace/'manual-blacklist.json',value)
        _audit(service.workspace/'audit.jsonl','manual_subtree_block_removed',
               domain=name,revision=revision(value)[:16])
        return {'removed':True,'domain':name,'revision':revision(value),'published':False}

def draft_rules(service,instant=None):
    instant=instant or now();items=records(service)['entries']
    fresh=[x for x in items if timestamp(x['expires_at'],'expires_at')>instant]
    for item in fresh:
        validate(item)
        archive(service,item)
    return ([{'domain':item['domain'],'decision':'BLOCK','scope':'SUBTREE',
              'approved':True,'expires_at':item['expires_at'],
              'evidence':'manual-review-v1:sha256:'+revision(item)} for item in fresh],
            len(items)-len(fresh))
