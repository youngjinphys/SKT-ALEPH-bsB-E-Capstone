"""Narrow Sites-to-operations assertion verifier; never a browser credential.

The configured key decodes to 32 random bytes. Signed POST assertions are consumed
atomically in PostgreSQL before dispatch, including preview operations. Missing
replay storage fails closed. No production process-local replay cache exists.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
from fastapi import HTTPException
from .state import SupabaseStore, StorageUnavailable, Conflict

ASSERTION = 'x-aleph-sites-assertion'
SIGNATURE = 'x-aleph-sites-signature'
GET_PATHS = frozenset(('session','capabilities','cloud/storage','manual','analytics','overview','reviews','reviews/reset-context','drafts','engine','nodes','audit','deployment','intel','cloud/trust'))
POST_PATHS = frozenset(('manual/save','manual/remove','manual/preview','reviews/save','reviews/reset','build','engine','evaluate','nodes/register','nodes/remove','nodes/unregister','intel/refresh','intel/import','cloud/enroll/preview','cloud/enroll','cloud/trust/preview','cloud/trust','cloud/evidence/preview','cloud/evidence','cloud/publish/preview','cloud/publish'))

def allowed_path(method, path):
    if not path.startswith('/api/ops/'): return False
    path = path[len('/api/ops/'):]
    if method == 'POST': return path in POST_PATHS
    return method == 'GET' and (path in GET_PATHS or bool(re.fullmatch(r'deployment/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}|drafts/policy-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}\.json/(download|impact)', path)))

def present(request):
    return ASSERTION in request.headers or SIGNATURE in request.headers

def decode(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',value): raise ValueError('Invalid encoding')
    raw=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
    if base64.urlsafe_b64encode(raw).decode().rstrip('=') != value: raise ValueError('Noncanonical encoding')
    return raw

def consume_nonce(claims):
    nonce_hash=hashlib.sha256((claims['iss']+'\n'+claims['jti']).encode()).hexdigest()
    try:
        accepted=SupabaseStore().rpc('aleph_sites_consume_nonce',{'nonce_hash':nonce_hash,'expires_epoch':claims['exp']})
    except (StorageUnavailable, Conflict):
        raise HTTPException(503,'Sites replay protection unavailable') from None
    if accepted is not True: raise HTTPException(401,'Sites assertion already used or expired')

def verify(request, body):
    from .security import operator_allowed
    def deny(): raise HTTPException(401,'Invalid Sites assertion')
    origin=os.getenv('CAPSTONE_SITES_BRIDGE_ORIGIN','')
    secret=os.getenv('CAPSTONE_SITES_BRIDGE_SECRET','')
    if not re.fullmatch(r'https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.chatgpt\.site',origin):
        raise HTTPException(503,'Sites bridge is not configured')
    try:
        key=decode(secret)
        if len(key)!=32: raise ValueError()
    except ValueError: raise HTTPException(503,'Sites bridge is not configured') from None
    if request.headers.get('cookie') or request.headers.get('authorization'): deny()
    if any(len(request.headers.getlist(name))!=1 for name in (ASSERTION,SIGNATURE)): deny()
    encoded=request.headers[ASSERTION]; signature=request.headers[SIGNATURE]
    if len(encoded)>4096 or len(signature)!=43: deny()
    try:
        actual=decode(signature)
        if not hmac.compare_digest(actual,hmac.digest(key,encoded.encode('ascii'),'sha256')): deny()
        def unique(pairs):
            value={}
            for k,v in pairs:
                if k in value: raise ValueError()
                value[k]=v
            return value
        claims=json.loads(decode(encoded),object_pairs_hook=unique)
    except (ValueError,UnicodeError): deny()
    fields={'v','iss','aud','email','iat','exp','jti','method','path','body_sha256'}
    if type(claims) is not dict or set(claims)!=fields: deny()
    try:
        raw_path=request.scope.get('raw_path',b'').decode('ascii')
    except (UnicodeError, AttributeError): deny()
    now=time.time()
    if (type(claims['v']) is not int or claims['v']!=1 or claims['iss']!=origin or claims['aud']!='aleph-ops'
        or type(claims['iat']) is not int or type(claims['exp']) is not int
        or not 0<claims['exp']-claims['iat']<=30 or claims['iat']>now+5 or claims['exp']<=now
        or not isinstance(claims['jti'],str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',claims['jti'])
        or not isinstance(claims['email'],str) or len(claims['email'])>254
        or claims['method']!=request.method or claims['path']!=request.url.path
        or request.url.query or raw_path!=request.url.path
        or not allowed_path(request.method,request.url.path)
        or claims['body_sha256']!=hashlib.sha256(body).hexdigest()): deny()
    if request.method=='GET' and body: deny()
    if request.method=='POST' and (request.headers.get('origin')!=origin or request.headers.get('sec-fetch-site') not in (None,'same-origin')):
        raise HTTPException(403,'Cross-origin Sites operation rejected')
    if not operator_allowed(claims['email']): raise HTTPException(403,'이 계정에는 DNS 관제 운영자 권한이 없습니다.')
    if request.method=='POST': consume_nonce(claims)
    return claims['email']
