import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sync_config as c

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.settings={'ryujinx_dir':str(self.root),'account_path':'/save:/Player ['+'A'*32+']/files','games':{}}
        self.uid=(7).to_bytes(16,'little').hex();self.settings['deck_profile_uid']=self.uid
        for folder,title,kind,uid in [('one',0x100,1,self.uid),('bcat',0x200,2,'0'*32),('device',0x300,3,'0'*32),('other',0x400,1,(8).to_bytes(16,'little').hex())]:
            p=self.root/'bis/user/save'/folder;(p/'0').mkdir(parents=True)
            data=bytearray(512);data[:8]=title.to_bytes(8,'little');data[8:24]=bytes.fromhex(uid);data[32]=kind
            (p/'ExtraData0').write_bytes(data)
        (self.root/'system').mkdir()
        (self.root/'system/Profiles.json').write_text(json.dumps({'profiles':[{'user_id':'00000000000000070000000000000000','name':'Player Seven'}]}))
    def tearDown(self):self.tmp.cleanup()
    def test_account_only_and_profile_name(self):
        self.assertEqual({x['save_id'] for x in c.local_saves(self.settings)},{'one','other'})
        self.assertEqual(next(x['name'] for x in c.local_profiles(self.settings) if x['uid']==self.uid),'Player Seven')
    def test_all_switch_games_but_only_matching_local_owner_available(self):
        class FTP:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def cwd(self,p):pass
            def nlst(self):return ['Example [0000000000000100]','Other [0000000000000400]','Remote only [0000000000000900]']
        with patch.object(c,'connect',return_value=FTP()):games=c.discover_games(self.settings)
        self.assertEqual(len(games),3);self.assertEqual(games[0]['name'],'Example')
        self.assertEqual([g['available'] for g in games],[True,False,False])
        self.assertEqual(games[0]['remote_name'],'Example [0000000000000100]')
    def test_address_changes_and_invalid_addresses(self):
        self.assertEqual(c.parse_endpoint(' 10.0.0.25:5021 '),('10.0.0.25',5021))
        for value in ['10.0.0.25:0','10.0.0.25:65536','999.0.0.1:5000','10.0.0.25','ftp://10.0.0.25:5000']:
            with self.assertRaises(c.core.SyncError):c.parse_endpoint(value)
    def test_keys_separate_both_profiles(self):
        game=c.local_saves(self.settings)[0];one=c.game_key(game,self.settings['account_path'])
        self.assertNotEqual(one,c.game_key(game,self.settings['account_path'].replace('A','B')))
        self.assertNotEqual(one,c.game_key(dict(game,user_id='0'*32),self.settings['account_path']))
    def test_migration_preserves_baseline_and_backup(self):
        home=self.root/'app';home.mkdir();game=next(x for x in c.local_saves(self.settings) if x['save_id']=='one')
        settings=dict(self.settings,games={'old':game})
        (home/'settings.json').write_text(json.dumps(settings));(home/'state.json').write_text(json.dumps({'old':{'hash':'baseline'}}))
        result=c.load_or_create(home);key=next(iter(result['games']))
        self.assertEqual(json.loads((home/'state.json').read_text())[key],{'hash':'baseline'})
        self.assertTrue(list((home/'configuration-backups').glob('*/settings.json')))
        self.assertEqual(c.load_or_create(home),result)

if __name__=='__main__':unittest.main()
