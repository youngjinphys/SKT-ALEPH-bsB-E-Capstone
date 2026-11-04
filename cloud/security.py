"""Reuse verified Supabase sessions; Google login alone does not authorize DNS."""
import os,re
from urllib.error import HTTPError,URLError
from fastapi import HTTPException,Request
from .state import remote_json

ACCESS_COOKIE='__Host-capstone_at'
def operator_allowed(email,env=None):
    env=os.environ if env is None else env
    allow={x.strip().lower() for x in env.get('CAPSTONE_OPS_ALLOWED_EMAILS','').split(',') if x.strip()}
    return isinstance(email,str) and bool(allow) and email.lower() in allow

def require_operator(request:Request):
    from .pin_auth import identity
    test_identity = identity(request)
    if test_identity:
        return test_identity
    token=request.cookies.get(ACCESS_COOKIE,'')
    if not re.fullmatch(r'[A-Za-z0-9._~-]{13,8192}',token):raise HTTPException(401,'Google 로그인 세션이 필요합니다.')
    url=os.getenv('SUPABASE_URL','');key=os.getenv('SUPABASE_PUBLISHABLE_KEY','')
    if not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',url) or not key:raise HTTPException(503,'인증 공급자 설정이 필요합니다.')
    try:who=remote_json(url+'/auth/v1/user',{'apikey':key,'Authorization':'Bearer '+token,'Accept':'application/json'},limit=65536)
    except HTTPError as exc:
        if exc.code in (401,403):raise HTTPException(401,'세션이 만료되었습니다.') from None
        raise HTTPException(503,'인증 공급자를 확인할 수 없습니다.') from None
    except (URLError,OSError,ValueError):raise HTTPException(503,'인증 공급자를 확인할 수 없습니다.') from None
    if not isinstance(who,dict) or not who.get('id') or not (who.get('email_confirmed_at') or who.get('confirmed_at')):raise HTTPException(403,'확인된 계정이 필요합니다.')
    if not operator_allowed(who.get('email')):raise HTTPException(403,'이 계정에는 DNS 관제 운영자 권한이 없습니다.')
    return who['email']

def same_origin(request):
    origin=os.getenv('CAPSTONE_SITE_ORIGIN','https://skt-aleph-capstone.vercel.app')
    if request.headers.get('origin')!=origin or request.headers.get('sec-fetch-site') not in (None,'same-origin','none'):
        raise HTTPException(403,'Cross-origin operation rejected')
