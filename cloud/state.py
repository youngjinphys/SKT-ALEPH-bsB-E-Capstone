"""Bounded durable compare-and-swap state with request-local materialization.

Filesystem locks protect only the temporary instance. The PostgreSQL revision is
what prevents cross-instance lost writes, including replay-counter regressions.
No production memory/disk fallback is permitted.
"""
from contextlib import contextmanager
from copy import deepcopy
import json,os,re,secrets,stat,tempfile,threading
from pathlib import Path,PurePosixPath
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from policy_server.console import ConsoleService

MAX_STATE=8*1024*1024
MAX_FILES=512
class Conflict(ValueError):pass
class StorageUnavailable(RuntimeError):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def remote_json(url,headers,data=None,limit=MAX_STATE+1024*1024):
    raw=None if data is None else json.dumps(data,ensure_ascii=True,allow_nan=False).encode()
    req=Request(url,data=raw,headers={**headers,**({'Content-Type':'application/json'} if raw is not None else {})})
    with build_opener(NoRedirect).open(req,timeout=12) as response:
        value=response.read(limit+1)
    if len(value)>limit:raise StorageUnavailable('Oversized upstream response')
    return json.loads(value)

def empty_state():return {'format':1,'files':{}}

def validate_state(state):
    if type(state) is not dict or set(state)!={'format','files'} or type(state['format']) is not int or state['format']!=1 or type(state['files']) is not dict:
        raise ValueError('Invalid cloud snapshot')
    if len(state['files'])>MAX_FILES:raise ValueError('Cloud snapshot file limit reached')
    for path,content in state['files'].items():
        if not isinstance(path,str) or not re.fullmatch(r'(workspace|feed|policy-trust|node-trust)/[A-Za-z0-9_./-]+',path):raise ValueError('Unsafe snapshot path')
        parts=tuple(path.split('/'))
        if any(x in ('.','..') or x.startswith('.') for x in parts) or '//' in path or path.endswith('/') or not path.endswith(('.json','.jsonl','.pem')):
            raise ValueError('Unsafe snapshot path')
        if not isinstance(content,str) or len(content.encode())>2*1024*1024:raise ValueError('Oversized snapshot file')
        if parts[0] in ('node-trust','policy-trust') and not re.fullmatch(r'[a-f0-9]{64}\.pem',parts[-1]):raise ValueError('Invalid trust-key name')
    if len(json.dumps(state,ensure_ascii=True).encode())>MAX_STATE:raise ValueError('Cloud snapshot capacity reached')
    return state

class MemoryStore:
    """Test fixture only: get_store never constructs this class."""
    def __init__(self):self.value={'revision':0,'state':empty_state()};self.lock=threading.RLock()
    def load(self):
        with self.lock:return deepcopy(self.value)
    def save(self,revision,state):
        validate_state(state)
        with self.lock:
            if self.value['revision']!=revision:raise Conflict('Concurrent update; reload and retry')
            self.value={'revision':revision+1,'state':deepcopy(state)}
            return revision+1

class SupabaseStore:
    def __init__(self):
        # Never confuse the public-site OAuth tenant with the independently
        # managed operations DB. In production, partial/missing DB configuration
        # fails closed rather than falling back to the old authentication DB.
        dedicated = (os.getenv('VERCEL_ENV') == 'production' or any(
            os.getenv(name) for name in (
                'ALEPH_STATE_URL', 'ALEPH_STATE_PUBLISHABLE_KEY',
                'ALEPH_STATE_DB_CAPABILITY')))
        if dedicated:
            self.url=os.getenv('ALEPH_STATE_URL','').rstrip('/')
            self.key=os.getenv('ALEPH_STATE_PUBLISHABLE_KEY','')
            self.cap=os.getenv('ALEPH_STATE_DB_CAPABILITY','')
        else:
            # Local test/development compatibility only.
            self.url=os.getenv('SUPABASE_URL','').rstrip('/')
            self.key=os.getenv('SUPABASE_PUBLISHABLE_KEY','')
            self.cap=os.getenv('ALEPH_STATE_CAPABILITY','')
        if (not re.fullmatch(r'https://[a-z0-9-]+\.supabase\.co',self.url)
                or not re.fullmatch(r'(sb_publishable_[A-Za-z0-9_-]+|eyJ[A-Za-z0-9._-]+)',self.key)
                or not isinstance(self.cap,str) or not 48<=len(self.cap)<=256
                or not self.cap.isascii() or any(ord(c)<33 or ord(c)>126 for c in self.cap)):
            raise StorageUnavailable('영속 저장소 설정이 필요합니다. 로컬 임시 파일로 대체하지 않습니다.')
        if os.getenv('VERCEL_ENV')=='preview':
            raise StorageUnavailable('Preview deployments cannot access production operations state')
    def rpc(self,name,body):
        try:return remote_json(self.url+'/rest/v1/rpc/'+name,{'apikey':self.key,'Accept':'application/json'},{'capability':self.cap,**body})
        except HTTPError as exc:
            if exc.code==409:raise Conflict('Concurrent state update; reload before saving') from None
            raise StorageUnavailable('Durable state service rejected the request') from None
        except (URLError,TimeoutError,OSError,ValueError) as exc:raise StorageUnavailable('Durable state service unavailable') from None
    def load(self):
        value=self.rpc('aleph_ops_load',{})
        if type(value) is not dict or type(value.get('revision')) is not int or value['revision']<0:raise StorageUnavailable('Invalid stored revision')
        validate_state(value['state'])
        return value
    def save(self,revision,state):
        validate_state(state)
        value=self.rpc('aleph_ops_save',{'expected_revision':revision,'new_state':state})
        if type(value) is not dict or value.get('revision')!=revision+1:raise StorageUnavailable('State commit was not confirmed')
        return value['revision']

def get_store():return SupabaseStore()

class Workspace:
    def __init__(self,root):
        self.root=Path(root)
        for name in ('workspace','feed','policy-trust','node-trust'):(self.root/name).mkdir(mode=0o700,exist_ok=True)
        token=self.root/'token';token.write_text(secrets.token_urlsafe(48));token.chmod(0o600)
        self.service=ConsoleService(self.root/'workspace',token,
            feed_root=self.root/'feed',device=os.getenv('ALEPH_DEFAULT_DEVICE','edge-69'),
            trust_dir=self.root/'policy-trust',node_trust_dir=self.root/'node-trust')
    def export(self):
        files={}
        for folder in ('workspace','feed','policy-trust','node-trust'):
            for path in (self.root/folder).rglob('*'):
                if path.is_dir():continue
                if path.name.startswith('.'):continue
                info=path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('Unexpected workspace entry')
                content=path.read_text()
                if path.name=='audit.jsonl':content='\n'.join(content.splitlines()[-500:])+'\n'
                files[path.relative_to(self.root).as_posix()]=content
        return validate_state({'format':1,'files':files})

@contextmanager
def materialize(state):
    validate_state(state)
    with tempfile.TemporaryDirectory(prefix='aleph-request-') as tmp:
        root=Path(tmp)
        for rel,content in state['files'].items():
            path=root/rel;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            path.write_text(content);path.chmod(0o600)
        yield Workspace(root)
