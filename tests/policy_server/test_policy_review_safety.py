"""Offline regressions for manual boundaries, provenance and explicit withdrawals."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps'/app/'src') for app in ('policy-server','policy-sync','dns-agent')]
from dns_agent.policy import parse_policy
from policy_server import intel,manual_blacklist,public_suffix
from policy_server.console import ConsoleService,ConsoleConflict,_revision


class PolicyReviewSafetyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);workspace=self.root/'workspace';workspace.mkdir(mode=0o700)
        token=self.root/'token';token.write_text('a'*64);token.chmod(0o600)
        self.service=ConsoleService(workspace,token)

    def add(self,domain='incident.example.net',**changes):
        request=dict(domain=domain,reviewer='Original reviewer',reason='Reviewed dedicated domain and all subtree collateral impact',
            expires_at=intel.iso(datetime.now(timezone.utc)+timedelta(hours=4)),acknowledge_subtree=True,
            expected_revision=self.service.manual_blacklist()['revision'],confirm='UPSERT_MANUAL_SUBTREE')
        return self.service.save_manual_block({**request,**changes})

    def request(self,**changes):
        r=self.service.reviews()
        return dict(fingerprint=r['fingerprint'],review_set_revision=r['review_set_revision'] or 'NOT_PRESENT',
            manual_revision=self.service.manual_blacklist()['revision'],confirm_replacement=True,
            acknowledge_user_notice=True,**changes)

    def remove(self,domain='incident.example.net'):
        return self.service.remove_manual_block(dict(domain=domain,
            expected_revision=self.service.manual_blacklist()['revision'],confirm='REMOVE_MANUAL_BLOCK'))

    def evidence(self,*,age=timedelta(minutes=10),duration='300s',domain='gsb.example.net'):
        now=datetime.now(timezone.utc)-age;url='https://'+domain+'/login'
        source=intel.collect_urls((url+'\n').encode(),source='openphish',fetched_at=now)
        v=intel.verify_collected(source,'fixture-key',checked_at=now,fetch=Mock(return_value=json.dumps(
            {'threats':[{'url':url,'threatTypes':['SOCIAL_ENGINEERING']}],'cacheDuration':duration}).encode()))
        r=intel.review_template(v)
        r['reviews'][0].update(approved=True,acknowledge_subtree=True,reviewer='GSB reviewer',
            reason='Reviewed this synthetic evidence and complete subtree scope')
        intel.write_json(self.service.workspace/'verified.json',v)
        intel.write_json(self.service.workspace/'reviews.json',r)
        return self.service.reviews()['items'][0]

    def test_public_suffixes_and_private_wildcards_rejected(self):
        for domain in ('com.sg','org.sg','co.uk','foo.ck','kawasaki.jp','foo.kawasaki.jp','s3.amazonaws.com'):
            with self.subTest(domain=domain),self.assertRaises(ValueError):self.add(domain)
        for domain in ('reviewed.com.sg','www.ck','city.kawasaki.jp'):
            with self.subTest(domain=domain):self.add(domain)
        self.assertEqual(len(self.service.manual_blacklist()['entries']),3)

    def test_psl_private_rule_outside_legacy_denylist(self):
        self.assertTrue(public_suffix.is_public_suffix('duckdns.org'))
        with self.assertRaises(ValueError):self.add('duckdns.org')
        self.assertFalse(public_suffix.is_public_suffix('reviewed.duckdns.org'))

    def test_missing_or_tampered_psl_fails_closed_without_network(self):
        public_suffix._rules.cache_clear()
        self.addCleanup(public_suffix._rules.cache_clear)
        with patch.object(public_suffix,'PSL_PATH',self.root/'missing'):
            with self.assertRaises(FileNotFoundError):public_suffix.is_public_suffix('com.sg')
        bad=self.root/'bad-list';bad.write_text('sg\n')
        with patch.object(public_suffix,'PSL_PATH',bad):
            with self.assertRaisesRegex(ValueError,'integrity'):public_suffix.is_public_suffix('com.sg')

    def test_legacy_unsafe_record_remains_readable_removable_but_not_buildable(self):
        self.add();data=manual_blacklist.records(self.service);data['entries'][0]['domain']='com.sg'
        intel.write_json(self.service.workspace/'manual-blacklist.json',data)
        self.assertTrue(self.service.manual_blacklist()['entries'][0]['unsafe_boundary'])
        with self.assertRaises(ValueError):self.service.build(self.request())
        self.assertTrue(self.remove('com.sg')['removed'])

    def test_remove_last_rule_requires_separate_empty_confirmation(self):
        self.add();self.service.build(self.request());self.remove()
        with self.assertRaisesRegex(ValueError,'explicit empty'):self.service.build(self.request())
        result=self.service.build(self.request(confirm_empty_replacement=True))
        policy=parse_policy(self.service.download(result['draft']))
        self.assertEqual(policy.rules,())
        self.assertEqual(policy.expires_at-policy.issued_at,timedelta(minutes=15))
        self.assertFalse(result['signed']);self.assertFalse(result['published'])
        self.assertTrue(result['empty_replacement'])

    def test_empty_confirmation_requires_current_revisions_and_actual_empty_sources(self):
        request=self.request(confirm_empty_replacement=True)
        no_revision={k:v for k,v in request.items() if k!='manual_revision'}
        with self.assertRaises(ConsoleConflict):self.service.build(no_revision)
        self.add()
        with self.assertRaises(ConsoleConflict):self.service.build(request)
        with self.assertRaises(ConsoleConflict):self.service.build(self.request(confirm_empty_replacement=True))
        with self.assertRaises(ValueError):self.service.build(self.request(confirm_empty_replacement='true'))

    def test_manual_evidence_survives_edits_removal_and_cloud_roundtrip(self):
        from cloud.state import MemoryStore,materialize
        self.add();before=manual_blacklist.records(self.service)['entries'][0]
        result=self.service.build(self.request())
        evidence=json.loads(self.service.download(result['draft']))['rules'][0]['evidence']
        self.add(reviewer='Second reviewer',reason='Second independently reviewed rationale for the same domain')
        after=manual_blacklist.records(self.service)['entries'][0];self.remove()
        for record in (before,after):
            blob=json.loads((self.service.workspace/'manual-evidence'/(_revision(record)+'.json')).read_text())
            self.assertEqual(blob,record)
        self.assertEqual(evidence,'manual-review-v1:sha256:'+_revision(before))
        manifest=json.loads((self.service.workspace/'draft-evidence'/result['draft']).read_text())
        self.assertEqual(manifest['sources']['incident.example.net'],[evidence])
        state={'format':1,'files':{'workspace/'+p.relative_to(self.service.workspace).as_posix():p.read_text()
            for p in self.service.workspace.rglob('*') if p.is_file() and p.suffix in ('.json','.jsonl')}}
        store=MemoryStore();store.save(0,state)
        with materialize(store.load()['state']) as w:
            self.assertEqual(json.loads((w.service.workspace/'manual-evidence'/(_revision(before)+'.json')).read_text()),before)

    def test_archive_failure_or_collision_prevents_registry_mutation(self):
        self.add();before=manual_blacklist.records(self.service)
        with patch.object(manual_blacklist,'archive',side_effect=OSError('fixture disk full')):
            with self.assertRaises(OSError):self.add(reviewer='Other reviewer')
            with self.assertRaises(OSError):self.remove()
        self.assertEqual(manual_blacklist.records(self.service),before)
        path=self.service.workspace/'manual-evidence'/(_revision(before['entries'][0])+'.json')
        path.write_text('{}');path.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'archive mismatch'):self.remove()
        self.assertEqual(manual_blacklist.records(self.service),before)

    def test_archive_rejects_same_python_value_with_different_canonical_hash(self):
        self.add();record=manual_blacklist.records(self.service)['entries'][0]
        path=self.service.workspace/'manual-evidence'/(_revision(record)+'.json')
        changed={**record,'acknowledge_subtree':1}
        self.assertEqual(changed,record)
        path.write_text(json.dumps(changed));path.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'archive mismatch'):self.remove()

    def test_archive_does_not_write_private_evidence_into_public_repository(self):
        self.add();record=manual_blacklist.records(self.service)['entries'][0]
        with patch.object(intel,'ROOT',self.root):
            with self.assertRaisesRegex(ValueError,'outside the repository'):
                manual_blacklist.archive(self.service,record)

    def test_stale_gsb_does_not_block_manual_after_exact_explicit_exclusion(self):
        item=self.evidence();self.add()
        with self.assertRaisesRegex(ValueError,'stale'):self.service.build(self.request())
        request=self.request(excluded_expired_review_ids=[item['id']])
        result=self.service.build(request)
        self.assertEqual(result['manual_rules'],1);self.assertEqual(result['verified_rules'],0)
        self.assertTrue(self.service.reviews()['items'][0]['approved'])
        self.assertEqual(result['excluded_expired_review_ids'],[item['id']])

    def test_excluding_all_stale_approvals_requires_empty_confirmation_too(self):
        item=self.evidence();request=self.request(excluded_expired_review_ids=[item['id']])
        with self.assertRaisesRegex(ValueError,'explicit empty'):self.service.build(request)
        self.assertEqual(self.service.build({**request,'confirm_empty_replacement':True})['rules'],0)

    def test_unknown_duplicate_or_current_exclusion_is_rejected(self):
        item=self.evidence(age=timedelta(seconds=5));self.add()
        for refs in ([item['id']],['0'*64],[item['id'],item['id']]):
            with self.subTest(refs=refs),self.assertRaises(ValueError):
                self.service.build(self.request(excluded_expired_review_ids=refs))

    def test_exclusion_never_bypasses_review_integrity_or_revision(self):
        item=self.evidence();self.add();request=self.request(excluded_expired_review_ids=[item['id']])
        r=json.loads((self.service.workspace/'reviews.json').read_text())
        r['reviews'][0]['reason']='bad';intel.write_json(self.service.workspace/'reviews.json',r)
        with self.assertRaises(ConsoleConflict):self.service.build(request)
        with self.assertRaisesRegex(ValueError,'rationale'):
            self.service.build(self.request(excluded_expired_review_ids=[item['id']]))

    def test_mixed_current_and_expired_gsb_preserves_current_source_and_manual(self):
        from copy import deepcopy
        import hashlib
        self.evidence();v=json.loads((self.service.workspace/'verified.json').read_text())
        fresh=deepcopy(v['entries'][0]);url='https://fresh.example.net/login'
        fresh.update(domain='fresh.example.net',url=url,url_sha256=hashlib.sha256(url.encode()).hexdigest(),
                     valid_until=intel.iso(datetime.now(timezone.utc)+timedelta(minutes=5)))
        v['entries'].append(fresh);r=intel.review_template(v)
        for row in r['reviews']:
            row.update(approved=True,acknowledge_subtree=True,reviewer='Fixture reviewer',
                reason='Reviewed synthetic matching evidence and subtree impact')
        intel.write_json(self.service.workspace/'verified.json',v)
        intel.write_json(self.service.workspace/'reviews.json',r);self.add()
        expired=next(row for row in self.service.reviews()['items'] if not row['eligible'])
        result=self.service.build(self.request(excluded_expired_review_ids=[expired['id']]))
        self.assertEqual((result['verified_rules'],result['manual_rules']),(1,1))
        self.assertEqual(set(parse_policy(self.service.download(result['draft'])).blocked(datetime.now(timezone.utc))),
                         {'fresh.example.net','incident.example.net'})

    def test_combined_source_manifest_resolves_manual_record_hash(self):
        self.evidence(age=timedelta(seconds=5),domain='incident.example.net');self.add()
        result=self.service.build(self.request());policy=json.loads(self.service.download(result['draft']))
        manifest=json.loads((self.service.workspace/'draft-evidence'/result['draft']).read_text())
        refs=manifest['sources']['incident.example.net']
        self.assertEqual(len(refs),2)
        self.assertEqual(policy['rules'][0]['evidence'],'source-combined-v1:sha256:'+_revision({'sources':refs}))
        manual_ref=next(ref for ref in refs if ref.startswith('manual-review-v1:'))
        record=json.loads((self.service.workspace/'manual-evidence'/(manual_ref.rsplit(':',1)[1]+'.json')).read_text())
        self.assertEqual(manual_ref,'manual-review-v1:sha256:'+_revision(record))

    def test_psl_guard_also_rejects_verified_public_suffix_approval(self):
        self.evidence(age=timedelta(seconds=5),domain='com.sg')
        with self.assertRaisesRegex(ValueError,'SUBTREE'):self.service.build(self.request())
