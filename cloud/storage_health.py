"""Read-only capacity diagnostics for the bounded, durable operations snapshot.

Counts are metadata only: never expose file names, URLs, JSON or key material.
This reports limits, not provider availability or free space on a physical disk.
"""
from datetime import datetime, timezone
import json

_GROUPS=('archives','drafts','publications','trust','audit','other')


def _group(path):
    if path.startswith('workspace/evidence-archive/'):
        return 'archives'
    if path.startswith('workspace/drafts/'):
        return 'drafts'
    if path.startswith('feed/'):
        return 'publications'
    if path.startswith(('policy-trust/','node-trust/')):
        return 'trust'
    if path.endswith('/audit.jsonl'):
        return 'audit'
    return 'other'


def storage_health(state, *, max_bytes, max_files):
    """Return bounded-snapshot headroom using exactly the store's JSON encoding.

    No pruning is performed. Archive removal or retention changes require their
    own reviewed export/backup workflow; telemetry replay counters must survive.
    """
    if (type(max_bytes) is not int or max_bytes<=0 or
            type(max_files) is not int or max_files<=0):
        raise ValueError('Positive storage limits required')
    if (type(state) is not dict or set(state)!={'format','files'} or
            type(state['format']) is not int or state['format']!=1 or
            type(state['files']) is not dict):
        raise ValueError('Invalid durable snapshot')
    groups={key:{'file_count':0,'content_bytes':0} for key in _GROUPS}
    for path,content in state['files'].items():
        if not isinstance(path,str) or not isinstance(content,str):
            raise ValueError('Invalid snapshot file')
        group=groups[_group(path)]
        group['file_count']+=1
        group['content_bytes']+=len(content.encode('utf-8'))
    # Keep this encoding aligned with cloud.state.validate_state; Unicode
    # escaping and JSON object overhead both count toward its 8 MiB limit.
    used=len(json.dumps(state,ensure_ascii=True).encode('utf-8'))
    count=len(state['files'])
    pressure=max(used/max_bytes,count/max_files)
    level='CRITICAL' if pressure>=.9 else 'WARNING' if pressure>=.75 else 'NORMAL'
    return {'state':level,'bytes_used':used,'bytes_limit':max_bytes,
            'file_count':count,'file_limit':max_files,'groups':groups,
            'pressure_percent':round(pressure*100,1),'automatic_cleanup':False,
            'observed_at':datetime.now(timezone.utc).isoformat()}
