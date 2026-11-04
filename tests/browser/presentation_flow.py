"""Real-time flow replay, manual selection and accessibility acceptance checks.

Uses the existing local production browser runner. No external services or
microphone permission are used; timeouts cover the authored, deliberately slow
flow rather than changing the application's timers.
"""
from playwright.sync_api import expect


def check_flow(browser, origin):
    page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="no-preference")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def open_slide(fragment, anchor):
        page.goto(f"{origin}/capstone#{fragment}")
        expect(page.locator('.deck-root')).to_have_attribute('data-hydrated', 'true')
        page.locator(anchor).first.scroll_into_view_if_needed()

    def loop(panel, expected_cycle, timeout=18000):
        expect(panel).to_have_attribute('data-flow-cycle', str(expected_cycle), timeout=timeout)

    try:
        open_slide('dns', '.dns-client')
        dns = page.locator('.restored-dns')
        choices = page.get_by_role('group', name='DNS 시나리오 선택')
        expect(choices.get_by_role('button')).to_have_count(2)
        expect(page.get_by_role('button', name='HTTP 안내', exact=True)).to_have_count(0)
        allow = choices.get_by_role('button', name='정상 조회', exact=True)
        blocked = choices.get_by_role('button', name='차단 대상 조회', exact=True)
        allow.click()
        page.locator('.dns-client').scroll_into_view_if_needed()
        expect(dns).to_have_attribute('data-intro-step', '11')
        expect(dns).to_have_attribute('data-step', '0')
        expect(blocked).to_have_attribute('aria-pressed', 'false')
        # Every selected packet has a slower 1.8s traversal within a 2.2s stage.
        packet = page.locator('.dns-query-link .lane-horizontal .lane-packet[data-flow=query]')
        assert packet.evaluate("el => getComputedStyle(el).animationDuration") == '1.8s'
        expect(dns).to_have_attribute('data-flow-resting', 'true', timeout=16000)
        expect(dns).to_have_attribute('data-step', '5')
        expect(dns).to_have_attribute('data-playback', 'paused')
        expect(choices).to_have_attribute('data-flow-cue', 'false')
        # The pure timing test enforces the 1000ms rest. An eventual browser
        # observation can arrive partway through it, so do not start a second
        # fixed sleep here and accidentally require more than the authored rest.
        loop(dns, 1, 2000)
        expect(dns).to_have_attribute('data-step', '0')
        expect(dns).to_have_attribute('data-scenario', 'allow')
        expect(allow).to_have_attribute('aria-pressed', 'true')
        expect(choices).to_have_attribute('data-flow-cue', 'true')
        assert blocked.evaluate("el => getComputedStyle(el).animationName") == 'flow-alternative-cue'
        loop(dns, 2)
        expect(dns).to_have_attribute('data-scenario', 'allow')
        # Switching, including while a cycle is running, is exclusively explicit.
        blocked.click()
        page.locator('.dns-client').scroll_into_view_if_needed()
        expect(dns).to_have_attribute('data-scenario', 'block')
        expect(dns).to_have_attribute('data-flow-cycle', '0')
        expect(choices).to_have_attribute('data-flow-cue', 'false')
        loop(dns, 1)
        expect(dns).to_have_attribute('data-scenario', 'block')
        page.locator('#slide-area').press('r')
        expect(dns).to_have_attribute('data-flow-cycle', '0')
        expect(dns).to_have_attribute('data-scenario', 'block')
        expect(dns).to_have_attribute('data-intro-step', '11')
        # Global pause freezes state/cues and resume keeps the same selection.
        page.locator('#slide-area').press('m')
        state = dns.get_attribute('data-step')
        page.wait_for_timeout(2600)
        expect(dns).to_have_attribute('data-step', state)
        expect(choices).to_have_attribute('data-flow-cue', 'false')
        page.locator('#slide-area').press('m')
        expect(dns).to_have_attribute('data-scenario', 'block')
        page.emulate_media(reduced_motion='reduce')
        blocked.click()
        page.wait_for_timeout(2600)
        expect(dns).to_have_attribute('data-flow-cycle', '0')
        expect(choices).to_have_attribute('data-flow-cue', 'false')
        assert blocked.evaluate("el => getComputedStyle(el).animationName") == 'none'
        expect(page.locator('.dns-accessible-flow ol li')).to_have_count(4)
        page.emulate_media(reduced_motion='no-preference')

        # Internal causal stages loop, but paired demonstrations remain chosen.
        open_slide('bypass', '.dns-evidence-dashboard')
        page.get_by_role('button', name='격리 fixture', exact=True).click()
        page.locator('.chain-step').first.scroll_into_view_if_needed()
        chain = page.locator('.cname-walkthrough')
        loop(chain, 1)
        old_packet = page.locator('.cname-packet').first.element_handle()
        # Keep the scrolled diagram in view. Focusing the outer viewport can
        # move it away and legitimately suspend its visibility-gated replay.
        page.keyboard.press('r')
        expect(chain).to_have_attribute('data-flow-cycle', '0')
        old_packet.wait_for_element_state('hidden', timeout=5000)
        assert old_packet.evaluate('el => !el.isConnected')
        expect(page.get_by_role('button', name='CNAME 보호 공백', exact=True)).to_have_attribute('aria-pressed', 'true')
        page.get_by_role('button', name='SUBTREE 과차단', exact=True).click()
        subtree = page.locator('.subtree-case')
        subtree.scroll_into_view_if_needed()
        loop(subtree, 1)
        expect(page.get_by_role('button', name='SUBTREE 과차단', exact=True)).to_have_attribute('aria-pressed', 'true')

        open_slide('topology-public', '.dns-route-topology')
        routes = page.locator('.dns-route-topology')
        expect(routes).to_have_attribute('data-playing', 'true')
        old_route = page.locator('.dns-route-policy-line svg').element_handle()
        page.keyboard.press('r')
        old_route.wait_for_element_state('hidden', timeout=5000)
        assert old_route.evaluate('el => !el.isConnected')
        expect(routes).to_have_attribute('data-flow-cycle', '0')
        page.get_by_role('button', name='다른 DNS 경로', exact=True).click()
        loop(routes, 1)
        expect(routes).to_have_attribute('data-stage', '2')
        expect(page.get_by_role('button', name='다른 DNS 경로', exact=True)).to_have_attribute('aria-pressed', 'true')

        open_slide('policy-demo', '.policy-timeline')
        lifecycle = page.locator('.policy-lifecycle')
        selected = page.locator('.policy-timeline button').last
        selected.click()
        page.wait_for_timeout(4000)
        expect(selected).to_have_attribute('aria-pressed', 'true')
        assert lifecycle.get_attribute('data-step') == '2'

        open_slide('http', '.restored-protocol-path')
        protocol = page.locator('.protocol-walkthrough')
        page.get_by_role('button', name='SDE · IETF 초안', exact=True).click()
        page.locator('.restored-protocol-path').first.scroll_into_view_if_needed()
        loop(protocol, 1)
        expect(page.get_by_role('button', name='SDE · IETF 초안', exact=True)).to_have_attribute('aria-pressed', 'true')
        # Automatic visual repetition does not announce every phase indefinitely.
        expect(page.locator('.protocol-stage')).to_have_attribute('aria-live', 'off')
        assert not errors, errors
        print('Presentation flow checks passed: manual scenarios, slower repeated paths, 1s rest, cues, pause and reduced motion')
    finally:
        page.close()
