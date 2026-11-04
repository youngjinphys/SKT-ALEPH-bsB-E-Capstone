"""Production-build keyboard regression checks using the existing Playwright runner.

Run after `npm run check` in apps/web. No production service or account is used.
CHROMIUM_PATH can select an already installed browser for local verification.
"""
from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
import time
from urllib.request import build_opener, ProxyHandler

from playwright.sync_api import expect, sync_playwright
from presentation_motion import check_motion
from presentation_flow import check_flow
from presentation_term_callouts import check_term_callouts
from presentation_controls import check_controls
from presentation_layout_objects import check_layout_objects
from presentation_build_timestamp import check_build_timestamp
from presentation_dns_terminal import check_dns_terminal
from presentation_header import check_header_navigation
from presentation_dns_decision import check_dns_decision
from presentation_protocol_edges import check_protocol_edges

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps/web"
PORT = int(os.environ.get("ALEPH_PRESENTATION_TEST_PORT", "18767"))
ORIGIN = f"http://127.0.0.1:{PORT}"
SLIDES = json.loads((WEB / "capstone/data/sequence.json").read_text())["slides"]


def check_keyboard(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def open_slide(fragment="0"):
        page.goto(f"{ORIGIN}/capstone#{fragment}")
        expect(page.locator('.deck-root')).to_have_attribute("data-hydrated", "true")
        page.locator("#slide-area").focus()

    def at(index):
        expect(page).to_have_url(f"{ORIGIN}/capstone#{index}")
        expect(page.locator(".slide-active .deck-slide")).to_have_attribute(
            "aria-label", re.compile(rf"^{index + 1}번째 슬라이드"))

    open_slide()
    page.keyboard.press("ArrowRight")
    at(1)
    page.keyboard.press("ArrowLeft")
    at(0)
    page.keyboard.press("ArrowLeft")
    at(0)
    for _ in range(5):
        page.keyboard.press("ArrowRight")
    at(5)
    page.go_back()
    at(4)
    page.go_forward()
    at(5)
    page.reload()
    at(5)
    open_slide(str(len(SLIDES) - 1))
    page.keyboard.press("ArrowRight")
    at(len(SLIDES) - 1)

    # Opening a chapter/menu leaves focus on a navigation button. Plain arrows
    # must still work there; Space/Enter must retain native button activation.
    open_slide()
    page.locator(".deck-chapters button").first.click()
    chapter_index = int(page.url.rsplit("#", 1)[1])
    page.keyboard.press("ArrowRight")
    at(chapter_index + 1)
    page.get_by_role("button", name="목차", exact=True).click()
    page.locator(".overview-list button").nth(2).click()
    at(2)
    page.keyboard.press("ArrowRight")
    at(3)

    # Browser shortcuts, selection, scrolling and repeat/IME events are not
    # presentation commands. Test cancellation as well as unchanged slide state.
    open_slide("2")
    for key in ("Shift+ArrowRight", "Control+ArrowRight", "Meta+ArrowRight",
                "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", "Space"):
        page.keyboard.press(key)
        at(2)
    for options in ({"altKey": True}, {"repeat": True}, {"isComposing": True},
                    {"alreadyPrevented": True}):
        consumed = page.locator("#slide-area").evaluate("""(el, options) => {
            const event = new KeyboardEvent('keydown', {
                key: 'ArrowRight', bubbles: true, cancelable: true, ...options
            });
            if (options.alreadyPrevented) event.preventDefault();
            el.dispatchEvent(event);
            return event.defaultPrevented;
        }""", options)
        assert consumed == bool(options.get("alreadyPrevented")), options
        at(2)

    # Real native controls and nested contenteditables must keep their keys.
    for markup in ('<input value="abc">', '<textarea>abc</textarea>',
                   '<select><option>a</option><option>b</option></select>',
                   '<input type="range" min="0" max="5" value="2">',
                   '<div contenteditable="true"><span tabindex="0">abc</span></div>'):
        page.evaluate("""markup => {
            const host = document.createElement('div'); host.id = 'keyboard-fixture';
            host.innerHTML = markup; document.querySelector('.slide-active').append(host);
            (host.querySelector('span') || host.firstElementChild).focus();
        }""", markup)
        page.keyboard.press("ArrowRight")
        at(2)
        if 'type="range"' in markup:
            expect(page.locator('#keyboard-fixture input')).to_have_value("3")
        page.locator("#keyboard-fixture").evaluate("el => el.remove()")

    page.get_by_role("button", name="목차", exact=True).click()
    page.keyboard.press("ArrowRight")
    at(2)
    expect(page.get_by_role("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    page.get_by_role("button", name="참조·발표 노트 보기", exact=True).click()
    page.keyboard.press("ArrowRight")
    at(2)
    page.keyboard.press("Escape")
    expect(page.locator("#slide-details")).to_have_count(0)

    # Ordinary scenario/action buttons own Enter/Space, not arrows. Clicking
    # them must not trap deck navigation, and must not forcibly blur the button.
    dns_index = next(i for i, slide in enumerate(SLIDES) if slide["id"] == "dns")
    for activation in ("click", "Enter", "Space"):
        open_slide("dns")
        block = page.get_by_role("button", name="차단 대상 조회", exact=True)
        if activation == "click":
            block.click()
        else:
            block.focus()
            page.keyboard.press(activation)
        expect(block).to_be_focused()
        expect(block).to_have_attribute("aria-pressed", "true")
        expect(page).to_have_url(f"{ORIGIN}/capstone#dns")
        page.keyboard.press("ArrowRight")
        at(dns_index + 1)
        expect(page.locator("#slide-area")).to_be_focused()

    for slide_id, selector in (
        ("architecture", ".policy-flow-stage"),
        ("policy-demo", ".policy-timeline-stage button"),
    ):
        open_slide(slide_id)
        page.locator(".slide-active " + selector).first.click()
        page.keyboard.press("ArrowLeft")
        at(next(i for i, slide in enumerate(SLIDES) if slide["id"] == slide_id) - 1)
        expect(page.locator("#slide-area")).to_be_focused()

    open_slide("dns")
    page.locator(".slide-active .restored-diagram").focus()
    page.keyboard.press("ArrowDown")
    expect(page).to_have_url(f"{ORIGIN}/capstone#dns")
    page.keyboard.press("ArrowRight")
    at(dns_index + 1)

    # Arrow-owning widgets retain their keys, even if they have no handler or
    # live outside today's diagram class names. A generic role=group does not
    # claim arrow keys: scenario button groups above continue to navigate.
    open_slide("2")
    for role in ("tab", "tablist", "slider", "spinbutton", "combobox",
                 "listbox", "radiogroup", "radio", "menu", "menubar", "tree", "grid"):
        consumed = page.evaluate("""role => {
            const widget = document.createElement('div');
            widget.setAttribute('role', role); widget.tabIndex = 0;
            document.querySelector('.slide-active').append(widget); widget.focus();
            const event = new KeyboardEvent('keydown', {
                key: 'ArrowRight', bubbles: true, cancelable: true
            });
            widget.dispatchEvent(event); widget.remove(); return event.defaultPrevented;
        }""", role)
        assert not consumed, role
        at(2)

    # Remaining HTTP/HTTPS choices still use native button and arrow behavior.
    page.set_viewport_size({"width": 390, "height": 844})
    open_slide("http")
    visual = page.get_by_role("button", name="도식", exact=True)
    if visual.is_visible():
        visual.click()
    https = page.get_by_role("button", name="HTTPS", exact=True)
    https.focus()
    page.keyboard.press("Space")
    expect(https).to_be_focused()
    expect(https).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".protocol-standard-panel")).to_have_count(0)
    page.keyboard.press("ArrowRight")
    at(next(i for i, slide in enumerate(SLIDES) if slide["id"] == "http") + 1)
    open_slide("http")
    if visual.is_visible():
        visual.click()
    page.locator(".protocol-walkthrough").focus()
    page.keyboard.press("ArrowLeft")
    at(next(i for i, slide in enumerate(SLIDES) if slide["id"] == "http") - 1)

    page.set_viewport_size({"width": 390, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    open_slide("dns")
    points = page.get_by_role("button", name="요점", exact=True)
    visual = page.get_by_role("button", name="도식", exact=True)
    points.focus()
    page.keyboard.press("Enter")
    expect(points).to_be_focused()
    expect(points).to_have_attribute("aria-pressed", "true")
    expect(page.locator('#mobile-dns-visual')).to_be_hidden()
    page.keyboard.press("Tab")
    expect(visual).to_be_focused()
    page.keyboard.press("Space")
    expect(visual).to_have_attribute("aria-pressed", "true")
    expect(page.locator('#mobile-dns-visual')).to_be_visible()
    expect(page).to_have_url(f"{ORIGIN}/capstone#dns")
    page.keyboard.press("ArrowRight")
    at(dns_index + 1)
    expect(page.locator(".slide-leaving")).to_have_count(0)
    assert not errors, errors


def main():
    subprocess.run(["node", "--test", "tests/browser/flow-timing.test.mjs", "tests/browser/term-leader-geometry.test.mjs", "tests/browser/dns_terminal.test.mjs"], cwd=ROOT, check=True)
    with tempfile.TemporaryFile(mode="w+") as log:
        server = subprocess.Popen(
            ["npm", "run", "start", "--", "--hostname", "127.0.0.1", "--port", str(PORT)],
            cwd=WEB, env={**os.environ, "PLAYWRIGHT_LOCAL_HTTP": "1"},
            stdout=log, stderr=subprocess.STDOUT)
        try:
            opener = build_opener(ProxyHandler({}))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                try:
                    with opener.open(ORIGIN + "/capstone", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise TimeoutError("Presentation server did not become ready")
            with sync_playwright() as playwright:
                options = {"headless": True}
                if os.getenv("CHROMIUM_PATH"):
                    options["executable_path"] = os.environ["CHROMIUM_PATH"]
                browser = playwright.chromium.launch(**options)
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    page.set_default_timeout(5000)
                    check_build_timestamp(browser, ORIGIN)
                    check_keyboard(page)
                    check_header_navigation(browser, ORIGIN)
                    check_dns_decision(browser, ORIGIN)
                    check_protocol_edges(browser, ORIGIN)
                    check_dns_terminal(browser, ORIGIN)
                    check_motion(page, ORIGIN)
                    check_term_callouts(browser, ORIGIN)
                    check_flow(browser, ORIGIN)
                    check_layout_objects(browser, ORIGIN, SLIDES)
                    check_controls(page, ORIGIN, SLIDES)
                finally:
                    browser.close()
            print("Presentation keyboard browser checks passed")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
