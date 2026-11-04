"""Read-only receiver reachability checks: no key, report, or database access.

A successful GET proves only TLS/routing/clock compatibility. It does not enroll
or attest a DNS node. Redirects and proxy environment variables are not followed.
"""
from datetime import datetime, timezone
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from .snapshot import strict_load, timestamp

SERVICE = 'aleph-signed-node-receiver'


def health_payload(now=None):
    return {'service': SERVICE, 'formats': [1, 2, 3, 4], 'metrics_format': 4,
            'enrollment_required': True, 'storage': 'not_checked',
            'server_time': (now or datetime.now(timezone.utc)).isoformat()}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_health(url):
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    try:
        with opener.open(req, timeout=8) as response:
            if response.status != 200 or response.headers.get_content_type() != 'application/json':
                raise ValueError('Expected receiver JSON; check production routing and deployment protection')
            return strict_load(response.read(4097), limit=4096)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Receiver HTTP {exc.code}; check the production endpoint, TLS and deployment protection') from None
    except (urllib.error.URLError, OSError) as exc:
        raise ValueError('Receiver unreachable; check local DNS, outbound HTTPS, certificate trust and server clock') from exc


def check_receiver(url, *, now=None):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path != '/v1/nodes/report'):
        raise ValueError('Receiver must be an exact HTTPS /v1/nodes/report URL')
    value = fetch_health(url)
    expected = {'service','formats','metrics_format','enrollment_required','storage','server_time'}
    if (type(value) is not dict or set(value) != expected or value['service'] != SERVICE
            or type(value['formats']) is not list or 4 not in value['formats']
            or any(type(item) is not int for item in value['formats'])
            or value['metrics_format'] != 4 or value['enrollment_required'] is not True
            or value['storage'] != 'not_checked'):
        raise ValueError('Unexpected receiver capabilities; no node settings were changed')
    instant = now or datetime.now(timezone.utc)
    skew = (timestamp(value['server_time'], 'receiver time') - instant).total_seconds()
    if abs(skew) > 60:
        raise ValueError('Receiver/local clock differs by over 60 seconds; synchronize NTP before reporting')
    return {'reachable': True, 'clock_skew_s': round(skew, 3), 'metrics_format': 4,
            'storage': 'not_checked', 'node_registration': 'not_checked'}
