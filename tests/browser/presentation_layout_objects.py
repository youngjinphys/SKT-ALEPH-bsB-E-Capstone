"""Audit every slide's actual text and independent visual objects at breakpoints.

Reuses the production runner/browser. Decorative overlays have their stricter
word/leader/panel clearances in presentation_term_callouts.py.
"""
from pathlib import Path
import os
import re
from playwright.sync_api import expect

VIEWPORTS = ((1440, 900), (1180, 757), (1024, 768), (768, 1024), (390, 844), (320, 568))


def _assert_objects(slide, context):
    result = slide.evaluate("""root => {
        const visible = el => {
            if(!el.getClientRects().length)return false;
            for(let p=el;p&&p!==root.parentElement;p=p.parentElement){
                const css=getComputedStyle(p);
                if(css.visibility==='hidden'||css.visibility==='collapse'||css.display==='none'||Number(css.opacity)===0)return false;
            }
            return true;
        };
        const failures = [], describe = el => `${el.tagName}.${el.className}: ${el.textContent.trim().slice(0,70)}`;
        const items = [...root.querySelectorAll('h1,.slide-subtitle,.slide-point,.diagram-panel,.chart-card,.restored-node,.intro-stage,.policy-flow-stage,.policy-timeline-stage,.reference-group,.adoption-lane,.dns-route-node')].filter(visible);
        // A tall flex child centered above a scroller's content origin cannot
        // be recovered by wheel/Tab. Off-screen content below that origin is
        // allowed: this is a scrollable deck, not a fit-to-screen poster.
        for(const item of items){
            const r=item.getBoundingClientRect();
            for(let p=item.parentElement;p;p=p.parentElement){
                const css=getComputedStyle(p);
                if(!/auto|scroll/.test(css.overflowY))continue;
                const box=p.getBoundingClientRect(),scale=box.width/p.offsetWidth||1;
                const origin=box.top+(p.clientTop-p.scrollTop)*scale;
                if(r.top<origin-1)failures.push(`Object starts above reachable scroll content: ${describe(item)}`);
            }
        }
        for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++){
            const a=items[i],b=items[j];
            if(a.contains(b)||b.contains(a))continue;
            const x=a.getBoundingClientRect(),y=b.getBoundingClientRect();
            if(Math.min(x.right,y.right)-Math.max(x.left,y.left)>2&&Math.min(x.bottom,y.bottom)-Math.max(x.top,y.top)>2)
                failures.push(`Objects overlap: ${describe(a)} / ${describe(b)}`);
        }
        // Measure glyph ranges, not scrollWidth (decorative shadows/pseudo-elements
        // can enlarge the scrollable area without clipping a single letter).
        const blocks=[...root.querySelectorAll('h1,h2,h3,p,button,summary,td,th')].filter(visible);
        for(const block of blocks){
            if(block.closest('.sr-only,.term-note'))continue;
            const box=block.getBoundingClientRect(), range=document.createRange();
            const walker=document.createTreeWalker(block,NodeFilter.SHOW_TEXT);
            let node;
            while((node=walker.nextNode())){
                if(!node.textContent.trim()||!visible(node.parentElement)||node.parentElement.closest('.sr-only,svg'))continue;
                range.selectNodeContents(node);
                for(const r of range.getClientRects())if(r.width&&r.height&&(r.left<box.left-1||r.right>box.right+1))
                    failures.push(`Text leaves its block: ${describe(block)}`);
            }
        }
        return {failures:[...new Set(failures)],objects:items.length,textBlocks:blocks.length};
    }""")
    assert not result['failures'], (context, result)
    return result


def _assert_adoption_selection(slide, context):
    lanes = slide.locator('.adoption-lane')
    expect(lanes).to_have_count(3)
    expect(lanes.nth(2)).to_have_attribute('aria-pressed','true')
    neutral = lanes.nth(0).evaluate("el => {const css=getComputedStyle(el);return {'background-color':css.backgroundColor,'border-top-color':css.borderTopColor};}")
    for selected in (0, 1):
        lanes.nth(selected).click()
        expect(lanes.nth(selected)).to_have_attribute('aria-pressed','true')
        expect(lanes.nth(2)).to_have_attribute('aria-pressed','false')
        peer = lanes.nth(1 if selected == 0 else 0)
        expect(peer).to_have_attribute('aria-pressed','false')
        for property, color in neutral.items():
            # Poll both unselected cards through the normal 200ms transition.
            expect(peer).to_have_css(property,color)
            expect(lanes.nth(2)).to_have_css(property,color)
            expect(lanes.nth(selected)).not_to_have_css(property,color)
        print(f'Adoption selection {context}: {selected+1} selected, 03 matches neutral peer',flush=True)
    lanes.nth(2).click()
    expect(lanes.nth(2)).to_have_attribute('aria-pressed','true')


def check_layout_objects(browser, origin, slides):
    page = browser.new_page(reduced_motion='reduce')
    screenshots = Path(os.environ.get('ALEPH_LAYOUT_SCREENSHOTS', '/tmp/aleph-build-artifacts/layout'))
    screenshots.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        for width, height in VIEWPORTS:
            page.set_viewport_size({'width':width,'height':height})
            page.goto(f'{origin}/capstone#0')
            expect(page.locator('.deck-root')).to_have_attribute('data-hydrated','true')
            for index, data in enumerate(slides):
                page.evaluate('index => { window.location.hash=String(index); }', index)
                slide=page.locator('.slide-active .deck-slide')
                expect(slide).to_have_attribute('class', re.compile(rf'\bslide-{data["id"]}\b'))
                # Inspect both regions rather than declaring a hidden diagram safe.
                full=slide.locator('.mobile-full-view[aria-pressed="false"]')
                if full.count() and full.is_visible():
                    full.click()
                slide.evaluate('el => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                if data['id'] == 'friction-barriers':
                    _assert_adoption_selection(slide,(width,height))
                result=_assert_objects(slide,(data['id'],width,height))
                count += 1
                page.screenshot(path=str(screenshots/f'{index+1:02}-{data["id"]}-{width}x{height}.png'),full_page=True)
                print(f'Layout objects {data["id"]} {width}x{height}: {result["objects"]} objects, {result["textBlocks"]} text blocks',flush=True)
        print(f'Presentation object layout checks passed: {count} slide/viewport states',flush=True)
    finally:
        page.close()
