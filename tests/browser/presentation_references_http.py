"""Confirm the mistaken separate references route is absent from the built app."""
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from urllib.error import HTTPError
import os,subprocess,tempfile,time
ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'apps/web'
PORT=int(os.environ.get('ALEPH_REFERENCES_TEST_PORT','18774'))
def main():
    with tempfile.TemporaryFile(mode='w+') as log:
        server=subprocess.Popen(['npm','run','start','--','--hostname','127.0.0.1','--port',str(PORT)],cwd=WEB,env={**os.environ,'PLAYWRIGHT_LOCAL_HTTP':'1'},stdout=log,stderr=subprocess.STDOUT)
        try:
            opener=build_opener(ProxyHandler({}));deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if server.poll() is not None:
                    log.seek(0);raise RuntimeError(log.read())
                try:
                    with opener.open(f'http://127.0.0.1:{PORT}/capstone',timeout=2) as response:
                        assert response.status==200
                        assert response.headers.get('Content-Security-Policy')
                        break
                except OSError:time.sleep(.1)
            else:raise TimeoutError('Presentation did not respond')
            try:opener.open(f'http://127.0.0.1:{PORT}/capstone/references',timeout=2)
            except HTTPError as error:assert error.code==404,error.code
            else:raise AssertionError('Separate references route still exists')
            assert not (WEB/'.next/server/app/capstone/references/page.js.nft.json').exists()
            print('PASS: presentation HTTP200 with CSP; separate references route HTTP404')
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()
if __name__=='__main__':main()
