"""Offline tests: exact Google response, freshness, scope, authorization, I/O."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'apps/policy-server/src'), str(ROOT/'apps/dns-agent/src')]
from policy_server import intel as m
NOW=datetime(2026,10,29,1,0,0,tzinfo=timezone.utc)
URL='https://malicious-example-domain.online/secure/login'
URL2='http://another-phish-example.biz/'

def feed(urls=None):
    return m.collect_urls(('\n'.join(urls or [URL,URL2])+'\n').encode(),
                          source='local-openphish',fetched_at=NOW)

def matched(u):
    return {'threats':[{'url':u,'threatTypes':['SOCIAL_ENGINEERING']}],
            'cacheDuration':'300s'}

def verified(urls=None,response=None):
    obj=feed(urls)
    def remote(address,headers=None,limit=0):
        assert address.startswith(m.GOOGLE+'?')
        assert headers['x-goog-api-key']=='mock-key'
        return json.dumps(response or matched((urls or [URL])[0])).encode()
    return m.verify_collected(obj,'mock-key',fetch=remote,checked_at=NOW)

def approval(v,idx=0):
    a=m.review_template(v)
    r=a['reviews'][idx]
    r.update(approved=True,acknowledge_subtree=True,reviewer='Human Reviewer',
             reason='Manually verified this entire dedicated domain is safe to block')
    return a

class RealThreatPipelineTests(unittest.TestCase):
    def test_parse_feed_filters_invalid_deduplicates_and_does_not_fetch_sites(self):
        raw=f'# comment\n{URL}\n{URL}\nftp://evil.example.org/x\nhttp://127.0.0.1/\n'.encode()
        s=m.collect_urls(raw,source='local-openphish',fetched_at=NOW)
        self.assertEqual(len(s['entries']),1)
        self.assertEqual(s['rejected_count'],2)
        self.assertEqual(s['entries'][0]['domain'],'malicious-example-domain.online')

    def test_reject_url_credentials_unicode_port_and_controls(self):
        for url in ['https://bob:secret@foo.example.net/',
                    'http://foo.example.net:8000/a',
                    'https://evil.test/',
                    'https://good.example.net\nHTTP:evil',
                    'https://localhost/',
                    'http://[::1]/',
                    'https://exämple.de/',
                    'https://x.example.org/ hi',
                    'https://aa..bb/']:
            with self.subTest(url=url),self.assertRaises(m.IntelError):
                m.safe_url(url)

    def test_collect_only_openphish_remote_with_terms(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'collected.json'
            with patch.object(m,'get_https',return_value=(URL+'\n').encode()) as request:
                self.assertEqual(m.main(['collect','--source','openphish',
                                         '--accept-openphish-terms','--output',str(target)]),0)
                request.assert_called_once_with(m.OPENPHISH)
            self.assertEqual(target.stat().st_mode&0o777,0o600)
            self.assertEqual(len(m.read_json(target)['entries']),1)
            other=Path(folder)/'other.json'
            with patch.object(m,'get_https',side_effect=AssertionError('no fetching')):
                self.assertEqual(m.main(['collect','--source','openphish','--output',str(other)]),2)
            self.assertFalse(other.exists())

    def test_google_exact_match_with_no_automatic_approval(self):
        v=verified([URL],matched(URL))
        self.assertEqual(v['entries'][0]['status'],'MATCH')
        self.assertEqual(v['entries'][0]['threat_types'],['SOCIAL_ENGINEERING'])
        self.assertEqual(m.review_template(v)['reviews'][0]['approved'],False)
        self.assertEqual(m.review_template(v)['reviews'][0]['acknowledge_subtree'],False)
        self.assertEqual(len(v['entries']),1)

    def test_google_expression_response_is_not_assigned_to_query(self):
        v=verified([URL],{'threats':[{'url':'https://malicious-example-domain.online/','threatTypes':['SOCIAL_ENGINEERING']}],
                          'cacheDuration':'300s'})
        self.assertEqual(v['entries'][0]['status'],'UNRESOLVED')
        self.assertEqual(v['unassigned_expressions'],1)
        self.assertEqual(m.review_template(v)['reviews'],[])

    def test_batch_lookups_limited_and_bounded(self):
        entries=[{'url':f'https://host{i}.example.net/x','domain':f'host{i}.example.net',
                  'source':'local-openphish','url_sha256':'x'} for i in range(38)]
        result=list(m.batches(entries,maximum=15))
        self.assertEqual(list(map(len,result)),[15,15,8])
        self.assertTrue(all(len(m.GOOGLE+'?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode([('urls',x['url']) for x in batch])) < m.MAX_LOOKUP_URL for batch in result))

    def test_google_negative_does_not_mean_safe_and_expires(self):
        v=verified([URL],{'threats':[],'cacheDuration':'7s'})
        self.assertEqual(v['entries'][0]['status'],'NO_MATCH')
        self.assertEqual(m.parse_time(v['entries'][0]['valid_until'])-NOW,timedelta(seconds=7))
        self.assertEqual(m.review_template(v)['reviews'],[])

    def test_google_overlong_duration_is_capped_to_thirty_minutes(self):
        v=verified([URL],{'threats':[{'url':URL,'threatTypes':['SOCIAL_ENGINEERING']}],
                          'cacheDuration':'3600s'})
        self.assertEqual(m.parse_time(v['entries'][0]['valid_until'])-NOW,timedelta(minutes=30))

    def test_api_error_never_emits_partial_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'input.json';b=Path(folder)/'output.json'
            m.write_json(a,feed([URL,URL2]))
            with patch.dict('os.environ',{'SAFE_BROWSING_API_KEY':'secret-api-key'}),patch.object(
                    m,'get_https',side_effect=m.IntelError('network request failed')):
                self.assertEqual(m.main(['verify','--input',str(a),'--output',str(b),
                                         '--ack-url-disclosure','--ack-noncommercial-use']),2)
            self.assertFalse(b.exists())

    def test_approval_bound_to_exact_verification_and_requires_ack(self):
        v=verified([URL],matched(URL))
        r=approval(v)
        p=m.build_policy(v,r,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)
        self.assertEqual(p['rules'][0]['decision'],'BLOCK')
        self.assertEqual(p['rules'][0]['scope'],'SUBTREE')
        self.assertEqual(p['rules'][0]['domain'],'malicious-example-domain.online')
        self.assertLessEqual(m.parse_time(p['expires_at'])-NOW,timedelta(minutes=15))
        for field,bad in [('url_sha256','f'*64),('checked_at','2000-01-01T00:00:00Z')]:
            q=json.loads(json.dumps(r))
            q['reviews'][0][field]=bad
            with self.subTest(field=field),self.assertRaises(m.IntelError):
                m.build_policy(v,q,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)

    def test_missing_expired_google_evidence_cannot_compile(self):
        v=verified([URL],matched(URL))
        r=approval(v)
        with self.assertRaisesRegex(m.IntelError,'stale'):
            m.build_policy(v,r,at=NOW+timedelta(minutes=6),acknowledge_replacement=True,acknowledge_notice=True)
        with self.assertRaises(m.IntelError):
            m.build_policy(v,r,at=NOW,acknowledge_replacement=True,acknowledge_notice=False)
        with self.assertRaises(m.IntelError):
            m.build_policy(v,r,at=NOW,acknowledge_replacement=False)

    def test_google_negative_and_unreviewed_never_block(self):
        v=verified([URL],{'threats':[],'cacheDuration':'300s'})
        a=m.review_template(v)
        with self.assertRaises(m.IntelError):
            m.build_policy(v,a,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)
        v=verified([URL],matched(URL))
        a=m.review_template(v)
        with self.assertRaises(m.IntelError):
            m.build_policy(v,a,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)

    def test_protected_shared_hosts_are_never_dns_blocked(self):
        for url in ['https://badaccount.github.io/landing',
                    'https://evil.pages.dev/login','https://www.google.com/account']:
            v=verified([url],matched(url))
            with self.subTest(url=url),self.assertRaisesRegex(m.IntelError,'shared-platform'):
                m.build_policy(v,approval(v),at=NOW,acknowledge_replacement=True,acknowledge_notice=True)

    def test_false_approval_or_unacknowledged_subtree_refused(self):
        v=verified([URL],matched(URL))
        a=approval(v);a['reviews'][0]['acknowledge_subtree']=False
        with self.assertRaises(m.IntelError):
            m.build_policy(v,a,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)
        a=approval(v);a['reviews'][0]['reason']='short'
        with self.assertRaises(m.IntelError):
            m.build_policy(v,a,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)

    def test_output_private_atomic_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            destination=Path(folder)/'artifact.json';victim=Path(folder)/'outside'
            victim.write_text('do not touch')
            destination.symlink_to(victim)
            with self.assertRaises(m.IntelError):m.write_json(destination,{'x':1})
            self.assertEqual(victim.read_text(),'do not touch')
            destination.unlink()
            m.write_json(destination,{'hello':'world'})
            self.assertEqual(m.read_json(destination),{'hello':'world'})
            self.assertEqual(destination.stat().st_mode&0o777,0o600)

    def test_unknown_google_threat_type_is_not_a_clean_verdict(self):
        v=verified([URL],{'threats':[{'url':URL,'threatTypes':['FUTURE_THREAT_TYPE']}],
                          'cacheDuration':'100s'})
        self.assertEqual(v['entries'][0]['status'],'UNRESOLVED')
        self.assertEqual(m.review_template(v)['reviews'],[])

    def test_partial_google_batch_failure_is_fail_closed(self):
        inputs=[f'https://test{i}.some-domain.org/' for i in range(20)]
        artifact=feed(inputs)
        count=[0]
        def server(url,headers=None,limit=0):
            count[0]+=1
            if count[0]==2:raise m.IntelError('API unavailable')
            return json.dumps({'threats':[],'cacheDuration':'10s'}).encode()
        with self.assertRaises(m.IntelError):
            m.verify_collected(artifact,'key',fetch=server,checked_at=NOW)
        self.assertEqual(count[0],2)

    def test_local_artifacts_cannot_be_saved_to_unignored_repo_location(self):
        root=Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(m.IntelError,'outside the repository'):
            m.write_json(root/'candidate_private_urls.json',{'secret':'no'})
        self.assertFalse((root/'candidate_private_urls.json').exists())

    def test_invalid_unknown_response_fields_or_duration_rejected(self):
        for value in [{'threats': [],'cacheDuration':'not-a-duration'},
                      {'threats':'bad','cacheDuration':'300s'},
                      {'threats':[],'cacheDuration':'0s'},
                      {'threats':[],'cacheDuration':'30s','newDanger':'yes'},
                      {'threats':[{'url':URL,'threatTypes':'SOCIAL_ENGINEERING'}],
                       'cacheDuration':'300s'}]:
            with self.subTest(value=value),self.assertRaises(m.IntelError):
                m.parse_google_response(json.dumps(value).encode(),[{'url':URL}],NOW)

    def test_strict_json_duplicate_keys_and_oversize(self):
        for data in [b'{"a":1,"a":2}', b'{"a":NaN}',b'[]'+b' '*m.MAX_ARTIFACT_BYTES]:
            with self.assertRaises(m.IntelError):m.parse_json(data)

    def test_compile_emits_valid_dns_contract_when_local_agent_available(self):
        v=verified([URL],matched(URL));a=approval(v)
        p=m.build_policy(v,a,at=NOW,acknowledge_replacement=True,acknowledge_notice=True)
        root=Path(__file__).resolve().parents[2]
        candidate=root/'apps/dns-agent/src'
        if not candidate.exists():self.skipTest('dns agent unavailable in local fixture')
        sys.path.insert(0,str(candidate))
        from dns_agent.policy import parse_policy
        self.assertEqual(parse_policy(json.dumps(p).encode(),now=NOW).blocked(NOW),
                         ('malicious-example-domain.online',))

if __name__=='__main__': unittest.main()
