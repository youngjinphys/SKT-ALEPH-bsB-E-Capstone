"""Atomic operator-confirmed public descriptor enrollment. Never stores private keys."""
from aleph_policy_sync.enrollment import validate_enrollment
from policy_server.console import ConsoleConflict
from .operations import preview_trust,trust_key


def preview_enrollment(work,data):
    if type(data) is not dict or set(data)!={'enrollment'}:
        raise ValueError('One public node enrollment descriptor is required')
    node=validate_enrollment(data['enrollment'])
    preview_trust(work,{'role':'node','public_key':node['public_key']})
    registry=work.service.nodes._registry()
    if node['key_id'] in registry['retired_key_ids']:
        raise ValueError('Retired node key cannot be enrolled; rotate the device key')
    identity={key:node[key] for key in ('device_id','dns_address','label','key_id')}
    for old in registry['nodes']:
        if old['device_id']==node['device_id'] or old['key_id']==node['key_id']:
            if old!=identity:
                raise ConsoleConflict('Device or key is already bound to another identity; no replacement performed')
            return {**identity,'already_registered':True,'proof_of_possession':True}
    return {**identity,'already_registered':False,'proof_of_possession':True}


def enroll(work,data):
    if (type(data) is not dict or set(data)!={'enrollment','expected_key_id','confirm'}
            or data['confirm']!='ENROLL_NODE'):
        raise ValueError('Explicit ENROLL_NODE acknowledgement is required')
    preview=preview_enrollment(work,{'enrollment':data['enrollment']})
    if data['expected_key_id']!=preview['key_id']:
        raise ConsoleConflict('Enrollment differs from previewed fingerprint')
    if preview['already_registered']:
        return {**preview,'registered':True}
    trust_key(work,{'role':'node','public_key':data['enrollment']['payload']['public_key'],
                    'expected_key_id':preview['key_id'],'confirm':'TRUST_PUBLIC_KEY'})
    work.service.register_node({k:preview[k] for k in ('device_id','dns_address','label','key_id')})
    return {**preview,'registered':True,'state':'NO_REPORT'}
