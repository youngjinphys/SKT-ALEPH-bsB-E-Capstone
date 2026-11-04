"""Check every shared callout against real rendered glyph and control rectangles.

Imported by presentation_keyboard.py; does not create its own browser/server.
The pure routing tests are in term-leader-geometry.test.mjs.
"""
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
        const described = target.getAttribute('aria-describedby')?.split(/\\s+/).includes(note.id);
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
            if (css.visibility === 'hidden' || css.visibility === 'collapse' || parent.closest('[hidden],svg,script,style')) continue;
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
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        # The SNI precedent was intentionally removed from the authored table.
        # A slide ID must not leave an unrelated, targetless definition behind.
        page.goto(f'{origin}/capstone#precedents')
        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
        expect(page.locator('.slide-active .term-note')).to_have_count(0)
        expect(page.locator('.slide-active [data-term-target="sni"]')).to_have_count(0)
        for width, height in ((1440, 900), (1366, 768), (390, 844), (390, 667), (768, 1024)):
            page.set_viewport_size({'width': width, 'height': height})
            for slide, term in TERMS:
                print(f'Callout {term}: {width}x{height}', flush=True)
                page.goto(f'{origin}/capstone#{slide}')
                expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
                visual = page.get_by_role('button', name='도식', exact=True)
                if visual.count() and visual.first.is_visible():
                    visual.first.click()
                scene = page.locator(f'.slide-active .term-scene[data-term="{term}"]').first
                scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                if term == 'cname':
                    _assert_chain_connectors(scene)
                baseline = (width, height) == (1440, 900)
                result = _assert_clear(scene, required=baseline)
                if term == 'dnsmasq' and baseline:
                    assert result['side'] == 'top', result
                # Reflow at fractional browser zoom, then nested slide scrolling.
                page.locator('.deck-root').evaluate("el => { el.style.zoom = '1.25'; }")
                scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                _assert_clear(scene)
                if term == 'cname':
                    _assert_chain_connectors(scene)
                page.locator('.deck-root').evaluate("el => { el.style.zoom = ''; }")
                if term == 'cname':
                    page.get_by_role('button', name='SUBTREE 과차단', exact=True).click()
                    expect(page.locator('.term-note')).to_have_count(0)
                    page.get_by_role('button', name='CNAME 보호 공백', exact=True).click()
                    scene.locator('[data-term-target]').first.scroll_into_view_if_needed()
                    _assert_clear(scene)
        assert not errors, errors
    finally:
        page.close()
