import copy
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import card_library as c

def dump(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))

class CartridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.local=self.base/'host';self.local.mkdir();self.root=self.base/'Ryujinx';self.root.mkdir()
        dump(self.root/'Config.json',{'input_config':[{'gyro':'CemuHook'}],'game_dirs':[]})
        self.host={'slot':{'kind':'mmc'},'ryujinx_dir':str(self.root)}
    def tearDown(self):self.tmp.cleanup()
    def cartridge(self,name,ident,profile):
        p=self.base/name;p.mkdir()
        for rel in ['data/bis/user/save','data/system','data/mods','data/sdcard','roms','sync']:(p/rel).mkdir(parents=True)
        (p/'data/system/profile').write_text(profile)
        dump(p/'sync/settings.json',{'host':profile,'games':{},'account_path':profile})
        dump(p/'sync/state.json',{'proof':profile})
        (p/'roms/Game [0000000000000100].xci').write_bytes(b'fixture')
        manifest={'schema':2,'kind':'switch-library','library_id':ident*32,'data_dir':'data','rom_dir':'roms','sync_dir':'sync',
            'games':[{'title_id':'0000000000000100','rom':'Game [0000000000000100].xci'}],
            'game_metadata':{'0000000000000100/updates.json':{'selected':'@CARD@/roms/update.nsp'}}}
        (p/'roms/update.nsp').write_bytes(b'fixture update');dump(p/'.switch-library.json',manifest)
        return p,manifest
    def disks(self,mount,uuid='new-card',usb=None):
        values=[{'name':'mmcblk0','path':'/dev/mmcblk0','tran':'mmc','type':'disk','children':[
            {'path':'/dev/mmcblk0p1','type':'part','fstype':'ext4','uuid':uuid,'mountpoints':[str(mount)]}]}]
        if usb:values.append({'name':'sda','path':'/dev/sda','tran':'usb','type':'disk','children':[
            {'path':'/dev/sda1','type':'part','fstype':'ext4','uuid':'usb','mountpoints':[str(usb)]}]})
        return values
    def test_replacement_card_new_uuid_is_accepted_without_registration(self):
        card,m=self.cartridge('larger','a','profile-A');m['card_uuid']='old-uuid';dump(card/'.switch-library.json',m)
        found,_,_=c.locate(self.host,False,self.disks(card,'different-new-uuid'));self.assertEqual(found,card)
    def test_completely_different_library_is_accepted(self):
        a,_=self.cartridge('a','a','profile-A');b,_=self.cartridge('b','b','profile-B')
        for card in [a,b]:self.assertEqual(c.locate(self.host,False,self.disks(card))[0],card)
    def test_internal_slot_has_priority_over_usb(self):
        a,_=self.cartridge('slot','a','profile-A');b,_=self.cartridge('usb','b','profile-B')
        self.assertEqual(c.locate(self.host,False,self.disks(a,usb=b))[0],a)
    def test_steam_card_in_slot_does_not_fall_back_to_usb_switch_card(self):
        steam=self.base/'steam';steam.mkdir();usb,_=self.cartridge('usb','b','profile-B')
        with self.assertRaises(c.LibraryError):c.locate(self.host,False,self.disks(steam,usb=usb))
    def test_absent_card_does_not_create_local_saves(self):
        before=set(self.base.rglob('*'))
        with self.assertRaises(c.LibraryError):c.prepare(self.host,self.local,False,[])
        self.assertEqual(before,set(self.base.rglob('*')))
    def test_malformed_card_does_not_redirect_current_profile(self):
        card,m=self.cartridge('invalid','a','profile-A');m['data_dir']='../outside';dump(card/'.switch-library.json',m)
        with self.assertRaises(c.LibraryError):c.prepare(self.host,self.local,False,self.disks(card))
        self.assertFalse((self.local/'card').exists())
    def test_external_profile_symlink_is_rejected(self):
        card,_=self.cartridge('card','a','profile-A');outside=self.base/'outside';outside.mkdir()
        (card/'data/system/profile').unlink();(card/'data/system').rmdir();(card/'data/system').symlink_to(outside)
        with self.assertRaises(c.LibraryError):c.locate(self.host,False,self.disks(card))
    def test_two_libraries_do_not_mix_profile_dlc_cache_or_sync_state(self):
        a,ma=self.cartridge('a','a','profile-A');b,mb=self.cartridge('b','b','profile-B')
        ma['game_metadata']['0000000000000100/dlc.json']=[{'path':'@CARD@/roms/dlc.nsp'}];dump(a/'.switch-library.json',ma)
        c.prepare(self.host,self.local,False,self.disks(a))
        (self.root/'games/cache-proof').write_text('A shaders')
        self.assertTrue((self.root/'games/0000000000000100/dlc.json').exists())
        c.prepare(self.host,self.local,False,self.disks(b))
        self.assertEqual((self.root/'system/profile').read_text(),'profile-B')
        self.assertFalse((self.root/'games/cache-proof').exists());self.assertFalse((self.root/'games/0000000000000100/dlc.json').exists())
        self.assertEqual(c.read(b/'sync/settings.json')['account_path'],'profile-B')
        self.assertEqual(c.read(a/'sync/state.json'),{'proof':'profile-A'});self.assertEqual(c.read(b/'sync/state.json'),{'proof':'profile-B'})
        c.prepare(self.host,self.local,False,self.disks(a))
        self.assertEqual((self.root/'system/profile').read_text(),'profile-A');self.assertEqual((self.root/'games/cache-proof').read_text(),'A shaders')
        self.assertEqual(c.read(self.root/'Config.json')['input_config'],[{'gyro':'CemuHook'}])
    def test_game_selected_by_title_id_survives_file_rename(self):
        card,m=self.cartridge('card','a','profile-A');old=card/'roms'/m['games'][0]['rom'];old.rename(card/'roms/new-name.xci')
        m['games'][0]['rom']='new-name.xci'
        self.assertEqual(c.arguments(['--fullscreen','--game','0000000000000100'],m,card),['--fullscreen',str(card/'roms/new-name.xci')])
        with self.assertRaises(c.LibraryError):c.arguments(['--game','0000000000000200'],m,card)
    def test_game_symlink_to_other_storage_rejected(self):
        card,m=self.cartridge('card','a','profile-A');p=card/'roms'/m['games'][0]['rom'];p.unlink();other=self.base/'outside.xci';other.write_bytes(b'fixture');p.symlink_to(other)
        with self.assertRaises(c.LibraryError):c.arguments([str(p)],m,card)
        with self.assertRaises(c.LibraryError):c.arguments(['--game','0000000000000100'],m,card)
    def test_copying_only_emulation_folder_to_new_card_is_enough(self):
        old,m=self.cartridge('old','a','profile-A');folder=old/'Emulation';folder.mkdir()
        for name in ['data','roms','sync']:shutil.move(str(old/name),str(folder/name))
        m.update(data_dir='Emulation/data',rom_dir='Emulation/roms',sync_dir='Emulation/sync')
        dump(folder/'switch-library.json',m)
        (old/'.switch-library.json').unlink()
        new=self.base/'new-bigger-card';new.mkdir();shutil.copytree(folder,new/'Emulation')
        self.assertEqual(c.locate(self.host,False,self.disks(new,'unregistered-uuid'))[0],new)
    def test_dlc_nca_internal_path_not_rewritten(self):
        self.assertEqual(c.map_paths({'path':'@CARD@/roms/dlc.nsp','nca':'/content.nca'},Path('/card')),
                         {'path':'/card/roms/dlc.nsp','nca':'/content.nca'})
        with self.assertRaises(c.LibraryError):c.map_paths('@CARD@/../wrong',Path('/card'))
    def test_removing_update_from_card_clears_host_cache_selection(self):
        card,m=self.cartridge('card','a','profile-A');c.prepare(self.host,self.local,False,self.disks(card))
        self.assertTrue((self.root/'games/0000000000000100/updates.json').exists())
        m['game_metadata']={};dump(card/'.switch-library.json',m);c.prepare(self.host,self.local,False,self.disks(card))
        self.assertFalse((self.root/'games/0000000000000100/updates.json').exists())
    def test_session_lock_blocks_concurrent_library_changes(self):
        with c.session_lock(self.local):
            with self.assertRaises(c.LibraryError):
                with c.session_lock(self.local):pass
    def test_export_updates_are_portable_and_do_not_pin_card_uuid(self):
        card,m=self.cartridge('card','a','profile-A');c.prepare(self.host,self.local,False,self.disks(card))
        p=self.root/'games/0000000000000100/updates.json';dump(p,{'selected':str(self.local/'card/roms/new.nsp')})
        with patch.object(Path,'is_mount',return_value=True):c.export_metadata(card,m,self.local/'card',self.root)
        value=c.read(card/'.switch-library.json');self.assertEqual(value['game_metadata']['0000000000000100/updates.json']['selected'],'@CARD@/roms/new.nsp')
        self.assertNotIn('card_uuid',value)
    def test_frontend_settings_accept_esde_native_xml_fragment(self):
        p=self.base/'es-settings.xml';p.write_text('<?xml version="1.0"?>\n<string name="ROMDirectory" value="old"/>\n<string name="MediaDirectory" value="old"/>\n<bool name="KeepMe" value="true"/>')
        c.prepare_frontend({'frontend_settings':str(p),'frontend_media':'/local/media'},Path('/slot'),{'rom_dir':'Emulation/roms/switch'})
        self.assertIn('/slot/Emulation/roms',p.read_text());self.assertIn('name="KeepMe"',p.read_text())
    def test_frontend_settings_accept_single_xml_root(self):
        p=self.base/'es-settings.xml';p.write_text('<config><string name="ROMDirectory" value="old"/></config>')
        c.prepare_frontend({'frontend_settings':str(p),'frontend_media':'/local/media'},Path('/slot'),{'rom_dir':'Emulation/roms/switch'})
        self.assertIn('<config>',p.read_text());self.assertIn('/slot/Emulation/roms',p.read_text())
    def test_catalog_tracks_added_removed_and_renamed_games_without_host_registration(self):
        card,m=self.cartridge('card','a','profile-A')
        old=card/'roms'/m['games'][0]['rom'];old.rename(card/'roms/Renamed [0000000000000100].xci')
        (card/'roms/New [0000000000001000].nsp').write_bytes(b'fixture')
        (card/'roms/Update [0000000000001800].nsp').write_bytes(b'fixture')
        (card/'roms/Pack [0000000000001001].nsp').write_bytes(b'fixture')
        catalog=c.catalog_games(card,m)
        self.assertEqual({g['rom'] for g in catalog},{'Renamed [0000000000000100].xci','New [0000000000001000].nsp'})
        self.assertEqual({c.game_id(g) for g in catalog},{'0000000000000100','0000000000001000'})
        (card/'roms/Renamed [0000000000000100].xci').unlink()
        self.assertEqual(len(c.catalog_games(card,m)),1)

if __name__=='__main__':unittest.main()

