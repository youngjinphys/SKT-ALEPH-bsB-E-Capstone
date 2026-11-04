"""Authenticated cloud OpenPhish -> GSB v5 query with durable CAS reservation.

No suspect URL visits, auto approvals, or signing. Private raw URLs remain in the
operator state while public API responses expose only aggregate metadata.
"""
from datetime import datetime,timedelta,timezone
import os,secrets
from cloud.state import StorageUnavailable
from policy_server import intel
from policy_server.console import ConsoleError,ConsoleConflict,_audit
from policy_server.evidence_store import adopt,_describe,_context,EvidenceConflict
from policy_server.refresh_bridge import RUN_ID

COOLDOWN=timedelta(minutes=15)
ERROR_COOLDOWN=timedelta(minutes=2)
MAX_RUNNING=timedelta(seconds=90)
LIMIT=15
STATE='collector-state.json'
PENDING='pending-intel.json'

def now():return datetime.now(timezone.utc)

def configured():
    key=os.getenv('SAFE_BROWSING_API_KEY','')
    return bool(os.getenv('ALEPH_OPENPHISH_SOURCE_ALLOWED','')=='true'
        and key and 1<=len(key)<=1024 and key.isascii()
        and all(33<=ord(c)<=126 for c in key))

def stored(work,name):
    path=work.service.workspace/name
    if not path.exists():return None
    from policy_server.console import _json_read
    return _json_read(path)

def state(work):
    info=stored(work,STATE)
    if info is None:return {'state':'IDLE','run':None,'requested_at':None,'error_code':None}
    if (type(info) is not dict or set(info)!={'state','run','requested_at','error_code'}
        or info['state'] not in ('IDLE','RUNNING','SUCCESS','ERROR')
        or type(info['run']) is not str or not RUN_ID.fullmatch(info['run'])
        or type(info['requested_at']) is not str
        or info['error_code'] not in (None,'UPSTREAM_ERROR')):
        raise ConsoleError('Invalid cloud collector state')
    intel.parse_time(info['requested_at'])
    return info

def status(work, instant=None):
    instant=instant or now()
    info=state(work)
    pending=stored(work,PENDING)
    latest=None
    if pending is not None:
        if type(pending) is not dict or set(pending)!={'run','fingerprint','verified_snapshot'}:
            raise ConsoleError('Invalid pending verified evidence')
        if type(pending['run']) is not str or not RUN_ID.fullmatch(pending['run']):
            raise ConsoleError('Invalid verified collector run')
        if pending['run']==info['run']:
            desc=_describe(pending['verified_snapshot'],instant)
            if desc['fingerprint']!=pending['fingerprint']:
                raise ConsoleError('Collector evidence fingerprint mismatch')
            if desc['importable']:
                latest={'run':pending['run'],'fingerprint':desc['fingerprint'],
                    'checked_at':desc['checked_at'],'verified':desc['verified'],
                    'review_proposals':desc['review_proposals'],
                    'unassigned_expressions':desc['unassigned_expressions']}
    context,_=_context(work.service)
    elapsed=instant-intel.parse_time(info['requested_at']) if info['requested_at'] else COOLDOWN
    ttl=(ERROR_COOLDOWN if info['state']=='ERROR' else COOLDOWN)-elapsed
    cooldown=max(0,int(ttl.total_seconds())+int(ttl.microseconds>0))
    actual=info['state']
    if actual=='RUNNING' and elapsed>MAX_RUNNING:
        actual='INTERRUPTED';cooldown=0
    if not configured():actual='NOT_CONFIGURED'
    elif info['state']=='SUCCESS' and latest is None:actual='EXPIRED'
    return {'state':actual,'run':info['run'],'latest':latest,
            'review_revision':work.service._review_revision(),
            'context_revision':context,'cooldown_seconds':cooldown,
            'message':('Provider key and authorized OpenPhish terms required'
                       if not configured() else None)}

