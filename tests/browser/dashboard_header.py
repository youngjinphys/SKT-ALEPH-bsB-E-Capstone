"""Header-only visual regression using the real local/cloud HTML and CSS.

No application JavaScript, authentication, server, or production requests run.
Unlocked labels/visibility are synthetic layout states, not login verification.
Run: PYTHONPATH=apps/policy-server/src python3 tests/browser/dashboard_header.py
"""
from pathlib import Path
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from cloud.assets import assets
from policy_server.console_assets import HTML, CSS
from playwright.sync_api import sync_playwright

WIDTHS = (320, 360, 390, 700, 701, 707, 768, 787, 1024, 1100, 1101, 1280, 1440, 1920)
OUT = Path(os.environ.get('ALEPH_SCREENSHOTS', '/tmp/aleph-header-artifacts'))
STATES = {
    'locked': ('콘솔 인증 필요', False),
    'connected': ('콘솔 연결됨', True),
    'pin': ('테스트 운영자 · 15분 세션', True),
    'long-account': ('운영자 · ' + 'long.operator.' * 5 + '@example.org', True),
}


def check_header(page, mode, state, width):
    geometry = page.evaluate('''() => {
      const box = el => el.getBoundingClientRect();
      const visible = el => box(el).width > 0 && box(el).height > 0;
      const inside = (inner, outer) => inner.left >= outer.left - 1 && inner.right <= outer.right + 1 && inner.top >= outer.top - 1 && inner.bottom <= outer.bottom + 1;
      const header = box(document.querySelector('.topbar'));
      const controls = [...document.querySelectorAll('.topbar-actions>a,.topbar-actions>button')].filter(visible).map(el => {
        const rect = box(el), range = document.createRange();
        range.selectNodeContents(el);
        const text = range.getBoundingClientRect();
        return {id:el.id,label:el.textContent,box:rect.toJSON(),inside:inside(rect,header),textInside:inside(text,rect),
          offset:Math.abs((rect.top+rect.bottom-text.top-text.bottom)/2),
          lines:new Set([...range.getClientRects()].filter(r=>r.width).map(r=>Math.round(r.top))).size};
      });
      const dot = box(document.querySelector('#connection-dot'));
      const status = box(document.querySelector('.connection-status'));
      const textEl = document.querySelector('#connection-text');
      const text = box(textEl), textRange = document.createRange();
      textRange.selectNodeContents(textEl);
      const context = box(document.querySelector('.topbar-context'));
      const actions = box(document.querySelector('.topbar-actions'));
      return {controls,overflow:document.documentElement.scrollWidth > innerWidth,
        lockVisible:visible(document.querySelector('#logout-button')),
        contextAboveActions:context.bottom <= actions.top,
        dotInsideStatus:inside(dot,status),statusInside:inside(status,header),
        dotCenterOffset:Math.abs((dot.top+dot.bottom-status.top-status.bottom)/2),
        textVisible:visible(textEl)&&getComputedStyle(textEl).clipPath==='none',
        textDisplay:getComputedStyle(textEl).display,
        textInsideStatus:inside(text,status)&&inside(textRange.getBoundingClientRect(),status),
        statusOverlap:controls.some(({box:r})=>r.left<status.right-1&&r.right>status.left+1&&r.top<status.bottom-1&&r.bottom>status.top+1)};
    }''')
    prefix = f'{mode}/{state}/{width}'
    assert not geometry['overflow'], (prefix, 'horizontal overflow', geometry)
    assert geometry['lockVisible'] == STATES[state][1], (prefix, 'hidden lock leaked')
    expected_controls = (4 if mode == 'cloud' else 1) + int(STATES[state][1])
    assert len(geometry['controls']) == expected_controls, (prefix, 'missing header action', geometry)
    assert geometry['textDisplay'] != 'none', (prefix, 'status removed from accessibility tree')
    assert geometry['dotInsideStatus'] and geometry['statusInside'], (prefix, 'status containment', geometry)
    assert geometry['dotCenterOffset'] <= 1, (prefix, 'orphan/misaligned status dot', geometry)
    if geometry['textVisible']:
        assert geometry['textInsideStatus'], (prefix, 'status text overflow', geometry)
    assert not geometry['statusOverlap'], (prefix, 'status/control overlap', geometry)
    if 701 <= width <= 1100:
        assert geometry['contextAboveActions'], (prefix, 'tablet context/actions share row')
    for i, control in enumerate(geometry['controls']):
        assert control['inside'] and control['textInside'], (prefix, 'control/text clipped', control)
        assert control['offset'] <= 3, (prefix, 'label not centered', control)
        assert control['lines'] == 1, (prefix, 'broken control label', control)
        assert control['box']['height'] >= 44, (prefix, 'small target', control)
        r = control['box']
        for previous in geometry['controls'][:i]:
            p = previous['box']
            assert not (r['left'] < p['right'] - 1 and r['right'] > p['left'] + 1 and r['top'] < p['bottom'] - 1 and r['bottom'] > p['top'] + 1), (prefix, 'control overlap')
    return geometry


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        opts = {'headless': True}
        if os.getenv('CHROMIUM_PATH'):
            opts['executable_path'] = os.environ['CHROMIUM_PATH']
        browser = p.chromium.launch(**opts)
        try:
            for mode in ('local', 'cloud'):
                html, css = (HTML, CSS) if mode == 'local' else assets()[:2]
                html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
                html = re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*>', '', html)
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                # No network is needed. A request would indicate a fixture leak.
                network = []
                page.on('request', lambda req: network.append(req.url))
                page.route('**/*', lambda route: route.abort())
                page.set_content(html, wait_until='domcontentloaded')
                page.add_style_tag(content=css)
                for state, (label, unlocked) in STATES.items():
                    if mode == 'local' and state in ('pin', 'long-account'):
                        continue
                    page.evaluate('''({label,unlocked})=>{
                      document.querySelector('#connection-text').textContent=label;
                      document.querySelector('#logout-button').hidden=!unlocked;
                    }''', {'label': label, 'unlocked': unlocked})
                    for width in WIDTHS:
                        page.set_viewport_size({'width': width, 'height': 900})
                        try:
                            geometry = check_header(page, mode, state, width)
                        except AssertionError:
                            page.screenshot(path=str(OUT / f'FAILED-{mode}-{state}-{width}.png'))
                            raise
                        results.append({'mode': mode, 'state': state, 'width': width, 'controls': geometry['controls']})
                        if width in (320, 707, 1101, 1440):
                            page.locator('.topbar').screenshot(path=str(OUT / f'{mode}-{state}-{width}.png'))
                    # Native tab traversal must include links and buttons but not
                    # hidden lock. No click/navigation or auth action occurs.
                    page.set_viewport_size({'width': 390, 'height': 900})
                    page.locator('#refresh-button').focus()
                    page.keyboard.press('Tab')
                    next_id = page.evaluate('document.activeElement.id')
                    assert (next_id == 'logout-button') if unlocked else (next_id != 'logout-button'), (mode, state, 'lock tab order')
                    if mode == 'cloud':
                        page.locator('.topbar-actions>a').first.focus()
                        focus = page.locator('.topbar-actions>a').first.evaluate('''el=>{const style=getComputedStyle(el), r=el.getBoundingClientRect(), h=el.closest('.topbar').getBoundingClientRect(), inset=parseFloat(style.outlineWidth)+parseFloat(style.outlineOffset);return {width:parseFloat(style.outlineWidth),style:style.outlineStyle,inside:r.left-inset>=h.left&&r.right+inset<=h.right&&r.top-inset>=h.top&&r.bottom+inset<=h.bottom};}''')
                        assert focus['width'] >= 2 and focus['style'] != 'none' and focus['inside'], (mode, state, 'missing/clipped focus outline')
                        page.keyboard.press('Tab')
                        assert page.evaluate('document.activeElement.getAttribute("href")') == '/capstone', (mode, state, 'link tab order')
                assert not network, (mode, 'unexpected fixture network', network)
                page.close()
        finally:
            browser.close()
    (OUT / 'header-geometry.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f'PASS: {len(results)} header states across {len(WIDTHS)} widths; synthetic local/cloud, no authentication or API calls')


if __name__ == '__main__':
    main()
