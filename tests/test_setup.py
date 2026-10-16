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
import native_card
import shlex
import shutil
import legacy_migration

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
        self.manager = None
        self.emu = self.home / 'Emulation'
        self.launcher = self.emu / 'tools/launchers/ryujinx.sh'
        self.launcher.parent.mkdir(parents=True)
        (self.emu / 'roms/switch').mkdir(parents=True)
        put(self.home / '.config/steam-rom-manager/userData/userSettings.json',
            {'environmentVariables': {'romsDirectory': str(self.emu / 'roms')}})
        backend = self.home / '.config/EmuDeck/backend/functions/EmuScripts'
        backend.mkdir(parents=True)
        (backend / 'emuDeckRyujinx.sh').write_text('# fixture stock backend\n')
        self.settings = self.home / '.config/EmuDeck/settings.sh'
        self.settings.write_text('autoMapSwitch="false"\n')
        put(self.source / 'Config.json', {'game_dirs': [], 'input_config': [{'gyro': 'host gyro'}],
                                         'res_scale': 2, 'docked_mode': True, 'custom': {'proof': 'preserve'}})
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
        self.exe.write_text('#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\nroot=Path(' + repr(str(self.source)) + ')\n'
                            'config=json.loads((root/"Config.json").read_text())\n'
                            'if \'autoMapSwitch="true"\' in Path(' + repr(str(self.settings)) + ').read_text():\n'
                            ' config["input_config"]=[{"name":"mapped by stock launcher fixture"}]\n'
                            ' (root/"Config.json").write_text(json.dumps(config))\n'
                            '(root/"executed.json").write_text(json.dumps({"argv":sys.argv[1:],"profile":(root/"system/Profiles.json").read_text(),"controls":config["input_config"]}))\n')
        self.exe.chmod(0o755)
        self.launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(str(self.exe)) + ' "$@"\n')
        self.launcher.chmod(0o755)

    def tearDown(self):
        self.stop_data()
        self.temp.cleanup()

    def devices(self, mount=None):
        return [{'name': 'mmcblk0', 'path': '/dev/mmcblk0', 'type': 'disk', 'tran': 'mmc',
                 'children': [{'path': '/dev/mmcblk0p1', 'type': 'part', 'fstype': 'ext4',
                               'uuid': 'not-registered', 'mountpoints': [str(mount or self.mount)]}]}]

    def stop_data(self):
        if self.manager:
            self.manager.close()
            self.manager = None

    def start_data(self, local, library_id):
        self.manager = native_card.DataManager(card.read(local / 'host.json'), local)
        self.manager.tick(devices=self.devices(), busy=False, allow_mount=False)
        self.assertEqual(card.read(local / 'native-status.json')['state'], 'ready')

    def prepare(self):
        return setup.prepare_card(self.mount, self.source, [self.roms])

    def install(self, **kwargs):
        with patch.object(Path, 'is_mount', return_value=True):
            return setup.install(PACKAGE, self.home, self.mount, {'kind': 'mmc'}, self.exe,
                                 self.source, self.steam, idle_check=lambda: None,
                                 service_start=self.start_data, service_stop=self.stop_data, **kwargs)

    def test_fresh_preparation_and_attach_leave_originals_untouched(self):
        before = card.read(self.source / 'Config.json')['input_config']
        self.install(mode='prepare', rom_dirs=[self.roms])
        self.assertEqual(before, card.read(self.source / 'Config.json')['input_config'])
        self.assertTrue((self.roms / 'Fixture [0000000000001000].xci').exists())
        root = self.source
        self.assertEqual(card.read(root / 'Config.json')['input_config'], [{'gyro': 'host gyro'}])
        self.assertTrue((root / 'bis').is_symlink())
        self.assertEqual((root / 'system').resolve(), self.mount / 'Emulation/storage/ryujinx/data/system')
        self.assertNotIn('card_uuid', card.read(self.mount / 'Emulation/switch-library.json'))

    def legacy_fixture(self):
        manifest = self.prepare()
        self.old = self.home / '.local/share/switch-library'
        self.old.mkdir(parents=True)
        (self.old / 'card').symlink_to(self.mount)
        self.cache = self.old / 'libraries' / manifest['library_id'] / 'games'
        self.cache.mkdir(parents=True)
        (self.cache / 'warm-cache.bin').write_bytes(b'compiled shader cache')
        for name in setup.SHARED:
            shutil.rmtree(self.source / name)
            (self.source / name).symlink_to(self.old / 'card' / manifest['data_dir'] / name)
        (self.source / 'games').symlink_to(self.cache)
        publish = self.home / 'Applications/publish'
        publish.mkdir()
        self.exe.rename(publish / 'Ryujinx')
        self.exe = publish / 'Ryujinx'
        self.wrapper = publish / 'Ryujinx.sh'
        self.wrapper.write_text('#!/bin/sh\nexec "' + str(self.old / 'ryujinx.sh') + '" "$@"\n')
        self.wrapper.chmod(0o755)
        self.original_wrapper = b'#!/bin/sh\nSCRIPT_DIR=$(dirname "$(realpath "$0")")\nexec "$SCRIPT_DIR/Ryujinx" "$@"\n'
        before = self.home / 'Emulation/backups/earlier/Ryujinx.before-switch-library.sh'
        before.parent.mkdir(parents=True)
        before.write_bytes(self.original_wrapper)
        # This fixture has the stock toolsPath nested one level deeper, like
        # existing EmuDeck hosts. It must not be guessed from romsDirectory.
        new_launcher = self.emu / 'tools/emudeck/launchers/ryujinx.sh'
        new_launcher.parent.mkdir(parents=True)
        self.launcher.rename(new_launcher)
        self.launcher = new_launcher
        self.launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(str(self.wrapper)) + ' "$@"\n')
        self.launcher.chmod(0o755)
        frontend = self.launcher.parent / 'es-de/es-de.sh'
        frontend.parent.mkdir()
        frontend.write_text('#!/bin/sh\nexit 0\n')
        frontend.chmod(0o755)
        paths = {'emulationPath': str(self.old / 'card/Emulation'),
                 'romsPath': str(self.old / 'card/Emulation/roms'),
                 'toolsPath': str(self.launcher.parent.parent),
                 'biosPath': str(self.old / 'card/Emulation/bios'),
                 'savesPath': str(self.old / 'card/Emulation/saves'),
                 'storagePath': str(self.old / 'card/Emulation/storage')}
        self.settings.write_text('autoMapSwitch="false"\ncontrollerLayout="baxy"\n' +
                                 ''.join(k + '=' + shlex.quote(v) + '\n' for k, v in paths.items()))
        put(self.settings.with_suffix('.json'), {'storagePath': str(self.old / 'card'), 'custom': 'preserve'})
        stale = self.base / 'old-card-512/Emulation'
        put(self.home / '.config/steam-rom-manager/userData/userSettings.json',
            {'environmentVariables': {'romsDirectory': str(stale / 'roms'), 'steamDirectory': '/preserve'}})
        put(self.home / '.config/steam-rom-manager/userData/userConfigurations.json',
            [{'executable': str(stale / 'tools/launchers/ryujinx.sh'), 'romDirectory': str(stale / 'roms/switch')}])
        xml = self.home / 'ES-DE/settings/es_settings.xml'
        xml.parent.mkdir(parents=True)
        xml.write_text('<?xml version="1.0"?>\n<string name="ROMDirectory" value="' + str(self.old / 'card/Emulation/roms') +
                       '" />\n<string name="MediaDirectory" value="keep" />')
        xml = self.home / 'ES-DE/custom_systems/es_find_rules.xml'
        xml.parent.mkdir(parents=True)
        xml.write_text('<rules><entry>' + str(self.old / 'ryujinx.sh') + '</entry></rules>')
        desktop = self.home / '.local/share/applications/Ryujinx.desktop'
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text('[Desktop Entry]\nExec="' + str(self.old / 'ryujinx.sh') + '"\nPath=' + str(self.old) + '\n')
        (self.emu / 'tools/switch-save-sync').symlink_to(self.old / 'card' / manifest['sync_dir'])
        put(self.old / 'host.json', {'schema': 2, 'ryujinx_dir': str(self.source), 'emulator_executable': str(self.exe)})
        manifest['games'][0]['name'] = 'Fixture (Ryujinx)'
        card.write_changed(card.marker_path(self.mount), manifest)
        self.steam.mkdir(parents=True)
        shortcuts = {'0': {'appid': 42, 'appname': 'Fixture (Ryujinx)', 'exe': str(self.old / 'ryujinx.sh'),
                           'LaunchOptions': '--game 0000000000001000', 'tags': {'0': 'preserved'}},
                     '1': {'appid': 43, 'appname': 'Ryujinx (Emulator)', 'exe': str(self.old / 'ryujinx.sh')},
                     '2': {'appid': 44, 'appname': 'EmulationStationDE', 'exe': str(self.old / 'frontend.sh')}}
        (self.steam / 'shortcuts.vdf').write_bytes(steam.encode({'shortcuts': shortcuts}))
        return manifest

    def test_legacy_migration_retires_wrapper_preserves_cache_controls_and_shortcut_ids(self):
        manifest = self.legacy_fixture()
        before = card.read(self.source / 'Config.json')
        native_launcher = self.launcher.read_bytes()
        self.install()
        self.assertFalse(self.old.exists())
        self.assertEqual(self.wrapper.read_bytes(), self.original_wrapper)
        self.assertEqual(self.launcher.read_bytes(), native_launcher)
        after = card.read(self.source / 'Config.json')
        before['game_dirs'] = [str(self.emu / 'roms/switch')]
        self.assertEqual(before, after)
        self.assertEqual((self.source / 'games/warm-cache.bin').read_bytes(), b'compiled shader cache')
        self.assertEqual(legacy_migration.shell_paths(self.home)['toolsPath'], str(self.launcher.parent.parent))
        self.assertEqual(legacy_migration.shell_paths(self.home)['romsPath'], str(self.emu / 'roms'))
        self.assertIn('autoMapSwitch="false"', self.settings.read_text())
        shortcuts = steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts']
        self.assertEqual(len(shortcuts), 4)
        self.assertEqual(shortcuts['0']['appid'], 42)
        self.assertEqual(shortcuts['0']['tags'], {'0': 'preserved'})
        self.assertEqual(shortcuts['1']['appid'], 43)
        self.assertEqual(shortcuts['2']['appid'], 44)
        for shortcut in shortcuts.values():
            self.assertNotIn(str(self.old), shortcut['exe'])
            self.assertNotIn('(Ryujinx) (Ryujinx)', shortcut['appname'])
        result = subprocess.run([str(self.launcher), '--fullscreen', str(self.emu / 'roms/switch' / manifest['games'][0]['rom'])],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Fixture User', card.read(self.source / 'executed.json')['profile'])
        self.install()  # Native reinstallation works after the legacy runtime is retired.
        self.assertEqual(len(steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts']), 4)

    def test_legacy_service_failure_restores_all_entry_points_and_links(self):
        self.legacy_fixture()
        paths = [self.wrapper, self.settings, self.settings.with_suffix('.json'), self.steam / 'shortcuts.vdf',
                 self.home / 'ES-DE/settings/es_settings.xml', self.home / 'ES-DE/custom_systems/es_find_rules.xml',
                 self.home / '.local/share/applications/Ryujinx.desktop']
        before = {p: p.read_bytes() for p in paths}
        with patch.object(self, 'start_data', side_effect=OSError('service failed')), self.assertRaises(OSError):
            self.install()
        self.assertTrue(self.old.is_dir())
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertEqual((self.source / 'games').resolve(), self.cache)
        self.assertTrue((self.source / 'system/prod.keys').is_file())

    def test_legacy_missing_original_wrapper_stops_before_functional_changes(self):
        self.legacy_fixture()
        (self.home / 'Emulation/backups/earlier/Ryujinx.before-switch-library.sh').unlink()
        before = self.wrapper.read_bytes()
        with self.assertRaisesRegex(ValueError, 'original Ryujinx'):
            self.install()
        self.assertEqual(self.wrapper.read_bytes(), before)
        self.assertTrue(self.old.is_dir())
        self.assertFalse((self.local / 'installation.json').exists())

    def test_legacy_retry_after_service_materialised_portable_metadata(self):
        manifest = self.legacy_fixture()
        relative = '0000000000001000/updates.json'
        put(self.cache / relative, {'selected': str(self.old / 'card/old-update.nsp')})
        manifest['game_metadata'] = {relative: {'selected': '@CARD@/Emulation/storage/ryujinx/patchesAndDlc/update.nsp'}}
        card.write_changed(card.marker_path(self.mount), manifest)
        real_start = self.start_data
        def start_then_fail(local, identity):
            real_start(local, identity)
            raise OSError('ready handshake failed after attachment')
        with patch.object(self, 'start_data', side_effect=start_then_fail), self.assertRaises(OSError):
            self.install()
        self.assertTrue(self.old.is_dir())
        self.install()
        self.assertFalse(self.old.exists())
        self.assertIn(str(self.local / 'active/card'), card.read(self.source / 'games' / relative)['selected'])

    def test_second_host_uses_card_profile_but_own_controller(self):
        self.prepare()
        put(self.source / 'system/Profiles.json', {'profiles': [{'name': 'Different Host User'}]})
        self.install()
        self.assertEqual(card.read(self.source / 'system/Profiles.json')['profiles'][0]['name'], 'Fixture User')
        backup = Path(card.read(self.local / 'installation.json')['backup'])
        journal = card.read(backup / 'transaction.json')
        entry = next(i for i in journal['items'] if i['path'] == str(self.source / 'system'))
        self.assertEqual(card.read(backup / entry['backup'] / 'Profiles.json')['profiles'][0]['name'], 'Different Host User')

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
        result = subprocess.run([str(self.launcher), '--fullscreen', str(self.emu / 'roms/switch/Fixture [0000000000001000].xci')],
                                env=dict(os.environ, PATH=str(tools) + ':/usr/bin:/bin'),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        executed = card.read(self.source / 'executed.json')
        self.assertNotIn('--root-data-dir', executed['argv'])
        self.assertIn('Fixture User', executed['profile'])
        self.assertEqual(Path(executed['argv'][-1]).read_bytes(), b'fake game')

    def test_card_install_adds_only_sync_and_preserves_stock_setup(self):
        original = self.launcher.read_bytes()
        self.prepare()
        self.install()
        shortcuts = steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts']
        self.assertEqual([value['appname'] for value in shortcuts.values()], ['Switch Deck Sync'])
        self.assertEqual(self.launcher.read_bytes(), original)
        self.assertFalse((self.local / 'ryujinx.sh').exists())
        self.assertFalse((self.local / 'ryujinx').exists())
        self.assertNotIn('emulator_executable', card.read(self.local / 'host.json'))
        config = card.read(self.source / 'Config.json')
        self.assertEqual(config['res_scale'], 2)
        self.assertTrue(config['docked_mode'])
        self.assertEqual(config['custom'], {'proof': 'preserve'})
        self.assertEqual(self.settings.read_text(), 'autoMapSwitch="false"\n')

    def test_card_update_preserves_srm_and_existing_game_entries_exactly(self):
        self.prepare()
        existing = {'appname': 'My SRM Game', 'exe': '"' + str(self.launcher) + '"',
                    'appid': 42, 'LaunchOptions': 'custom args', 'StartDir': '/custom',
                    'tags': {'0': 'Selected games'}, 'icon': '/my/art.ico'}
        self.steam.mkdir(parents=True)
        (self.steam / 'shortcuts.vdf').write_bytes(steam.encode({'shortcuts': {'0': existing}}))
        self.install()
        self.install()
        shortcuts = steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts']
        self.assertEqual(shortcuts['0'], existing)
        self.assertEqual(len(shortcuts), 2)

    def test_game_can_launch_with_our_python_runtime_files_unavailable(self):
        self.prepare()
        self.install()
        # Mapping is already present. A game must not import/execute our runtime.
        for path in self.local.glob('*.py'):
            path.write_text('raise RuntimeError("custom runtime must not be used to launch games")\n')
        result = subprocess.run([str(self.launcher), '--fullscreen',
                                 str(self.emu / 'roms/switch/Fixture [0000000000001000].xci')],
                                capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=''))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Fixture User', card.read(self.source / 'executed.json')['profile'])

    def test_stock_automap_disabled_and_enabled_are_both_owned_by_native_launcher(self):
        self.prepare()
        self.install()
        for enabled in (False, True):
            settings = 'autoMapSwitch="' + str(enabled).lower() + '"\n'
            self.settings.write_text(settings)
            result = subprocess.run([str(self.launcher)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            controls = card.read(self.source / 'executed.json')['controls']
            self.assertEqual(controls, [{'name': 'mapped by stock launcher fixture'}] if enabled else [{'gyro': 'host gyro'}])
            self.assertEqual(self.settings.read_text(), settings)

    def test_service_start_failure_rolls_back_real_directories_and_config(self):
        self.prepare()
        original = (self.source / 'Config.json').read_bytes()
        with patch.object(self, 'start_data', side_effect=OSError('service start failed')), self.assertRaises(OSError):
            self.install()
        self.assertEqual((self.source / 'Config.json').read_bytes(), original)
        self.assertFalse((self.source / 'bis').is_symlink())
        self.assertFalse((self.emu / 'roms/switch').is_symlink())
        self.assertFalse((self.home / '.config/systemd/user' / native_card.UNIT).exists())

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
        self.stop_data()
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
                return '1' if args[1] == 'What would you like to set up?' else '0'
            if args[0] == '--getexistingdirectory':
                return str(self.roms)
            return ''

        devices = [{'name': 'mmcblk0', 'path': '/dev/mmcblk0', 'type': 'disk', 'tran': 'mmc', 'size': '64G',
                    'children': [{'path': '/dev/mmcblk0p1', 'type': 'part', 'fstype': 'ext4', 'mountpoints': [str(self.mount)]}]}]
        original_install = setup.install
        def install_ui(*args, **kwargs):
            return original_install(*args, **kwargs, idle_check=lambda: None,
                                    service_start=self.start_data, service_stop=self.stop_data)
        with patch.object(wizard, 'dialog', side_effect=reply), patch.object(wizard, 'dependencies'), \
                patch.object(wizard, 'close_steam'), patch.object(card, 'block_devices', return_value=devices), \
                patch.object(Path, 'is_mount', return_value=True), patch.object(setup_wizard.shutil, 'which', return_value=None), \
                patch.object(setup, 'install', side_effect=install_ui), \
                patch.object(setup_wizard.subprocess, 'Popen') as spawn:
            wizard.run()
        spawn.assert_not_called()
        self.assertTrue((self.local / 'host.json').exists())
        self.assertTrue((self.steam / 'shortcuts.vdf').exists())
        self.assertTrue(any(args[0] == '--yesno' for args in dialogs))
        self.assertFalse(any(args[0] == '--inputbox' for args in dialogs))
        self.assertIn('Open Steam from the application menu', dialogs[-1][1])

    def test_prepared_card_wizard_russian_finishes_without_starting_steam(self):
        self.prepare()
        self.steam.mkdir(parents=True)
        wizard = setup_wizard.Wizard(PACKAGE)
        wizard.home = self.home
        wizard.dbus = None
        dialogs = []
        def reply(*args):
            dialogs.append(args)
            return '1' if args[0] == '--radiolist' else ''
        original_install = setup.install
        def install_ui(*args, **kwargs):
            return original_install(*args, **kwargs, idle_check=lambda: None,
                                    service_start=self.start_data, service_stop=self.stop_data)
        with patch.object(wizard, 'dialog', side_effect=reply), patch.object(wizard, 'dependencies'), \
                patch.object(wizard, 'close_steam'), patch.object(card, 'block_devices', side_effect=self.devices), \
                patch.object(Path, 'is_mount', return_value=True), \
                patch.object(setup, 'install', side_effect=install_ui), \
                patch.object(setup_wizard.subprocess, 'Popen') as spawn:
            wizard.run()
        spawn.assert_not_called()
        self.assertIn('Открой Steam через меню приложений', dialogs[-1][1])
        self.assertIn('Настройки синхронизации с карты уже готовы', dialogs[-1][1])

    def test_restore_success_and_failure_do_not_start_steam_as_installer_child(self):
        self.prepare()
        self.install()
        wizard = setup_wizard.Wizard(PACKAGE)
        wizard.home = self.home
        wizard.ru = False
        with patch.object(wizard, 'dialog'), patch.object(wizard, 'close_steam'), \
                patch.object(native_card, 'stop_service', side_effect=self.stop_data), \
                patch.object(native_card, 'systemctl'), \
                patch.object(setup_wizard.subprocess, 'Popen') as spawn:
            with patch.object(setup, 'restore', side_effect=OSError('restore failed')), self.assertRaises(OSError):
                wizard.restore_previous()
            wizard.restore_previous()
        spawn.assert_not_called()

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
