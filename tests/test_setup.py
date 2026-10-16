import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import card_library as card
import setup_library as setup
import steam_shortcuts as steam
import setup_wizard

PACKAGE = Path(__file__).resolve().parents[1]


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sds tests with spaces ')
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.mount = self.base / 'card'
        self.mount.mkdir()
        self.source = self.home / '.config/Ryujinx'
        self.local = self.home / '.local/share/switch-deck-sync'
        self.steam = self.home / '.local/share/Steam/userdata/123/config'
        self.source.mkdir(parents=True)
        put(self.source / 'Config.json', {'game_dirs': [], 'input_config': [{'gyro': 'host gyro'}]})
        for name in setup.SHARED:
            (self.source / name).mkdir()
        (self.source / 'bis/user/save').mkdir(parents=True)
        firmware = self.source / 'bis/system/Contents/registered'
        firmware.mkdir(parents=True)
        (firmware / 'fixture.nca').write_bytes(b'fake firmware, no proprietary data')
        (self.source / 'system/prod.keys').write_text('fixture, not keys')
        put(self.source / 'system/Profiles.json', {'profiles': [{'name': 'Fixture User'}]})
        self.roms = self.base / 'original games'
        self.roms.mkdir()
        (self.roms / 'Fixture [0000000000001000].xci').write_bytes(b'fake game')
        self.exe = self.home / 'Applications/Ryujinx'
        self.exe.parent.mkdir()
        self.exe.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\nroot=Path(sys.argv[sys.argv.index("--root-data-dir")+1])\n(root/"executed.json").write_text(json.dumps({"argv":sys.argv[1:],"profile":(root/"system/Profiles.json").read_text()}))\n')
        self.exe.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        return setup.prepare_card(self.mount, self.source, [self.roms])

    def install(self, **kwargs):
        with patch.object(Path, 'is_mount', return_value=True):
            return setup.install(PACKAGE, self.home, self.mount, {'kind': 'mmc'}, self.exe,
                                 self.source, self.steam, idle_check=lambda: None, **kwargs)

    def test_fresh_preparation_and_attach_leave_originals_untouched(self):
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        self.install(mode='prepare', rom_dirs=[self.roms])
        self.assertEqual(before, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()})
        self.assertTrue((self.roms / 'Fixture [0000000000001000].xci').exists())
        root = self.local / 'ryujinx'
        self.assertEqual(card.read(root / 'Config.json')['input_config'], [{'gyro': 'host gyro'}])
        self.assertTrue((root / 'bis').is_symlink())
        self.assertEqual((root / 'system').resolve(), self.mount / 'Emulation/storage/ryujinx/data/system')
        self.assertNotIn('card_uuid', card.read(self.mount / 'Emulation/switch-library.json'))

    def test_second_host_uses_card_profile_but_own_controller(self):
        self.prepare()
        put(self.source / 'system/Profiles.json', {'profiles': [{'name': 'Different Host User'}]})
        self.install()
        self.assertEqual(card.read(self.local / 'ryujinx/system/Profiles.json')['profiles'][0]['name'], 'Fixture User')
        self.assertEqual(card.read(self.source / 'system/Profiles.json')['profiles'][0]['name'], 'Different Host User')

    def test_repeat_install_preserves_state_saves_and_steam_ids(self):
        manifest = self.prepare()
        sync = self.mount / manifest['sync_dir']
        put(sync / 'state.json', {'baseline': 'retain'})
        put(sync / 'settings.json', {'schema': 2, 'host': '10.10.10.12', 'games': {}, 'port': 5000})
        self.install()
        shortcuts = (self.steam / 'shortcuts.vdf').read_bytes()
        self.install()
        self.assertEqual(shortcuts, (self.steam / 'shortcuts.vdf').read_bytes())
        self.assertEqual(card.read(sync / 'state.json'), {'baseline': 'retain'})
        self.assertEqual(card.read(sync / 'settings.json')['host'], '10.10.10.12')

    def test_failure_restores_existing_shortcuts_and_host_settings(self):
        self.prepare()
        original = steam.encode({'shortcuts': {'0': {'appname': 'Unrelated Steam Game', 'appid': 12, 'exe': '/game'}}})
        self.steam.mkdir(parents=True)
        (self.steam / 'shortcuts.vdf').write_bytes(original)
        real = setup.Transaction.replace

        def fail(tx, path, *args, **kwargs):
            if path.name == 'installation.json':
                raise OSError('injected full disk')
            return real(tx, path, *args, **kwargs)

        with patch.object(setup.Transaction, 'replace', fail), self.assertRaises(OSError):
            self.install()
        self.assertEqual((self.steam / 'shortcuts.vdf').read_bytes(), original)
        self.assertFalse((self.local / 'host.json').exists())
        self.assertTrue(card.marker_path(self.mount).exists())

    def test_new_card_clone_works_on_a_fresh_host(self):
        self.prepare()
        self.install()
        tools = self.base / 'bin'
        tools.mkdir()
        inventory = {'blockdevices': [{'name': 'mmcblk0', 'path': '/dev/mmcblk0', 'type': 'disk', 'tran': 'mmc',
                     'children': [{'path': '/dev/mmcblk0p1', 'type': 'part', 'fstype': 'ext4', 'uuid': 'never-registered',
                                   'mountpoints': [str(self.mount)]}]}]}
        script = tools / 'lsblk'
        script.write_text('#!/usr/bin/python3\nprint(' + repr(json.dumps(inventory)) + ')\n')
        script.chmod(0o755)
        result = subprocess.run([sys.executable, str(self.local / 'card_library.py'), 'emulator', '--fullscreen',
                                 '--game', '0000000000001000'], env=dict(os.environ, PATH=str(tools) + ':/usr/bin:/bin'),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        executed = card.read(self.local / 'ryujinx/executed.json')
        self.assertEqual(executed['argv'][0:2], ['--root-data-dir', str(self.local / 'ryujinx')])
        self.assertIn('Fixture User', executed['profile'])
        self.assertEqual(Path(executed['argv'][-1]).read_bytes(), b'fake game')

    def test_update_dlc_outside_card_are_copied_and_paths_portable(self):
        patchfile = self.base / 'DLC same name.nsp'
        patchfile.write_bytes(b'fake DLC')
        put(self.source / 'games/0000000000001000/dlc.json', [{'path': str(patchfile), 'nca': '/content.nca'}])
        value = self.prepare()['game_metadata']['0000000000001000/dlc.json'][0]
        self.assertTrue(value['path'].startswith('@CARD@/Emulation/storage/ryujinx/patchesAndDlc/'))
        self.assertEqual(value['nca'], '/content.nca')
        self.assertEqual((self.mount / value['path'][7:]).read_bytes(), patchfile.read_bytes())

    def test_preparation_retry_after_copy_failure_uses_owned_staging(self):
        original = setup.copy_verified
        count = 0

        def fail(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError('simulated interrupted copy')
            return original(*args, **kwargs)

        with patch.object(setup, 'copy_verified', fail), self.assertRaises(OSError):
            self.prepare()
        self.assertFalse(card.marker_path(self.mount).exists())
        self.prepare()
        self.assertTrue(card.marker_path(self.mount).exists())

    def test_pending_sync_blocks_install_without_runtime_changes(self):
        manifest = self.prepare()
        put(self.mount / manifest['sync_dir'] / 'pending.json', {'partial': True})
        with self.assertRaises(setup.SetupError):
            self.install()
        self.assertFalse((self.local / 'host.json').exists())

    def test_copy_will_not_replace_different_file(self):
        target = self.base / 'existing.xci'
        target.write_bytes(b'keep this')
        with self.assertRaises(setup.SetupError):
            setup.copy_verified(self.roms / 'Fixture [0000000000001000].xci', target)
        self.assertEqual(target.read_bytes(), b'keep this')

    def test_explicit_restore_keeps_card_data(self):
        self.prepare()
        result = self.install()
        setup.restore(Path(result['backup']))
        self.assertFalse((self.local / 'host.json').exists())
        self.assertTrue((self.mount / 'Emulation/storage/ryujinx/data/system/prod.keys').exists())
        # Recovery is repeatable after a second interruption.
        setup.restore(Path(result['backup']))

    def test_shortcut_writer_preserves_existing_ids_and_64bit_types(self):
        data = steam.encode({'shortcuts': {'0': {'appname': 'Game', 'exe': '/old/Ryujinx', 'appid': 42,
                             'LaunchOptions': '"Game [0000000000001000].xci"', 'some64': steam.UInt64(2**48),
                             'tags': {'0': 'mine'}}}})
        self.assertEqual(steam.encode(steam.decode(data)), data)
        changed, ids = steam.upsert(data, [{'appname': 'New Game Name', 'title_id': '0000000000001000', 'exe': '/new/Ryujinx', 'LaunchOptions': '--game 0000000000001000'}])
        value = steam.decode(changed)['shortcuts']['0']
        self.assertEqual(ids['New Game Name'], 42)
        self.assertEqual(value['tags'], {'0': 'mine'})
        self.assertEqual(value['some64'], 2**48)

    def test_stable_reader_path_survives_card_device_uuid_changes(self):
        links = self.base / 'by-path'
        links.mkdir()
        (links / 'pci-usb-reader').symlink_to('/dev/sdc')
        slot = setup.reader_slot({'path': '/dev/sdc', 'name': 'sdc', 'tran': 'usb'}, links)
        self.assertEqual(slot, {'kind': 'reader-path', 'path': str(links / 'pci-usb-reader')})

    def test_idle_guard_refuses_running_steam(self):
        proc = self.base / 'proc/123'
        proc.mkdir(parents=True)
        (proc / 'cmdline').write_bytes(b'/usr/lib/steam/steam\0')
        with self.assertRaises(setup.SetupError):
            setup.require_idle(proc.parent)

    def test_graphical_wizard_fresh_install_has_no_manual_configuration_step(self):
        self.steam.mkdir(parents=True)
        wizard = setup_wizard.Wizard(PACKAGE)
        wizard.home = self.home
        wizard.dbus = None
        dialogs = []

        def reply(*args):
            dialogs.append(args)
            if args[0] == '--radiolist':
                return '0'
            if args[0] == '--getexistingdirectory':
                return str(self.roms)
            return ''

        devices = [{'name': 'mmcblk0', 'path': '/dev/mmcblk0', 'type': 'disk', 'tran': 'mmc', 'size': '64G',
                    'children': [{'path': '/dev/mmcblk0p1', 'type': 'part', 'fstype': 'ext4', 'mountpoints': [str(self.mount)]}]}]
        with patch.object(wizard, 'dialog', side_effect=reply), patch.object(wizard, 'dependencies'), \
                patch.object(wizard, 'close_steam'), patch.object(card, 'block_devices', return_value=devices), \
                patch.object(Path, 'is_mount', return_value=True), patch.object(setup_wizard.shutil, 'which', return_value=None):
            wizard.run()
        self.assertTrue((self.local / 'host.json').exists())
        self.assertTrue((self.steam / 'shortcuts.vdf').exists())
        self.assertTrue(any(args[0] == '--yesno' for args in dialogs))
        self.assertFalse(any(args[0] == '--inputbox' for args in dialogs))

    def test_duplicate_base_games_stop_before_touching_host_runtime(self):
        self.prepare()
        (self.mount / 'Emulation/roms/switch/Duplicate [0000000000001000].xci').write_bytes(b'duplicate')
        with self.assertRaises(setup.SetupError):
            self.install()
        self.assertFalse((self.local / 'host.json').exists())

    def test_unregistered_sync_history_is_not_adopted_by_fresh_preparation(self):
        sync = self.mount / 'Emulation/tools/switch-save-sync'
        put(sync / 'state.json', {'unrelated': 'retain'})
        with self.assertRaises(setup.SetupError):
            self.prepare()
        self.assertEqual(card.read(sync / 'state.json'), {'unrelated': 'retain'})
        self.assertFalse((self.mount / 'Emulation/.switch-deck-sync-preparation.json').exists())

    def test_preparation_rejects_destination_directory_link_outside_card(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.mount / 'Emulation').symlink_to(outside)
        with self.assertRaises(card.LibraryError):
            self.prepare()
        self.assertEqual(list(outside.iterdir()), [])

    def test_preparation_resumes_when_optional_emulator_folders_were_absent(self):
        for name in ('mods', 'sdcard'):
            (self.source / name).rmdir()
        original = setup.portable_metadata
        with patch.object(setup, 'portable_metadata', side_effect=OSError('copy interrupted')), self.assertRaises(OSError):
            self.prepare()
        self.prepare()
        self.assertTrue(card.marker_path(self.mount).exists())

    def test_unrelated_same_name_shortcut_is_not_replaced(self):
        data = steam.encode({'shortcuts': {'0': {'appname': 'Game', 'exe': '/another-game', 'appid': 42}}})
        result, ids = steam.upsert(data, [{'appname': 'Game', 'title_id': '0000000000001000', 'exe': '/managed/ryujinx.sh'}])
        self.assertEqual(steam.decode(result)['shortcuts']['0']['exe'], '/another-game')
        self.assertNotEqual(ids['Game'], 42)


if __name__ == '__main__':
    unittest.main()
