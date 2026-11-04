"""Built references-page contract check using local HTTP and the standard library.

Run after apps/web `npm run check`. This is not browser/visual verification.
"""
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from html.parser import HTMLParser
import json
import os
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'apps/web'
PORT=int(os.environ.get('ALEPH_REFERENCES_TEST_PORT','18774'))

class Page(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=[];self.links=[];self.details=0
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if 'id' in values:self.ids.append(values['id'])
        if tag=='a':self.links.append(values)
        if tag=='details':self.details+=1

def main():
    with tempfile.TemporaryFile(mode='w+') as log:
        server=subprocess.Popen(['npm','run','start','--','--hostname','127.0.0.1','--port',str(PORT)],cwd=WEB,env={**os.environ,'PLAYWRIGHT_LOCAL_HTTP':'1'},stdout=log,stderr=subprocess.STDOUT)
        try:
            opener=build_opener(ProxyHandler({}));deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if server.poll() is not None:
                    log.seek(0);raise RuntimeError(log.read())
                try:
                    with opener.open(f'http://127.0.0.1:{PORT}/capstone/references',timeout=2) as response:
                        assert response.status==200
                        html=response.read().decode();headers={k.lower():v for k,v in response.headers.items()};break
                except OSError:time.sleep(.1)
            else:raise TimeoutError('References route did not respond')
            page=Page();page.feed(html)
            assert len(page.ids)==len(set(page.ids)),'Duplicate IDs'
            for link in page.links:
                href=link.get('href','')
                if href.startswith('#'):assert href[1:] in page.ids,href
                if href.startswith('https:'):assert link.get('rel')=='noopener noreferrer',link
            assert len([key for key in page.ids if key.startswith('slide-') and key!='slide-index'])==14
            manuscript=(WEB/'docs/presentation/final-20min-scenario.md').read_text().split('# 발표자 참고 · 예상 질문과 답변')[1]
            assert page.details==sum(line.startswith('## ') for line in manuscript.splitlines())
            assert all(key in page.ids for key in ('slide-index','bibliography','questions'))
            assert 'content-security-policy' in headers
            entries=[key for key in page.ids if key.startswith('reference-') and key!='reference-main']
            assert len(entries)>25
            print(f'PASS: local references HTTP200; {len(entries)} sources,14slide mappings,{page.details}Q&A;unique IDs,valid anchors,CSP')
            manifest=json.loads((WEB/'.next/server/app/capstone/references/page.js.nft.json').read_text())
            assert any('final-20min-scenario.md' in path for path in manifest['files'])
            assert any('sources.json' in path for path in manifest['files'])
            print('PASS: deployment trace contains manuscript and source registry')
        finally:
            server.terminate()
            try:server.wait(timeout=5)
            except subprocess.TimeoutExpired:server.kill();server.wait()

if __name__=='__main__':main()
