"""Exercise the real presentation controls, not just synthetic focus fixtures.

Imported by presentation_keyboard.py and run against its local production server.
No source link is followed and microphone capture is never requested. Every arrow
case remounts its slide through public URL navigation so earlier selections cannot
hide a control or turn a focus regression into a false pass. A fresh document per
viewport resets deck-wide state without hundreds of redundant asset reloads.
"""
from pathlib import Path
import json
from decimal import Decimal, ROUND_HALF_UP
import re

from playwright.sync_api import expect


DATA = Path(__file__).resolve().parents[2] / "apps/web/capstone/data"
VIEWPORTS = ((1440, 900), (1366, 768), (390, 844), (390, 720), (390, 667))
ACTIVE = ".slide-active .deck-slide"


def _name(control):
    return control.get_attribute("aria-label") or re.sub(r"\s+", " ", control.inner_text()).strip()


def _descriptor(control):
    # The full-view button changes its label and removes preceding pane buttons.
    # Its stable class avoids accidentally resolving the old ordinal afterwards.
    if "mobile-full-view" in (control.get_attribute("class") or "").split():
        return ("selector", ".mobile-full-view")
    if control.get_attribute("id"):
        return ("id", control.get_attribute("id"))
    # innerText is not an accessible name: several real buttons contain
    # aria-hidden step numbers/captions. Keep their stable DOM ordinal within
    # the freshly remounted state instead of fabricating a role/name query.
    ordinal = control.evaluate("el => [...el.closest('.deck-slide').querySelectorAll('button')].indexOf(el)")
    return ("index", (ordinal, _name(control)))


def _button(page, descriptor):
    kind, value = descriptor
    slide = page.locator(ACTIVE)
    if kind == "selector":
        return slide.locator(value)
    if kind == "id":
        return slide.locator(f'[id={json.dumps(value)}]')
    return slide.locator("button").nth(value[0])


def _visible_buttons(page):
    return [_descriptor(button) for button in page.locator(ACTIVE).get_by_role("button").all()
            if button.is_visible() and button.is_enabled()]


def _assert_readable(control, context):
    control.scroll_into_view_if_needed()
    geometry = control.evaluate("""el => {
        const rect = el.getBoundingClientRect();
        let left = 0, right = innerWidth, top = 0, bottom = innerHeight;
        for (let parent = el.parentElement; parent; parent = parent.parentElement) {
            const css = getComputedStyle(parent), box = parent.getBoundingClientRect();
            if (/hidden|clip|auto|scroll/.test(css.overflowX)) {
                left = Math.max(left, box.left); right = Math.min(right, box.right);
            }
            if (/hidden|clip|auto|scroll/.test(css.overflowY)) {
                top = Math.max(top, box.top); bottom = Math.min(bottom, box.bottom);
            }
        }
        return {width: rect.width, height: rect.height,
            horizontal: rect.left >= left - 1 && rect.right <= right + 1,
            vertical: rect.top >= top - 1 && rect.bottom <= bottom + 1,
            textFits: el.scrollWidth <= el.clientWidth + 1};
    }""")
    assert geometry["width"] > 0 and geometry["height"] > 0, (context, geometry)
    assert geometry["horizontal"] and geometry["vertical"], (context, "clipped control", geometry)
    assert geometry["textFits"], (context, "horizontally clipped label", geometry)


def _assert_focus_indicator(control, context):
    indicator = control.evaluate("""el => {
        const css = getComputedStyle(el);
        return {visible: el.matches(':focus-visible'), width: parseFloat(css.outlineWidth),
            style: css.outlineStyle, color: css.outlineColor};
    }""")
    assert indicator["visible"] and indicator["width"] >= 2, (context, indicator)
    assert indicator["style"] not in ("none", "hidden"), (context, indicator)
    assert indicator["color"] not in ("transparent", "rgba(0, 0, 0, 0)"), (context, indicator)


def _assert_selected_style(control, context):
    result = control.evaluate("""el => {
        const group = el.closest('[role="group"],fieldset');
        const peer = group?.querySelector('button[aria-pressed="false"]');
        if (!peer || el.getAttribute('aria-pressed') !== 'true') return null;
        const signature = node => {
            const css = getComputedStyle(node);
            return [css.backgroundColor, css.color, css.borderColor, css.fontWeight, css.boxShadow];
        };
        return {selected: signature(el), other: signature(peer)};
    }""")
    if result:
        assert result["selected"] != result["other"], (context, "selected state has no visual distinction", result)


