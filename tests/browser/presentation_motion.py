"""Text handoffs stay smooth, stable and readable without changing playback timing.

Imported by presentation_keyboard.py so this uses the existing built-app runner.
"""
from playwright.sync_api import expect


def check_motion(page, origin):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.emulate_media(reduced_motion="no-preference")

    def open_slide(fragment):
        # Other suites open independent pages; motion is a foreground behavior.
        page.bring_to_front()
        page.goto(f"{origin}/capstone#{fragment}")
        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
        assert page.evaluate('document.visibilityState') == 'visible'

    def assert_fade(selector):
        layers = page.locator(selector + ' .diagram-text-layer')
        assert layers.count() >= 2, selector
        assert layers.evaluate_all("""els => els.every(el => {
            const css = getComputedStyle(el);
            return el.getAttribute('aria-hidden') === 'true'
                ? css.visibility === 'hidden' && css.opacity === '0' && css.transitionDuration === '0s'
                : css.transitionProperty === 'opacity' && parseFloat(css.transitionDuration) > 0;
        })"""), selector
        expect(page.locator(selector + ' .diagram-text-layer[aria-hidden="false"]')).to_have_count(1)

    open_slide('dns')
    dns = page.locator('.restored-dns')
    title = page.locator('.dns-upstream strong')
    page.locator('.dns-client').scroll_into_view_if_needed()
    expect(dns).to_have_attribute('data-playback', 'running')
    assert_fade('.dns-upstream strong')
    initial = title.bounding_box()
    # Observe before the real handoff. Assertion polling can be a second apart
    # and return only after a 320ms fade has finished; sample rendered frames in
    # the page instead, without unsafe-eval or changing the application clock.
    handoff = title.evaluate("""el => new Promise(resolve => {
        const deadline=performance.now()+10000;
        const sample=()=>{
            const layers=[...el.querySelectorAll('.diagram-text-layer')];
            const active=layers.find(layer=>layer.getAttribute('aria-hidden')==='false');
            const opacity=layers.map(layer=>Number(getComputedStyle(layer).opacity));
            const visible=layers.filter(layer=>getComputedStyle(layer).visibility!=='hidden'&&Number(getComputedStyle(layer).opacity)>0);
            const overlap=visible.length>1;
            const intermediate=active?.textContent==='업스트림 DNS' && opacity.some(value=>value>0&&value<1);
            if(overlap || intermediate || performance.now()>=deadline){resolve({intermediate,overlap,opacity,active:active?.textContent,visibility:document.visibilityState,phase:el.closest('.restored-dns')?.dataset.introStep});return;}
            requestAnimationFrame(sample);
        };
        requestAnimationFrame(sample);
    })""")
    assert handoff['intermediate'] and not handoff['overlap'], handoff
    expect(title.locator('[aria-hidden="false"]')).to_have_text('업스트림 DNS')
    expect(title.locator('[aria-hidden="false"]')).to_have_css('opacity', '1')
    expect(title.locator('[aria-hidden="true"]')).to_have_css('opacity', '0')
    settled = title.bounding_box()
    assert abs(initial['width'] - settled['width']) < 1
    assert abs(initial['height'] - settled['height']) < 1
    expect(dns).to_have_attribute('data-intro-step', '11', timeout=10000)
    # Rapid scenario reversals cannot leave stale labels, blank text or reflow.
    web = page.locator('.dns-web')
    before = web.bounding_box()
    for name in ('차단 대상 조회', '정상 조회', '차단 대상 조회'):
        page.get_by_role('button', name=name, exact=True).click()
    expect(page.locator('.dns-web strong')).to_have_text('목적지 웹 서버')
    expect(page.locator('.dns-client small .diagram-text-layer[aria-hidden="false"]')).to_contain_text('blocked.test')
    assert abs(before['height'] - web.bounding_box()['height']) < 1
    for selector in ('.dns-intro-status', '.dns-client small'):
        assert_fade(selector)
    page.locator('#slide-area').press('r')
    expect(dns).to_have_attribute('data-intro-step', '11')
    expect(dns).to_have_attribute('data-scenario', 'block')
    expect(title.locator('[aria-hidden="false"]')).to_have_text('업스트림 DNS')

    for slide, selector, button in (
        ('architecture', '.policy-flow-detail strong', '.policy-flow-stage'),
        ('policy-demo', '.policy-timeline-result p', '.policy-timeline-stage button'),
    ):
        open_slide(slide)
        assert_fade(selector)
        detail = page.locator(selector)
        before = detail.bounding_box()
        page.locator(button).last.click()
        # Inspect the full transition, including rapid reversals, not only its end.
        for target in (page.locator(button).first, page.locator(button).last):
            target.click()
            page.locator(button).first.click()
            target.click()
            sampled = detail.evaluate("""el => new Promise(resolve => {
                const until=performance.now()+400, samples=[];
                const sample=()=>{
                    const layers=[...el.querySelectorAll('.diagram-text-layer')];
                    const visible=layers.filter(layer=>getComputedStyle(layer).visibility!=='hidden'&&Number(getComputedStyle(layer).opacity)>0);
                    const current=layers.find(layer=>layer.getAttribute('aria-hidden')==='false');
                    samples.push({visible:visible.length,stale:visible.some(layer=>layer!==current)});
                    if(performance.now()>=until){resolve(samples);return;}
                    requestAnimationFrame(sample);
                };
                sample();
            })""")
            assert sampled and all(frame['visible'] <= 1 and not frame['stale'] for frame in sampled), (slide, sampled)
            assert sampled[-1]['visible'] == 1, (slide, sampled)
            expect(detail.locator('[aria-hidden="false"]')).to_have_css('opacity', '1')
        after = detail.bounding_box()
        assert abs(before['height'] - after['height']) < 1, selector
    open_slide('http')
    assert_fade('.protocol-stage strong')

    # OS reduced motion and deck pause show current text immediately, never
    # retain a half-faded/blank layer. Controls remain usable without motion.
    for reduced, pause in (('reduce', False), ('no-preference', True)):
        page.emulate_media(reduced_motion=reduced)
        open_slide('dns')
        if pause:
            page.locator('#slide-area').press('m')
            expect(page.locator('html')).to_have_attribute('data-motion', 'off')
        page.get_by_role('button', name='차단 대상 조회', exact=True).click()
        active = page.locator('.dns-client small .diagram-text-layer[aria-hidden="false"]')
        expect(active).to_have_text('blocked.test · A 조회')
        assert active.evaluate("el => getComputedStyle(el).opacity") == '1'
        assert active.evaluate("el => getComputedStyle(el).transitionDuration") == '0s'

    # Longest labels reserve their space even in the narrow visual pane.
    page.set_viewport_size({"width": 390, "height": 844})
    page.emulate_media(reduced_motion='reduce')
    open_slide('dns')
    page.get_by_role('button', name='도식', exact=True).click()
    before = page.locator('.restored-dns-map').bounding_box()
    for name in ('차단 대상 조회', '정상 조회'):
        page.get_by_role('button', name=name, exact=True).click()
        after = page.locator('.restored-dns-map').bounding_box()
        assert abs(before['height'] - after['height']) < 1
    assert page.locator('.restored-dns').evaluate('el => el.scrollWidth <= el.clientWidth + 1')
    for width, height in ((1366, 768), (390, 667)):
        page.set_viewport_size({"width": width, "height": height})
        for slide in ('dns', 'architecture', 'policy-demo', 'http', 'topology-public'):
            open_slide(slide)
            visual_tab = page.get_by_role('button', name='도식', exact=True)
            if visual_tab.count() and visual_tab.is_visible():
                visual_tab.click()
            for text in page.locator('.slide-active .diagram-text-swap').all():
                if not text.is_visible():
                    continue
                text.scroll_into_view_if_needed()
                assert text.evaluate("""el => {
                    const box = el.getBoundingClientRect();
                    let top = 0, bottom = innerHeight, left = 0, right = innerWidth;
                    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
                        const css = getComputedStyle(parent), rect = parent.getBoundingClientRect();
                        if (/hidden|clip|auto|scroll/.test(css.overflowY)) {
                            top = Math.max(top, rect.top); bottom = Math.min(bottom, rect.bottom);
                        }
                        if (/hidden|clip|auto|scroll/.test(css.overflowX)) {
                            left = Math.max(left, rect.left); right = Math.min(right, rect.right);
                        }
                    }
                    return box.top >= top - 1 && box.bottom <= bottom + 1 &&
                        box.left >= left - 1 && box.right <= right + 1;
                }"""), f'{slide} caption clipped at {width}x{height}'
    print('Presentation text motion checks passed')
