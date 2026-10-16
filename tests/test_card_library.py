import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import card_library as card
import native_card
import test_setup as fixtures


class NativeCardTests(unittest.TestCase):
    setUp = fixtures.SetupTests.setUp
    tearDown = fixtures.SetupTests.tearDown
    prepare = fixtures.SetupTests.prepare
    install = fixtures.SetupTests.install
    devices = fixtures.SetupTests.devices
    start_data = fixtures.SetupTests.start_data
    stop_data = fixtures.SetupTests.stop_data

    def other_card(self):
        second = self.base / 'second card'
        shutil.copytree(self.mount, second)
        value = card.read(card.marker_path(second))
        value['library_id'] = 'b' * 32
        card.write_changed(card.marker_path(second), value)
        card.write_changed(second / value['data_dir'] / 'system/Profiles.json',
                           {'profiles': [{'name': 'Other card profile'}]})
        return second

    def test_new_uuid_and_different_library_are_accepted_in_the_same_reader(self):
        self.prepare()
        second = self.other_card()
        self.install()
        old_controls = card.read(self.source / 'Config.json')['input_config']
        self.manager.tick(self.devices(second), busy=False, allow_mount=False)
        self.assertEqual(card.read(self.source / 'system/Profiles.json')['profiles'][0]['name'], 'Other card profile')
        self.assertEqual(card.read(self.source / 'Config.json')['input_config'], old_controls)
        self.manager.tick(self.devices(), busy=False, allow_mount=False)
        self.assertEqual(card.read(self.source / 'system/Profiles.json')['profiles'][0]['name'], 'Fixture User')

    def test_usb_library_is_not_used_when_selected_slot_contains_ordinary_steam_card(self):
        self.prepare()
        self.install()
        steam = self.base / 'steam card'
        steam.mkdir()
        devices = self.devices(steam)
        usb = copy.deepcopy(self.devices()[0])
        usb.update(name='sda', path='/dev/sda', tran='usb')
        usb['children'][0]['path'] = '/dev/sda1'
        devices.append(usb)
        self.manager.tick(devices, busy=False, allow_mount=False)
        self.assertEqual(os.readlink(self.local / 'active'), '/dev/null')
        self.assertEqual(card.read(self.local / 'native-status.json')['state'], 'absent')

    def test_no_card_prevents_fallback_local_saves(self):
        self.prepare()
        self.install()
        self.manager.tick([], busy=False, allow_mount=False)
        with self.assertRaises(OSError):
            (self.source / 'bis/user/save/accidental-local-save').mkdir(parents=True)
        self.assertFalse((self.local / 'active').is_dir())
        self.assertEqual((self.mount / 'Emulation/storage/ryujinx/data/system/prod.keys').read_text(), 'fixture, not keys')

    def test_service_descriptor_does_not_pin_card_and_crash_does_not_create_local_saves(self):
        self.prepare()
        self.install()
        target = os.readlink(self.local / 'active')
        self.assertTrue(target.startswith('/proc/'))
        fd_path = Path('/proc/self/fd') / str(self.manager.directory_fd)
        self.assertTrue(str(fd_path.resolve()).startswith(str(self.local / 'targets')))
        os.close(self.manager.directory_fd)
        self.manager.directory_fd = None
        with self.assertRaises(OSError):
            (self.source / 'bis/user/save/unwanted').mkdir(parents=True)

    def test_busy_emulator_never_switches_to_another_profile(self):
        self.prepare()
        second = self.other_card()
        self.install()
        self.manager.tick(self.devices(second), busy=True, allow_mount=False)
        self.assertEqual(card.read(self.local / 'native-status.json')['state'], 'busy')
        self.assertFalse((self.source / 'system/Profiles.json').exists())
        self.manager.tick(self.devices(second), busy=False, allow_mount=False)
        self.assertEqual(card.read(self.source / 'system/Profiles.json')['profiles'][0]['name'], 'Other card profile')

    def test_partial_metadata_write_does_not_disconnect_active_game(self):
        self.prepare()
        self.install()
        p = self.source / 'games/0000000000001000/updates.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{')
        active = os.readlink(self.local / 'active')
        self.manager.tick(self.devices(), busy=True, allow_mount=False)
        self.assertEqual(os.readlink(self.local / 'active'), active)
        self.assertTrue((self.source / 'system/Profiles.json').is_file())
        p.write_text(json.dumps({'selected': str(self.local / 'active/card/Emulation/storage/ryujinx/patchesAndDlc/new.nsp')}))
        with patch.object(Path, 'is_mount', return_value=True):
            self.manager.tick(self.devices(), busy=False, allow_mount=False)
        manifest = card.read(card.marker_path(self.mount))
        self.assertEqual(manifest['game_metadata']['0000000000001000/updates.json']['selected'],
                         '@CARD@/Emulation/storage/ryujinx/patchesAndDlc/new.nsp')

    def test_cache_namespaces_and_update_paths_do_not_leak_between_cards(self):
        value = self.prepare()
        value['game_metadata'] = {'0000000000001000/updates.json': {'selected': '@CARD@/Emulation/roms/switch/update.nsp'}}
        card.write_changed(card.marker_path(self.mount), value)
        second = self.other_card()
        other = card.read(card.marker_path(second))
        other['game_metadata'] = {}
        card.write_changed(card.marker_path(second), other)
        self.install()
        (self.source / 'games/cache-proof').write_text('first card shaders')
        self.manager.tick(self.devices(second), busy=False, allow_mount=False)
        self.assertFalse((self.source / 'games/cache-proof').exists())
        self.assertFalse((self.source / 'games/0000000000001000/updates.json').exists())
        self.manager.tick(self.devices(), busy=False, allow_mount=False)
        self.assertEqual((self.source / 'games/cache-proof').read_text(), 'first card shaders')
        self.assertIn(str(self.local / 'active/card'), (self.source / 'games/0000000000001000/updates.json').read_text())

    def test_standard_emudeck_dlc_folder_is_card_owned_and_metadata_is_portable(self):
        self.prepare()
        self.install()
        patches = self.emu / 'storage/ryujinx/patchesAndDlc'
        (patches / 'new pack.nsp').write_bytes(b'fixture DLC')
        self.assertEqual((self.mount / 'Emulation/storage/ryujinx/patchesAndDlc/new pack.nsp').read_bytes(), b'fixture DLC')
        p = self.source / 'games/0000000000001000/dlc.json'
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps([{'path': str(patches / 'new pack.nsp'), 'nca': '/content.nca'}]))
        with patch.object(Path, 'is_mount', return_value=True):
            self.manager.tick(self.devices(), busy=False, allow_mount=False)
        manifest = card.read(card.marker_path(self.mount))
        selected = manifest['game_metadata']['0000000000001000/dlc.json'][0]
        self.assertEqual(selected, {'path': '@CARD@/Emulation/storage/ryujinx/patchesAndDlc/new pack.nsp', 'nca': '/content.nca'})

    def test_emudeck_reset_is_detected_without_replacing_native_settings(self):
        self.prepare()
        self.install()
        (self.source / 'bis').unlink()
        (self.source / 'bis/user/save').mkdir(parents=True)
        (self.source / 'bis/user/save/proof').write_text('new native data')
        config = (self.source / 'Config.json').read_bytes()
        self.manager.tick(self.devices(), busy=False, allow_mount=False)
        self.assertFalse((self.local / 'active').is_dir())
        self.assertEqual((self.source / 'bis/user/save/proof').read_text(), 'new native data')
        self.assertEqual((self.source / 'Config.json').read_bytes(), config)

    def test_external_symlinks_in_card_data_are_rejected(self):
        value = self.prepare()
        outside = self.base / 'outside'
        outside.mkdir()
        system = self.mount / value['data_dir'] / 'system'
        shutil.rmtree(system)
        system.symlink_to(outside)
        with self.assertRaises(card.LibraryError):
            card.validated_manifest(self.mount)

    def test_card_clone_needs_only_the_emulation_folder(self):
        self.prepare()
        second = self.base / 'larger card'
        second.mkdir()
        shutil.copytree(self.mount / 'Emulation', second / 'Emulation')
        found, _, _ = card.locate({'slot': {'kind': 'mmc'}}, False, self.devices(second))
        self.assertEqual(found, second)

    def test_dlc_internal_nca_paths_are_not_rewritten(self):
        self.assertEqual(card.map_paths({'path': '@CARD@/roms/dlc.nsp', 'nca': '/content.nca'}, Path('/card')),
                         {'path': '/card/roms/dlc.nsp', 'nca': '/content.nca'})
        with self.assertRaises(card.LibraryError):
            card.map_paths('@CARD@/../wrong', Path('/card'))

    def test_catalog_detects_new_base_games_and_excludes_updates(self):
        value = self.prepare()
        roms = self.mount / value['rom_dir']
        (roms / 'New [0000000000002000].nsp').write_bytes(b'fixture')
        (roms / 'Update [0000000000002800].nsp').write_bytes(b'fixture')
        catalog = card.catalog_games(self.mount, value)
        self.assertEqual({card.game_id(g) for g in catalog}, {'0000000000001000', '0000000000002000'})

    def test_service_restart_attaches_the_card_without_an_emulator_launch(self):
        self.prepare()
        self.install()
        self.stop_data()
        self.assertEqual(os.readlink(self.local / 'active'), '/dev/null')
        self.start_data(self.local, '')
        self.assertTrue((self.source / 'system/Profiles.json').is_file())
        self.assertFalse((self.source / 'executed.json').exists())

    def test_installed_background_service_attaches_and_stops_without_starting_emulator(self):
        self.prepare()
        self.install()
        self.stop_data()
        tools = self.base / 'fake tools'
        tools.mkdir()
        listing = tools / 'lsblk'
        listing.write_text('#!/usr/bin/python3\nprint(' + repr(json.dumps({'blockdevices': self.devices()})) + ')\n')
        listing.chmod(0o755)
        child = subprocess.Popen([sys.executable, str(self.local / 'native_card.py'), 'watch'],
                                 env=dict(os.environ, PATH=str(tools) + ':/usr/bin:/bin'),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(80):
                if card.read(self.local / 'native-status.json').get('state') == 'ready':
                    break
                if child.poll() is not None:
                    self.fail(child.communicate()[1])
                time.sleep(0.05)
            self.assertEqual(card.read(self.local / 'native-status.json')['state'], 'ready')
            self.assertTrue((self.source / 'system/prod.keys').is_file())
            self.assertFalse((self.source / 'executed.json').exists())
        finally:
            child.terminate()
            child.communicate(timeout=8)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(os.readlink(self.local / 'active'), '/dev/null')


if __name__ == '__main__':
    unittest.main()
