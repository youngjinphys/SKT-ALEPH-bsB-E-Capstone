"""Watermark hydration, timezone and unobstructed-footer checks in the CI browser."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from playwright.sync_api import expect


def local_label(instant, zone):
    local = datetime.fromisoformat(instant.replace("Z", "+00:00")).astimezone(ZoneInfo(zone))
    minutes = int(local.utcoffset().total_seconds() / 60)
    if minutes == 0:
        offset = "UTC"
    else:
        hours, remainder = divmod(abs(minutes), 60)
        offset = f"GMT{'+' if minutes > 0 else '-'}{hours}"
        if remainder:
            offset += f":{remainder:02d}"
    return f"Updated at {local:%Y-%m-%d %H:%M:%S} {offset}"


def check_build_timestamp(browser, origin):
    artifact_dir = Path("/tmp/aleph-build-artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    built_at = None
    for width, height, zone in [
        (1440, 900, "Asia/Seoul"),
        (1366, 768, "America/Los_Angeles"),
        (1024, 768, "Asia/Kathmandu"),
        (390, 844, "Asia/Seoul"),
        (320, 568, "America/Los_Angeles"),
    ]:
        context = browser.new_context(viewport={"width": width, "height": height}, timezone_id=zone)
        try:
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.emulate_media(reduced_motion="reduce")
            # A wrong viewer clock cannot become the displayed build time.
            page.clock.set_fixed_time(datetime(2035, 1, 1))
            for fragment in ["0", "8"]:
                page.goto(f"{origin}/capstone#{fragment}")
                expect(page.locator(".deck-root")).to_have_attribute("data-hydrated", "true")
                marker = page.locator(".build-timestamp")
                expect(marker).to_be_visible()
                assert marker.count() == 1
                timestamp = marker.locator("time").get_attribute("datetime")
                built_at = built_at or timestamp
                assert timestamp == built_at, (width, zone, timestamp, built_at)
                expected = local_label(built_at, zone)
                expect(marker).to_have_text(expected)
                expect(marker.locator("time")).to_have_attribute("aria-label", f"웹 빌드 시각: {expected.removeprefix('Updated at ')}")
                assert marker.get_attribute("title").startswith("웹 빌드 시작 시각 · 표시 시간대: ")
                assert marker.get_attribute("aria-live") is None
                box = marker.bounding_box()
                area = page.locator("#slide-area").bounding_box()
                assert box["x"] >= 0 and box["x"] + box["width"] <= width, box
                assert box["y"] >= area["y"] + area["height"] + 1, (box, area)
                assert box["y"] + box["height"] <= height, box
                assert marker.evaluate("el => getComputedStyle(el).pointerEvents") == "none"
                assert marker.evaluate("el => el.tabIndex") == -1
            page.screenshot(path=str(artifact_dir / f"build-watermark-{width}x{height}.png"))
            page.reload()
            expect(page.locator(".deck-root")).to_have_attribute("data-hydrated", "true")
            expect(page.locator(".build-timestamp time")).to_have_attribute("datetime", built_at)
            expect(page.locator(".build-timestamp")).to_have_text(local_label(built_at, zone))
            page.clock.set_fixed_time(datetime(2040, 7, 1))
            expect(page.locator(".build-timestamp")).to_have_text(local_label(built_at, zone))
            assert not errors, errors
        finally:
            context.close()


    # With no JavaScript or unsupported timezone APIs, the same valid artifact
    # remains readable in UTC instead of showing a made-up time or Invalid Date.
    for javascript in [False, True]:
        context = browser.new_context(viewport={"width": 390, "height": 844}, timezone_id="Asia/Seoul", java_script_enabled=javascript)
        try:
            if javascript:
                context.add_init_script("""(() => {
                    const Original = Intl.DateTimeFormat;
                    Intl.DateTimeFormat = new Proxy(Original, {
                        construct(target, args) {
                            if (args[1]?.timeZoneName === 'shortOffset') throw new RangeError('unsupported timezone formatting');
                            return Reflect.construct(target, args);
                        }
                    });
                })();""")
            page = context.new_page()
            page.goto(f"{origin}/capstone#0")
            if javascript:
                expect(page.locator(".deck-root")).to_have_attribute("data-hydrated", "true")
            expect(page.locator(".build-timestamp")).to_have_text(f"Updated at {built_at[:10]} {built_at[11:19]} UTC")
            expect(page.locator(".build-timestamp time")).to_have_attribute("datetime", built_at)
        finally:
            context.close()
    print("Build timestamp local timezone and fallback browser checks passed")
