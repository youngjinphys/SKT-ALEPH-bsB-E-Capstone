"""Same-project Vercel ASGI adapter, separate from the privileged DNS process."""
import json,os,re
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from .state import get_store,materialize,validate_state,Conflict,StorageUnavailable,MAX_STATE,MAX_FILES
from .storage_health import storage_health
from .security import require_operator,same_origin
from .operations import trust_key,preview_trust,import_evidence,preview_evidence,publish
from .assets import assets
from .enrollment import preview_enrollment,enroll
from policy_server import intel
from policy_server.console import ConsoleConflict,_audit
from policy_server.nodes import NodeConflict
from aleph_policy_sync.snapshot import device_id,verify_envelope,strict_load
from aleph_policy_sync.telemetry import MAX_REPORT_BYTES

app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def secure_headers(request,call_next):
    reply=await call_next(request)
    reply.headers['Cache-Control']='private, no-store, max-age=0'
    reply.headers['X-Content-Type-Options']='nosniff'
    reply.headers['Referrer-Policy']='no-referrer'
    reply.headers['X-Frame-Options']='DENY'
    reply.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    reply.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'"
    return reply

@app.exception_handler(HTTPException)
async def http_error(request,exc):return JSONResponse({'error':str(exc.detail)},status_code=exc.status_code)

@app.get('/dashboard',response_class=HTMLResponse)
def dashboard():return assets()[0]

@app.get('/dashboard/assets/{name}')
def static_asset(name:str):
    if name=='console.css':return Response(assets()[1],media_type='text/css')
    if name=='console.js':return Response(assets()[2],media_type='application/javascript')
    raise HTTPException(404,'Unknown asset')

async def read_json(request,limit=65536):
    if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':raise HTTPException(415,'JSON required')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>limit:raise HTTPException(413,'Request too large')
    try:value=strict_load(bytes(raw),limit=limit)
    except (ValueError,UnicodeError):raise HTTPException(400,'Invalid JSON') from None
    if type(value) is not dict:raise HTTPException(400,'JSON object required')
    return value,bytes(raw)

def transact(operation,write=False,*,actor=None,action=None):
    try:
        store=get_store();snapshot=store.load()
        with materialize(snapshot['state']) as work:
            result=operation(work)
            if write and actor is not None:
                # Bind server-verified identity to the same CAS commit as the
                # mutation. Never use the user-editable reviewer name as auth.
                _audit(work.service.workspace/'audit.jsonl','cloud_operator_committed',
                       actor=actor,action=action,state_revision=snapshot['revision']+1,
                       reference=action+' · '+actor)
            revision=store.save(snapshot['revision'],work.export()) if write else snapshot['revision']
        if isinstance(result,Response):response=result
        else:response=JSONResponse(result)
        response.headers['X-Aleph-State-Revision']=str(revision)
        return response
    except (Conflict,ConsoleConflict,NodeConflict) as exc:raise HTTPException(409,str(exc)[:180]) from None
    except StorageUnavailable as exc:raise HTTPException(503,str(exc)[:180]) from None
    except FileNotFoundError:raise HTTPException(404,'Artifact not found') from None
    except (ValueError,TypeError,KeyError) as exc:raise HTTPException(422,str(exc)[:180]) from None
    except OSError:raise HTTPException(503,'Workspace operation failed') from None

def inspect_storage():
    """Inspect metadata without materializing or parsing private evidence files."""
    try:
        snapshot=get_store().load()
        validate_state(snapshot['state'])
        result=storage_health(snapshot['state'],max_bytes=MAX_STATE,max_files=MAX_FILES)
        return JSONResponse({**result,'revision':snapshot['revision']},
                            headers={'X-Aleph-State-Revision':str(snapshot['revision'])})
    except (StorageUnavailable,OSError,ValueError,KeyError,TypeError):
        # An outage must never look like an empty, healthy snapshot.
        raise HTTPException(503,'Cannot verify durable storage capacity') from None

READS={'analytics':'analytics','overview':'overview','reviews':'reviews','reviews/reset-context':'reset_context','drafts':'drafts','engine':'engine_config','nodes':'node_states','audit':'audit'}
WRITES={'reviews/save':'update_review','reviews/reset':'reset_reviews','build':'build','engine':'configure_engine','evaluate':'evaluate','nodes/register':'register_node','nodes/remove':'unregister_node','nodes/unregister':'unregister_node'}

@app.api_route('/api/ops/test-auth', methods=['GET','POST'])
async def test_auth(request:Request):
    from . import pin_auth
    if request.method == 'GET':
        cfg = pin_auth.config()
        return JSONResponse({'enabled': cfg is not None, 'additionalCodeRequired': bool(cfg and cfg.extra_hash),
                             'authenticated': bool(await run_in_threadpool(pin_auth.identity, request))})
    same_origin(request)
    body, _ = await read_json(request, 1024)
    if body.get('action') == 'logout':
        # If revocation fails, retain the cookie so the user can retry. Do not
        # claim server-side logout succeeded after merely hiding the dashboard.
        await run_in_threadpool(pin_auth.logout, request)
        response = JSONResponse({'ok': True})
        pin_auth.cookie(response)
        return response
    if body.get('action') != 'login':
        raise HTTPException(400, 'Invalid action')
    token, seconds = await run_in_threadpool(pin_auth.login, body)
    response = JSONResponse({'ok': True, 'expiresIn': seconds})
    pin_auth.cookie(response, token, seconds)
    return response