def check_controls(page, origin, slides):
    """Check every visible local action on every published slide and viewport."""
    errors = []
    on_error = lambda error: errors.append(str(error))
    page.on("pageerror", on_error)
    indexes = {slide["id"]: index for index, slide in enumerate(slides)}
    cases = 0
    inventory = {}
    viewport = VIEWPORTS[0]
    loaded_viewport = None

    def at(index):
        expect(page).to_have_url(f"{origin}/capstone#{index}")
        expect(page.locator(ACTIVE)).to_have_attribute(
            "aria-label", re.compile(rf"^{index + 1}번째 슬라이드"))

    def open_slide(index, setup=None):
        nonlocal loaded_viewport
        if loaded_viewport != viewport:
            page.goto(f"{origin}/capstone#{index}", wait_until="domcontentloaded")
            page.reload(wait_until="domcontentloaded")
            expect(page.locator(".deck-root")).to_have_attribute("data-hydrated", "true")
            loaded_viewport = viewport
        else:
            full = page.locator(ACTIVE).locator(".mobile-full-view[aria-pressed=true]")
            if full.count():
                full.click()
            current = int(page.url.rsplit("#", 1)[1])
            # Hash navigation is the presentation's public routing interface.
            # Visiting another slide first remounts even a same-slide test case.
            if current == index:
                intermediate = (index + 1) % len(slides)
                page.evaluate("index => { window.location.hash = String(index); }", intermediate)
                at(intermediate)
            page.evaluate("index => { window.location.hash = String(index); }", index)
        at(index)
        # Capacity includes the actual safe-area/footer reservation. A 720px
        # viewport with the 22px build footer correctly uses full view (698px).
        expected = page.locator(".deck-root").evaluate("""root => {
            const css = getComputedStyle(root), visual = window.visualViewport;
            const usable = (visual?.height ?? innerHeight) - (parseFloat(css.paddingTop) || 0) - (parseFloat(css.paddingBottom) || 0);
            if (usable < 700 || (visual?.scale ?? 1) > 1) return 'full';
            return matchMedia('(max-width:780px)').matches ? 'panes|single' : 'desktop';
        }""")
        expect(page.locator(ACTIVE)).to_have_attribute("data-mobile-layout", re.compile(rf"^(?:{expected})$"))
        if setup:
            setup()

    def activate(button, activation, context):
        expect(button).to_have_count(1)
        expect(button).to_be_visible()
        assert button.evaluate("el => el.tabIndex") == 0, (context, "action missing from normal Tab order")
        _assert_readable(button, context)
        pressed = button.get_attribute("aria-pressed")
        full_toggle = "mobile-full-view" in (button.get_attribute("class") or "").split()
        if activation == "click":
            button.click()
        else:
            # Establish actual keyboard modality before programmatic positioning.
            # This avoids :focus-visible depending on the preceding pointer case.
            page.keyboard.press("Tab")
            button.focus()
            _assert_focus_indicator(button, context)
            page.keyboard.press(activation)
        if button.get_attribute("data-term-target"):
            # Definitions are dialogs, not display-choice buttons. Their native
            # focus owner keeps arrows until Escape returns to the original word.
            dialog = page.locator(".term-definition-dialog[open]")
            expect(dialog).to_be_visible()
            before = page.url
            page.keyboard.press("ArrowRight")
            assert page.url == before, context
            page.keyboard.press("Escape")
            expect(dialog).to_have_count(0)
        expect(button).to_be_focused()
        if pressed is not None:
            expected = "false" if full_toggle and pressed == "true" else "true"
            expect(button).to_have_attribute("aria-pressed", expected)
        if "policy-flow-stage" in (button.get_attribute("class") or "").split():
            expect(button).to_have_attribute("aria-current", "step")
        if button.get_attribute("aria-pressed") == "true":
            for target_id in (button.get_attribute("aria-controls") or "").split():
                target = page.locator(ACTIVE).locator(f'[id={json.dumps(target_id)}]')
                expect(target).to_have_count(1)
                expect(target).to_be_visible()
        _assert_selected_style(button, context)

    def arrow(index, key, focused=None):
        nonlocal cases
        page.keyboard.press(key)
        destination = min(len(slides) - 1, max(0, index + (1 if key == "ArrowRight" else -1)))
        at(destination)
        if destination != index:
            if focused is not None:
                expect(page.locator("#slide-area")).to_be_focused()
            expect(page.locator(".slide-leaving")).to_have_count(0)
        elif focused is not None:
            expect(focused).to_be_focused()
        cases += 1

    def button_case(index, descriptor, key, activation="click", setup=None):
        context = (viewport, slides[index]["id"], descriptor, activation, key)
        open_slide(index, setup)
        button = _button(page, descriptor)
        activate(button, activation, context)
        at(index)  # Activating a display choice must not itself advance the deck.
        arrow(index, key, button)

    def click_named(name):
        page.locator(ACTIVE).get_by_role("button", name=name, exact=True).click()

    def full_view():
        page.locator(ACTIVE).locator(".mobile-full-view").click()
        expect(page.locator(ACTIVE)).to_have_attribute("data-mobile-layout", "full")

    def bypass_visual():
        visual = page.locator(ACTIVE).get_by_role("button", name="도식", exact=True)
        if visual.count() and visual.is_visible():
            visual.click()

    try:
        # Reduced motion makes selection assertions deterministic; the existing
        # motion suite separately exercises live transitions and interrupted runs.
        page.emulate_media(reduced_motion="reduce")
        for viewport in VIEWPORTS:
            page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
            for index, slide in enumerate(slides):
                open_slide(index)
                controls = _visible_buttons(page)
                inventory[(viewport, slide["id"])] = len(controls)
                # Prevent accidentally reverting only part of the semantic fix.
                expect(page.locator(ACTIVE).locator('[role="tab"],[role="tablist"],[role="tabpanel"]')).to_have_count(0)
                for descriptor in controls:
                    for key in ("ArrowLeft", "ArrowRight"):
                        button_case(index, descriptor, key)
                    if viewport in ((1440, 900), (390, 844)):
                        button_case(index, descriptor, "ArrowLeft", "Enter")
                        button_case(index, descriptor, "ArrowRight", "Space")

                # Every page, including pages with no local controls, participates
                # in the boundary checks. A real content click replaces any focus
                # previously held by a local control, without a synthetic blur.
                for key in ("ArrowLeft", "ArrowRight"):
                    open_slide(index)
                    page.locator(ACTIVE).locator("h1").click()
                    arrow(index, key)

                # Source links keep native activation semantics. Only focus and
                # arrows are tested: this must never open a third-party website.
                open_slide(index)
                links = page.locator(ACTIVE).get_by_role("link").all()
                visible_links = [n for n, link in enumerate(links) if link.is_visible()]
                for ordinal in visible_links:
                    for key in ("ArrowLeft", "ArrowRight"):
                        open_slide(index)
                        link = page.locator(ACTIVE).get_by_role("link").nth(ordinal)
                        link.focus()
                        expect(link).to_be_focused()
                        arrow(index, key, link)

                # Full view removes the pane controls and exposes both regions.
                # Re-enumerate rather than trusting the initial mobile inventory.
                if viewport == (390, 844):
                    open_slide(index, full_view)
                    for ordinal, descriptor in enumerate(_visible_buttons(page)):
                        button_case(index, descriptor,
                                    "ArrowLeft" if ordinal % 2 else "ArrowRight", setup=full_view)

            # State-dependent markup must also be checked after changing modes.
            index = indexes["architecture"]
            for mode in ("현재 코드", "공공·ISP 제안"):
                setup = lambda mode=mode: click_named(mode)
                open_slide(index, setup)
                stages = [_descriptor(button) for button in page.locator(ACTIVE).locator(".policy-flow-stage").all()]
                assert len(stages) == 4, (viewport, mode, "pipeline stage coverage changed")
                for descriptor in stages:
                    for key in ("ArrowLeft", "ArrowRight"):
                        button_case(index, descriptor, key, setup=setup)

            index = indexes["bypass"]
            open_slide(index, bypass_visual)
            expect(page.locator(ACTIVE).locator(".server-dns-observation")).to_be_visible()

            index = indexes["pi-network-plan"]
            conditions = json.loads((DATA / "dns-latency.json").read_text())["series"]
            for condition in conditions:
                for key in ("ArrowLeft", "ArrowRight"):
                    open_slide(index)
                    group = page.locator(ACTIVE).get_by_role("group", name="측정 조건", exact=True)
                    expect(group.get_by_role("button")).to_have_count(len(conditions))
                    condition_button = group.get_by_role("button", name=condition["label"], exact=True)
                    activate(condition_button, "click", (viewport, condition["id"], "combined"))
                    expect(condition_button).to_have_attribute("aria-pressed", "true")
                    chart = page.locator("#latency-chart")
                    expect(chart).to_have_attribute("data-metric", "combined")
                    expect(chart.locator(".latency-arm")).to_have_count(len(condition["arms"]))
                    expect(chart).to_have_attribute("aria-label", re.compile(r"^p50·p95 함께 비교"))
                    for arm in condition["arms"]:
                        row = chart.locator(f'[data-arm="{arm["id"]}"]')
                        for metric in ("p50", "p95"):
                            expect(row.locator(f'[data-percentile="{metric}"] strong')).to_have_text(f'{Decimal(str(arm[metric])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)} ms')
                        expect(row.locator('.latency-dot')).to_have_count(2)
                    _assert_readable(chart, (viewport, condition["id"], "chart"))
                    _assert_readable(page.locator(".latency-source"), (viewport, condition["id"], "source footer"))
                    arrow(index, key, condition_button)

            index = indexes["http"]
            for protocol in (("HTTP", "HTTPS") if viewport[0] <= 780 else (None,)):
                for standard in ("EDE · RFC 8914", "SDE · IETF 초안"):
                    open_slide(index)
                    if protocol:
                        click_named(protocol)
                        expect(page.locator(f"#panel-protocol-{protocol.lower()}")).to_be_visible()
                        other = "http" if protocol == "HTTPS" else "https"
                        expect(page.locator(f"#panel-protocol-{other}")).to_be_hidden()
                    button = page.locator(ACTIVE).get_by_role("button", name=standard, exact=True)
                    activate(button, "click", (viewport, protocol, standard))
                    expect(page.locator("#panel-standards")).to_have_attribute("role", "region")
                    expect(page.locator("#panel-standards")).to_have_attribute(
                        "aria-labelledby", "tab-ede" if standard.startswith("EDE") else "tab-sde")
                    arrow(index, "ArrowRight", button)

            print(f"Presentation control inventory {viewport[0]}x{viewport[1]}: " +
                  ", ".join(f'{slide["id"]}={inventory[(viewport, slide["id"])]}' for slide in slides), flush=True)

        # The former tab groups now use normal DOM tab order, without a roving
        # tabindex or arrow-key interception. Check actual Tab traversal, not
        # merely attributes, and validate each controlled region's label.
        viewport = (390, 844)
        page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
        for slide_id, selector in (("dns", ".mobile-pane-tabs"),
                                   ("http", ".protocol-path-tabs"),
                                   ("http", ".protocol-standard-tabs"),
                                   ("pi-network-plan", ".latency-series-select")):
            open_slide(indexes[slide_id])
            group = page.locator(ACTIVE).locator(selector)
            buttons = group.get_by_role("button")
            page.keyboard.press("Tab")
            buttons.first.focus()
            for ordinal in range(buttons.count()):
                button = buttons.nth(ordinal)
                expect(button).to_be_focused()
                _assert_focus_indicator(button, (slide_id, selector, ordinal))
                for target_id in (button.get_attribute("aria-controls") or "").split():
                    expect(page.locator(ACTIVE).locator(f'[id={json.dumps(target_id)}]')).to_have_count(1)
                if ordinal + 1 < buttons.count():
                    page.keyboard.press("Tab")
            for ordinal in range(buttons.count() - 2, -1, -1):
                page.keyboard.press("Shift+Tab")
                expect(buttons.nth(ordinal)).to_be_focused()

        # Selecting either pane preserves focus, correctly exposes one named
        # region, and keeps hidden content out of both focus and Tab traversal.
        for index, slide in enumerate(slides):
            open_slide(index)
            group = page.locator(ACTIVE).locator(".mobile-pane-tabs")
            if not group.count():
                continue
            for pane, other, label in (("points", "visual", "요점"), ("visual", "points", "도식")):
                button = group.get_by_role("button", name=label, exact=True)
                button.click()
                expect(button).to_be_focused()
                visible = page.locator(f'#mobile-{slide["id"]}-{pane}')
                hidden = page.locator(f'#mobile-{slide["id"]}-{other}')
                expect(visible).to_be_visible()
                expect(visible).to_have_attribute("role", "region")
                expect(visible).to_have_attribute("aria-labelledby", button.get_attribute("id"))
                expect(hidden).to_be_hidden()
                assert hidden.evaluate("el => el.inert"), (slide["id"], other, "hidden pane is not inert")

        # Exercise the actual protected native range in its actual modal. Never
        # click the microphone start button or request browser permissions.
        open_slide(indexes["dns"])
        page.get_by_role("button", name="목차", exact=True).click()
        slider = page.get_by_role("dialog").locator("#clap-sensitivity")
        slider.focus()
        page.keyboard.press("Home")
        expect(slider).to_have_value("1")
        page.keyboard.press("ArrowRight")
        expect(slider).to_have_value("2")
        at(indexes["dns"])
        page.keyboard.press("ArrowLeft")
        expect(slider).to_have_value("1")
        expect(slider).to_be_focused()
        at(indexes["dns"])
        expect(page.get_by_role("button", name="박수 넘김 켜기", exact=True)).to_have_attribute("aria-pressed", "false")
        page.keyboard.press("Escape")
        expect(page.get_by_role("dialog")).not_to_be_visible()
        page.keyboard.press("ArrowRight")
        at(indexes["dns"] + 1)

        assert not errors, errors
        print(f"Presentation controls passed: {len(slides)} slides, {len(VIEWPORTS)} viewports, "
              f"{cases} real-focus arrow cases, all local button activations and state combinations", flush=True)
    finally:
        page.remove_listener("pageerror", on_error)
