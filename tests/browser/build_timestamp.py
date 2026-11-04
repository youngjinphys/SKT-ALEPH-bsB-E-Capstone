"""Read-only HTTP checks of a built artifact; no browser, account or deployment.

Run after npm run build in apps/web. Starting the same artifact with conflicting
runtime metadata and timezones must not change its recorded build-server time.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps/web"
PORT = int(os.environ.get("ALEPH_BUILD_TEST_PORT", "18770"))
ORIGIN = f"http://127.0.0.1:{PORT}"
OPENER = build_opener(ProxyHandler({}))


class BuildTimeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_marker = False
        self.markers = 0
        self.times = []
        self.text = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "small" and attrs.get("class") == "build-timestamp":
            self.in_marker = True
            self.markers += 1
        if tag == "time" and self.in_marker:
            self.times.append(attrs.get("datetime"))

    def handle_endtag(self, tag):
        if tag == "small":
            self.in_marker = False

    def handle_data(self, data):
        if self.in_marker:
            self.text += data


def fetch(path):
    with OPENER.open(f"{ORIGIN}{path}", timeout=20) as response:
        assert response.status == 200
        return response.read().decode()


def check_artifact():
    metadata = json.loads((WEB / ".next/required-server-files.json").read_text())
    built_at = metadata["config"]["env"]["NEXT_PUBLIC_ALEPH_BUILD_TIME"]
    parsed = datetime.fromisoformat(built_at.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc, built_at
    assert parsed <= datetime.now(timezone.utc), "Build time cannot be in the future"
    label = parsed.strftime("Updated at %Y-%m-%d %H:%M:%S UTC")
    results = []
    for zone in ["Asia/Seoul", "America/Los_Angeles"]:
        env = dict(os.environ, TZ=zone, NEXT_PUBLIC_ALEPH_BUILD_TIME="1999-01-01T00:00:00.000Z")
        with tempfile.TemporaryFile(mode="w+") as log:
            server = subprocess.Popen(
                ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(PORT)],
                cwd=WEB, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        log.seek(0)
                        raise AssertionError(log.read())
                    try:
                        fetch("/capstone")
                        break
                    except (URLError, TimeoutError):
                        time.sleep(0.1)
                else:
                    raise AssertionError("Local production server did not become ready")
                for path in ["/", "/capstone", "/fishing", "/capstone"]:
                    parser = BuildTimeParser()
                    parser.feed(fetch(path))
                    assert parser.markers == 1, (zone, path, parser.markers)
                    assert parser.times == [built_at], (zone, path, parser.times, built_at)
                    assert parser.text == label, (zone, path, parser.text, label)
                    results.append({"zone": zone, "path": path, "builtAt": built_at})
                time.sleep(1.1)
                parser = BuildTimeParser()
                parser.feed(fetch("/capstone"))
                assert parser.times == [built_at]
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    print(json.dumps({"passed": len(results) + 2, "results": results}, indent=2))


if __name__ == "__main__":
    check_artifact()
