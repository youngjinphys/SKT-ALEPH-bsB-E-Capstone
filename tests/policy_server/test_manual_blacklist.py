"""Manual FQDN review and unsigned policy generation use the real compiler."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock
import json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'apps'/app/'src') for app in ('policy-server','policy-sync','dns-agent')]
from dns_agent.policy import parse_policy
from policy_server.console import ConsoleService,ConsoleConflict
from policy_server import intel

class ManualTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);root=Path(t.name)
        (root/'workspace').mkdir(mode=0o700)
        (root/'token').write_text('a'*64);(root/'token').chmod(0o600)
        self.service=ConsoleService(root/'workspace',root/'token')
    def candidate(self,domain='phishing-sample.example.net',**updates):
        p={'domain':domain,'reviewer':'Security operator','reason':'Reviewed synthetic domain and subtree collateral impact',
            'expires_at':(datetime.now(timezone.utc)+timedelta(hours=4)).isoformat(),
            'acknowledge_subtree':True,'expected_revision':self.service.manual_blacklist()['revision']}
        return {**p,**updates}
    def add(self,**updates):
        return self.service.save_manual_block({**self.candidate(**updates),'confirm':'UPSERT_MANUAL_SUBTREE'})
    def test_manual_only_draft_unsigned_and_archived(self):
        self.add()
        state=self.service.manual_blacklist();self.assertEqual(len(state['entries']),1)
        draft=self.service.build(dict(fingerprint=None,review_set_revision='NOT_PRESENT',
            manual_revision=state['revision'],confirm_replacement=True,acknowledge_user_notice=True))
        p=parse_policy(self.service.download(draft['draft']))
        self.assertEqual(p.blocked(datetime.now(timezone.utc)),('phishing-sample.example.net',))
        self.assertTrue(p.rules[0].evidence.startswith('manual-review-v1:sha256:'))
        self.assertFalse(draft['signed']);self.assertFalse(draft['published'])
    def test_bounds_preview_cas_remove_and_restore(self):
        original=self.service.manual_blacklist()['revision']
        p=self.candidate(); self.assertFalse(self.service.preview_manual_block(p)['enforcing'])
        self.add()
        with self.assertRaises(ConsoleConflict):
            self.service.save_manual_block({**p,'confirm':'UPSERT_MANUAL_SUBTREE'})
        for domain in ('co.uk','google.com','tenant.github.io','127.0.0.1','singlelabel'):
            with self.subTest(domain=domain),self.assertRaises(ValueError):
                self.service.preview_manual_block(self.candidate(domain))
        state=self.service.manual_blacklist()
        self.assertEqual(self.service.remove_manual_block({
            'domain':'phishing-sample.example.net','expected_revision':state['revision'],
            'confirm':'REMOVE_MANUAL_BLOCK'})['removed'],True)
        self.assertEqual(self.service.manual_blacklist()['entries'],[])
    def test_mixed_approved_gsb_and_manual_expiry_is_bounded(self):
        now=datetime.now(timezone.utc)
        u='https://phish-verified.example.org/login'
        collected=intel.collect_urls((u+'\n').encode(),source='openphish',fetched_at=now)
        verified=intel.verify_collected(collected,'testkey',checked_at=now,
            fetch=Mock(return_value=json.dumps({'threats':[{'url':u,'threatTypes':['SOCIAL_ENGINEERING']}],
                                                 'cacheDuration':'300s'}).encode()))
        intel.write_json(self.service.workspace/'verified.json',verified)
        template=intel.review_template(verified)
        template['reviews'][0].update(reviewer='Security operator',reason='Reviewed GSB result and subtree scope',
                                      approved=True,acknowledge_subtree=True)
        intel.write_json(self.service.workspace/'reviews.json',template)
        self.add();review=self.service.reviews();manual=self.service.manual_blacklist()
        draft=self.service.build(dict(fingerprint=review['fingerprint'],
            review_set_revision=review['review_set_revision'],manual_revision=manual['revision'],
            confirm_replacement=True,acknowledge_user_notice=True))
        p=parse_policy(self.service.download(draft['draft']))
        self.assertEqual(set(p.blocked(datetime.now(timezone.utc))),
                         {'phishing-sample.example.net','phish-verified.example.org'})
        self.assertLessEqual(p.expires_at,datetime.now(timezone.utc)+timedelta(minutes=6))
    def test_cloud_durable_snapshot_keeps_manual_registry(self):
        from cloud.state import MemoryStore,materialize
        store=MemoryStore()
        with materialize(store.load()['state']) as w:
            data=self.candidate()
            data['expected_revision']=w.service.manual_blacklist()['revision']
            w.service.save_manual_block({**data,'confirm':'UPSERT_MANUAL_SUBTREE'})
            store.save(0,w.export())
        with materialize(store.load()['state']) as w:
            self.assertEqual(len(w.service.manual_blacklist()['entries']),1)
