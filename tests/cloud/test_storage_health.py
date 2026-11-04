"""Metadata-only headroom; never return raw evidence, keys or retained file paths."""
import json
import unittest
try:
    from cloud.storage_health import storage_health
except ModuleNotFoundError:
    storage_health=None


class StorageHealthTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(storage_health), "durable storage metadata diagnostics are missing")

    def test_empty_state_is_valid_capacity_not_an_outage(self):
        state={'format':1,'files':{}}
        got=storage_health(state,max_bytes=8*1024*1024,max_files=512)
        self.assertEqual(got['state'],'NORMAL')
        self.assertEqual(got['file_count'],0)
        self.assertEqual(got['bytes_used'],len(json.dumps(state,ensure_ascii=True).encode()))
        self.assertEqual(got['bytes_limit'],8*1024*1024)
        self.assertFalse(got['automatic_cleanup'])

    def test_serialized_unicode_cost_matches_storage_enforcement(self):
        state={'format':1,'files':{'workspace/reviews.json':'{"reviewer":"운영자"}'}}
        got=storage_health(state,max_bytes=10000,max_files=512)
        self.assertEqual(got['bytes_used'],len(json.dumps(state,ensure_ascii=True).encode()))
        self.assertGreater(got['bytes_used'],len(json.dumps(state,ensure_ascii=False).encode()))

    def test_private_contents_and_file_names_are_never_disclosed(self):
        state={'format':1,'files':{
            'workspace/evidence-archive/private-run/verified.json':'https://sensitive.example/secret',
            'workspace/drafts/private-draft.json':'SUPER_SECRET',
            'policy-trust/'+'a'*64+'.pem':'PUBLIC KEY',
            'workspace/audit.jsonl':'actor@example.org'}}
        got=storage_health(state,max_bytes=10000,max_files=512)
        body=json.dumps(got)
        for forbidden in ('sensitive.example','SUPER_SECRET','private-run','private-draft','actor@example.org','a'*64):
            self.assertNotIn(forbidden,body)
        self.assertEqual(got['groups']['archives']['file_count'],1)
        self.assertEqual(got['groups']['drafts']['file_count'],1)
        self.assertEqual(got['groups']['trust']['file_count'],1)

    def test_file_and_byte_pressure_each_trigger_warning(self):
        state={'format':1,'files':{f'workspace/f{i}.json':'{}' for i in range(4)}}
        self.assertEqual(storage_health(state,max_bytes=100000,max_files=5)['state'],'WARNING')
        used=len(json.dumps(state,ensure_ascii=True).encode())
        self.assertEqual(storage_health(state,max_bytes=used,max_files=512)['state'],'CRITICAL')
        self.assertEqual(storage_health(state,max_bytes=used*2,max_files=512)['state'],'NORMAL')

    def test_bad_shapes_and_limits_are_not_reported_healthy(self):
        for state in ({}, {'format':True,'files':{}}, {'format':1,'files':[]},
                      {'format':1,'files':{'x':None}}):
            with self.subTest(state=state),self.assertRaises(ValueError):
                storage_health(state,max_bytes=10000,max_files=512)
        for kwargs in ({'max_bytes':0,'max_files':512},{'max_bytes':10000,'max_files':False}):
            with self.assertRaises(ValueError):storage_health({'format':1,'files':{}},**kwargs)

if __name__=='__main__':unittest.main()