@app.api_route('/api/ops/{path:path}',methods=['GET','POST'])
async def control(path:str,request:Request):
    if request.method=='POST':same_origin(request)
    email=await run_in_threadpool(require_operator,request)
    if request.method=='GET' and path=='session':
        # Authentication must not depend on the policy database or evidence files.
        return JSONResponse({'authorized':True,'email':email})
    if request.method=='GET' and path=='capabilities':
        # Static capabilities are independent of DB health, but not operator auth.
        return JSONResponse({'mode':'cloud','direct_refresh':False,'evidence_upload':True,
                             'signed_publication':True,'independent_signer':True,
                             'storage_diagnostics':True})
    if request.method=='GET' and path=='cloud/storage':
        return await run_in_threadpool(inspect_storage)
    if not re.fullmatch(r'[a-zA-Z0-9_./-]{1,180}',path) or '..' in path:raise HTTPException(404,'Unknown operation')
    if request.method=='GET':
        def read(work):
            if path in READS:return getattr(work.service,READS[path])()
            if path=='deployment':return work.service.deployment(include_rules=True)
            selected=re.fullmatch(r'deployment/([A-Za-z0-9][A-Za-z0-9_.-]{0,63})',path)
            if selected:return work.service.deployment(include_rules=True,device=selected[1])
            if path=='intel':return {'state':'EXTERNAL_COLLECTOR','latest':None,'review_revision':None,'message':'별도 수집기에서 검증한 파일을 미리보기 후 가져옵니다.'}
            if path=='cloud/trust':return {name:[x.stem for x in sorted((work.root/name).glob('*.pem'))] for name in ('policy-trust','node-trust')}
            match=re.fullmatch(r'drafts/(policy-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}\.json)/(download|impact)',path)
            if match:
                name,action=match.groups()
                if action=='impact':return work.service.draft_impact(name)
                return Response(work.service.download(name),media_type='application/json',headers={'Content-Disposition':'attachment; filename="'+name+'"'})
            raise HTTPException(404,'Unknown operation')
        return await run_in_threadpool(transact,read)
    body,_=await read_json(request,4*1024*1024 if path.startswith('cloud/') else 65536)
    def write(work):
        if path=='build' and 'review_set_revision' not in body:raise ConsoleConflict('Reload the draft review summary before building')
        if path in WRITES:return getattr(work.service,WRITES[path])(body)
        if path=='cloud/enroll/preview':return preview_enrollment(work,body)
        if path=='cloud/enroll':return enroll(work,body)
        if path=='cloud/trust/preview':return preview_trust(work,body)
        if path=='cloud/trust':
            if 'expected_key_id' not in body:raise ValueError('Inspect public-key fingerprint before trust registration')
            return trust_key(work,body)
        if path=='cloud/evidence/preview':return preview_evidence(work,body)
        if path=='cloud/evidence':return import_evidence(work,body)
        if path=='cloud/publish/preview':return publish(work,body,preview=True)
        if path=='cloud/publish':return publish(work,body)
        if path in ('intel/refresh','intel/adopt','intel/import'):raise HTTPException(503,'이 클라우드 관제는 외부 수집기를 사용합니다. 검증 파일을 미리보기한 뒤 가져오세요.')
        raise HTTPException(404,'Unknown operation')
    return await run_in_threadpool(transact,write,path not in ('evaluate','cloud/evidence/preview','cloud/publish/preview','cloud/trust/preview','cloud/enroll/preview'),actor=email,action=path)

@app.post('/v1/nodes/report')
async def receive_report(request:Request):
    if request.headers.get('origin') or request.headers.get('authorization'):raise HTTPException(403,'Only signed machine reports are accepted')
    report,raw=await read_json(request,MAX_REPORT_BYTES)
    # Reject malformed public traffic before allocating a durable DB workspace.
    if set(report)!={'payload','key_id','signature'} or type(report['payload']) is not dict:
        raise HTTPException(422,'Invalid signed node report envelope')
    return await run_in_threadpool(transact,lambda w:w.service.receive_node_report(raw),True)

@app.get('/v1/policies/{device}/current.json')
async def current_policy(device:str):
    try:device=device_id(device)
    except ValueError:raise HTTPException(404,'Unknown node') from None
    def read(work):
        raw=(work.root/'feed'/device/'current.json').read_bytes()
        verify_envelope(raw,expected_device=device,trust_dir=work.root/'policy-trust')
        return Response(raw,media_type='application/json')
    return await run_in_threadpool(transact,read)
