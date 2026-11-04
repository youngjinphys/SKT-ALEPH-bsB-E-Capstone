"""Check every shared callout against real rendered glyph and control rectangles.

Imported by presentation_keyboard.py; does not create its own browser/server.
The pure routing tests are in term-leader-geometry.test.mjs.
"""
from pathlib import Path
import os

from playwright.sync_api import expect

TERMS = (('dns', 'dnsmasq'), ('bypass', 'cname'),
         ('policy-demo', 'ttl'), ('friction-barriers', 'fqdn'))


def _assert_clear(scene, required=False):
    expect(scene.locator('.term-note')).to_have_count(1)
    expect(scene.locator('[data-term-target]').first).to_be_visible()
    if required:
        expect(scene.locator('.term-leader')).to_have_count(1)
    # Wait for ResizeObserver/scroll/font scheduling without changing app clocks.
    scene.evaluate("el => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    result = scene.evaluate("""root => {
        const note = root.querySelector('.term-note'), target = root.querySelector('[data-term-target]');
        const described = target.getAttribute('aria-describedby')?.split(/\\s+/).some(id => document.getElementById(id)?.textContent.includes(target.textContent.trim()));
        const svg = root.querySelector('.term-leader');
        // A dense layout may omit the decorative leader rather than cover text.
        // The definition and its accessible association must still be present.
        if (!svg) return {collisions:[], described, leader:false};
        const path = svg.querySelector('path');
        const matrix = svg.getScreenCTM(), marker = svg.querySelector('circle');
        const coordinates = path.getAttribute('d').match(/-?\\d+(?:\\.\\d+)?(?:e[+-]?\\d+)?/gi).map(Number);
        const points = [];
        for (let i = 0; i < coordinates.length; i += 2)
            points.push(new DOMPoint(coordinates[i], coordinates[i + 1]).matrixTransform(matrix));
        const dot = new DOMPoint(Number(marker.getAttribute('cx')), Number(marker.getAttribute('cy'))).matrixTransform(matrix);
        const radius = Number(marker.getAttribute('r')) * Math.max(Math.abs(matrix.a), Math.abs(matrix.d));
        const obstacles = [], range = document.createRange();
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            if (!node.textContent.trim()) continue;
            const parent = node.parentElement, css = getComputedStyle(parent);
            if (css.visibility === 'hidden' || css.visibility === 'collapse' || parent.closest('[hidden],.sr-only,.term-note,svg,script,style')) continue;
            range.selectNodeContents(node);
            for (const r of range.getClientRects()) if (r.width && r.height)
                obstacles.push({left:r.left-2, top:r.top-2, right:r.right+2, bottom:r.bottom+2});
        }
        for (const control of root.querySelectorAll('.term-anchor button,.term-anchor input,.term-anchor select,.term-anchor textarea')) {
            if (!control.getClientRects().length) continue;
            const r = control.getBoundingClientRect();
            obstacles.push({left:r.left, top:r.top, right:r.right, bottom:r.bottom});
        }
        const collisions = [];
        for (const r of obstacles) {
            for (let i = 1; i < points.length; i++) {
                const a = points[i-1], b = points[i];
                const hit = Math.abs(a.y-b.y) < .1
                    ? a.y>r.top+.1 && a.y<r.bottom-.1 && Math.max(a.x,b.x)>r.left+.1 && Math.min(a.x,b.x)<r.right-.1
                    : a.x>r.left+.1 && a.x<r.right-.1 && Math.max(a.y,b.y)>r.top+.1 && Math.min(a.y,b.y)<r.bottom-.1;
                if (hit) collisions.push('leader crosses text/control');
            }
            const x = Math.max(r.left, Math.min(r.right,dot.x)), y = Math.max(r.top,Math.min(r.bottom,dot.y));
            if (Math.hypot(dot.x-x,dot.y-y) < radius-.1) collisions.push('marker covers text/control');
        }
        return {collisions, side:svg.dataset.termSide, described, leader:true,
            hidden:svg.getAttribute('aria-hidden'), pointer:getComputedStyle(svg).pointerEvents};
    }""")
    assert not result['collisions'], result
    assert result['described'], result
    if result['leader']:
        assert result['hidden'] == 'true' and result['pointer'] == 'none', result
    return result


def _assert_overlay(scene):
    """HUD uses existing background and never changes underlying geometry."""
    result = scene.evaluate("""root => {
        const note=root.querySelector('.term-note'), target=root.querySelector('[data-term-target]');
        const box=note.getBoundingClientRect(), word=target.getBoundingClientRect(), scale=root.getBoundingClientRect().width/root.offsetWidth || 1;
        const failures=[], visible=getComputedStyle(note).visibility==='visible';
        if(getComputedStyle(note).position!=='absolute'||note.parentElement!==root)failures.push('HUD is not a scene overlay');
        if(root.querySelector('.term-dock'))failures.push('HUD still reserves a row');
        const elements=[root,...root.querySelectorAll('.term-anchor,.diagram-panel,button,.restored-node,.chain-step,.cname-link')];
        const geometry=()=>elements.map(el=>{const r=el.getBoundingClientRect();return [r.x,r.y,r.width,r.height]});
        const before=geometry();note.style.display='none';const after=geometry();note.style.display='';
        if(before.some((r,i)=>r.some((v,k)=>Math.abs(v-after[i][k])>.1)))failures.push('HUD reflows underlying content');
        if(!visible)return {failures,visible,layout:root.dataset.termLayout};
        const gap=Math.hypot(Math.max(0,word.left-box.right,box.left-word.right),Math.max(0,word.top-box.bottom,box.top-word.bottom))/scale;
        if(gap>181)failures.push('HUD too far from target');
        if(box.left<-.5||box.right>innerWidth+.5||box.top<-.5||box.bottom>innerHeight+.5)failures.push('HUD leaves viewport');
        const overlaps=r=>Math.min(box.right,r.right)-Math.max(box.left,r.left)>1 && Math.min(box.bottom,r.bottom)-Math.max(box.top,r.top)>1;
        const walker=document.createTreeWalker(root.closest('.deck-slide'),NodeFilter.SHOW_TEXT),range=document.createRange();
        let node;
        while((node=walker.nextNode())){
            if(!node.textContent.trim())continue;
            const parent=node.parentElement,css=getComputedStyle(parent);
            if(css.visibility==='hidden'||css.visibility==='collapse'||parent.closest('[hidden],.sr-only,.term-note,svg,script,style'))continue;
            range.selectNodeContents(node);
            for(const r of range.getClientRects())if(r.width&&r.height&&overlaps(r))failures.push('HUD covers diagram text');
        }
        for(const control of root.closest('.deck-slide').querySelectorAll('button,input,select,textarea,.restored-node,.chain-step,.cname-arrow,.slide-point'))
            if(control.getClientRects().length&&overlaps(control.getBoundingClientRect()))failures.push('HUD covers control/card/arrow');
        const noteWalker=document.createTreeWalker(note,NodeFilter.SHOW_TEXT);
        while((node=noteWalker.nextNode())){
            if(!node.textContent.trim())continue;
            range.selectNodeContents(node);
            for(const r of range.getClientRects())if(r.width&&r.height&&(r.left<box.left-1||r.right>box.right+1||r.top<box.top-1||r.bottom>box.bottom+1))failures.push('HUD text clips');
        }
        return {failures,gap,visible,layout:root.dataset.termLayout};
    }""")
    assert not result['failures'], result
    assert result['layout'] == ('overlay' if result['visible'] else 'on-demand'), result
    return result


def _assert_dialog(page, scene):
    target=scene.locator('[data-term-target]').first
    target.focus()
    page.keyboard.press('Enter')
    dialog=page.locator('.term-definition-dialog[open]')
    expect(dialog).to_be_visible()
    before=page.url
    page.keyboard.press('ArrowRight')
    assert page.url == before, 'Dialog must own its keyboard interaction'
    result=dialog.evaluate("""el=>{
        const r=el.getBoundingClientRect();
        return {viewport:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,
            readable:getComputedStyle(el).fontSize,close:!!el.querySelector('button'),text:el.textContent.length};
    }""")
    assert result['viewport'] and result['close'] and result['text']>30, result
    page.keyboard.press('Escape')
    expect(dialog).to_have_count(0)
    expect(target).to_be_focused()


def _assert_chain_connectors(scene):
    result = scene.locator('.chain-nodes').evaluate("""root => {
        const cards = [...root.querySelectorAll(':scope > .chain-step')];
        const links = [...root.querySelectorAll(':scope > .cname-link')];
        const failures = [];
        if (links.length !== cards.length - 1) failures.push('missing between-card connector');
        for (let i = 0; i < links.length; i++) {
            const before = cards[i].getBoundingClientRect(), after = cards[i+1].getBoundingClientRect();
            const link = links[i].getBoundingClientRect(), arrow = links[i].querySelector('.cname-arrow').getBoundingClientRect();
            if (link.top < before.bottom - 1 || link.bottom > after.top + 1) failures.push('connector overlaps a card');
            if (Math.abs((arrow.left+arrow.right)/2 - (before.left+before.right)/2) > 1) failures.push('arrow not centered between cards');
            const label = links[i].querySelector('.cname-link-label');
            if (label.scrollWidth > label.clientWidth+1) failures.push('connector label clipped');
        }
        return failures;
    }""")
    assert not result, result


def check_term_callouts(browser, origin):
    page = browser.new_page(reduced_motion='reduce')
    errors = []
    overlays = 0
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        # The SNI precedent was intentionally removed from the authored table.
        # A slide ID must not leave an unrelated, targetless definition behind.
        page.goto(f'{origin}/capstone#precedents')
        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
        expect(page.locator('.slide-active .term-note')).to_have_count(0)
        expect(page.locator('.slide-active [data-term-target="sni"]')).to_have_count(0)
        for width, height in ((1440, 900), (1366, 768), (390, 844), (390, 667), (768, 1024), (320, 740)):
            page.set_viewport_size({'width': width, 'height': height})
            for slide, term in TERMS:
                print(f'Callout {term}: {width}x{height}', flush=True)
                page.goto(f'{origin}/capstone#{slide}')
                expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
                visual = page.get_by_role('button', name='도식', exact=True)
                if visual.count() and visual.first.is_visible():
                    visual.first.click()
                if term == 'cname':
                    page.get_by_role('button', name='격리 fixture', exact=True).click()
                scene = page.locator(f'.slide-active .term-scene[data-term="{term}"]').first
                scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                if term == 'cname':
                    _assert_chain_connectors(scene)
                baseline = (width, height) == (1440, 900)
                _assert_clear(scene)
                placement = _assert_overlay(scene)
                overlays += placement["visible"]
                if baseline and term == "dnsmasq":
                    assert placement["visible"], "Reported spacious DNS case must show the background HUD"
                _assert_dialog(page, scene)
                if width in (1440, 390, 320) and height != 667:
                    screenshots = Path(os.environ.get('ALEPH_CALLOUT_SCREENSHOTS', '/tmp/aleph-build-artifacts/callouts'))
                    screenshots.mkdir(parents=True, exist_ok=True)
                    scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                    page.screenshot(path=str(screenshots / f'{term}-{width}x{height}.png'))
                _assert_overlay(scene)
                # Reflow at fractional browser zoom, then nested slide scrolling.
                page.locator('.deck-root').evaluate("el => { el.style.zoom = '1.25'; }")
                scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                _assert_clear(scene)
                _assert_overlay(scene)
                if term == 'cname':
                    _assert_chain_connectors(scene)
                page.locator('.deck-root').evaluate("el => { el.style.zoom = ''; }")
                if term == 'cname':
                    page.get_by_role('button', name='SUBTREE 과차단', exact=True).click()
                    expect(page.locator('.term-note')).to_have_count(0)
                    page.get_by_role('button', name='CNAME 보호 공백', exact=True).click()
                    scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                    _assert_clear(scene)
                    _assert_overlay(scene)
                # Large zoom must never create a row or cover content to force a HUD.
                page.locator('.deck-root').evaluate("el => { el.style.zoom = '2'; }")
                scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                _assert_clear(scene)
                _assert_overlay(scene)
                _assert_dialog(page, scene)
                page.locator('.deck-root').evaluate("el => { el.style.zoom = ''; }")
        assert overlays > 0, 'At least one spacious layout must render the requested automatic HUD'
        assert not errors, errors
    finally:
        page.close()