def begin(work,data,instant=None):
    expected={'accept_openphish_terms','ack_url_disclosure','ack_noncommercial'}
    if type(data) is not dict or set(data)!=expected or any(v is not True for v in data.values()):
        raise ValueError('Explicit OpenPhish terms, Google disclosure and non-commercial acknowledgement required')
    if not configured():
        raise StorageUnavailable('Direct provider query is not configured for permitted use')
    instant=instant or now()
    current=state(work)
    if current['requested_at']:
        elapsed=instant-intel.parse_time(current['requested_at'])
        if current['state']=='RUNNING' and elapsed<=MAX_RUNNING:
            raise ConsoleConflict('OpenPhish/GSB verification is already running')
        delay=ERROR_COOLDOWN if current['state']=='ERROR' else COOLDOWN
        if elapsed<delay and current['state']!='RUNNING':
            raise ConsoleConflict('Provider cooldown in effect')
    run=instant.strftime('%Y%m%dT%H%M%SZ-')+secrets.token_hex(5)
    info={'state':'RUNNING','run':run,'requested_at':intel.iso(instant),'error_code':None}
    intel.write_json(work.service.workspace/STATE,info)
    _audit(work.service.workspace/'audit.jsonl','cloud_intel_refresh_reserved',run=run)
    return {'accepted':True,'run':run,'state':'RUNNING'}

def query(*,fetch=None,instant=None):
    if not configured():raise StorageUnavailable('Provider key missing')
    fetch=fetch or intel.get_https;instant=instant or now()
    feed=fetch(intel.OPENPHISH,limit=intel.MAX_FEED_BYTES)
    collected=intel.collect_urls(feed,source='openphish',limit=LIMIT,fetched_at=instant)
    result=intel.verify_collected(collected,os.environ['SAFE_BROWSING_API_KEY'],
                                  checked_at=instant,fetch=fetch)
    intel.review_template(result)
    return result

def finish(work,run,verified=None,instant=None):
    current=state(work)
    if current['state']!='RUNNING' or current['run']!=run:
        raise ConsoleConflict('Collector run changed before completion')
    if verified is None:
        updated={**current,'state':'ERROR','error_code':'UPSTREAM_ERROR'}
    else:
        template=intel.review_template(verified)
        desc=_describe(verified,instant or now())
        if not desc['importable']:
            raise ValueError('Verified evidence expired before persistence')
        intel.write_json(work.service.workspace/PENDING,{
            'run':run,'fingerprint':template['verification_sha256'],
            'verified_snapshot':verified})
        updated={**current,'state':'SUCCESS','error_code':None}
    intel.write_json(work.service.workspace/STATE,updated)
    _audit(work.service.workspace/'audit.jsonl','cloud_intel_refresh_finished',
           run=run,result=updated['state'])
    return {'accepted':True,'state':updated['state'],'run':run,
            'importable':verified is not None,'signed':False,'published':False}

def import_latest(work,data):
    expected={'run','fingerprint','review_revision','context_revision','confirm'}
    if type(data) is not dict or set(data)!=expected or data['confirm']!='IMPORT_VERIFIED':
        raise ValueError('Explicit run-bound evidence import required')
    latest=status(work)['latest']
    if (latest is None or data['run']!=latest['run']
            or data['fingerprint']!=latest['fingerprint']):
        raise ConsoleConflict('Collector run changed or expired')
    context,_=_context(work.service)
    if data['review_revision']!=work.service._review_revision() or data['context_revision']!=context:
        raise ConsoleConflict('Review or evidence context changed; reload')
    pending=stored(work,PENDING)
    try:
        result=adopt(work.service,pending['verified_snapshot'],
                     data['fingerprint'],context_revision=data['context_revision'],
                     review_revision=data['review_revision'])
    except EvidenceConflict as error:
        raise ConsoleConflict(str(error)) from error
    if result['imported']:
        _audit(work.service.workspace/'audit.jsonl','cloud_collector_evidence_imported',
               run=data['run'],fingerprint=data['fingerprint'][:16],reviews_reset=True)
    return {**result,'run':data['run']}
