import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import card_library as card
import native_card
import setup_library as setup
import setup_wizard
import steam_shortcuts as steam
import sync_launcher
import test_setup as fixtures

put = fixtures.put
PACKAGE = fixtures.PACKAGE


class ScenarioTests(unittest.TestCase):
    setUp = fixtures.SetupTests.setUp
    tearDown = fixtures.SetupTests.tearDown
    prepare = fixtures.SetupTests.prepare
    install = fixtures.SetupTests.install
    devices = fixtures.SetupTests.devices
    start_data = fixtures.SetupTests.start_data
    stop_data = fixtures.SetupTests.stop_data


class StandaloneTests(ScenarioTests):
    def install_sync(self, steam_config=True):
        return setup.install_sync_only(PACKAGE, self.home, self.source,
                                       self.steam if steam_config else None, idle_check=lambda: None)

    def test_no_card_or_emudeck_required_and_emulator_data_is_unchanged(self):
        shutil.rmtree(self.home / '.config/EmuDeck')
        shutil.rmtree(self.home / '.config/steam-rom-manager')
        (self.source / 'system/prod.keys').unlink()
        shutil.rmtree(self.source / 'bis/system/Contents')
        before = {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        with patch.object(card, 'block_devices', side_effect=AssertionError('No reader lookup')), \
                patch.object(native_card, 'systemctl', side_effect=AssertionError('No card service')):
            self.install_sync()
        self.assertEqual(before, {p.relative_to(self.source): p.read_bytes() for p in self.source.rglob('*') if p.is_file()})
        self.assertFalse((self.local / 'active').exists())
        self.assertFalse((self.local / 'host.json').exists())
        self.assertEqual(card.read(self.local / 'installation.json')['architecture'], 'sync-only')
        entries = steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts']
        self.assertEqual([s['appname'] for s in entries.values()], ['Switch Deck Sync'])

    def test_update_and_restore_keep_sync_history_and_existing_steam_games(self):
        self.steam.mkdir(parents=True)
        existing = {'appname': 'Selected Emulator', 'exe': '/my/emulator', 'appid': 44, 'tags': {'0': 'mine'}}
        (self.steam / 'shortcuts.vdf').write_bytes(steam.encode({'shortcuts': {'0': existing}}))
        first = self.install_sync()
        settings = card.read(self.local / 'data/settings.json')
        settings.update(host='10.10.10.50', games={'fixture': {'name': 'Chosen game'}})
        put(self.local / 'data/settings.json', settings)
        put(self.local / 'data/state.json', {'common-state': 'retain'})
        self.install_sync()
        self.assertEqual(card.read(self.local / 'data/settings.json'), settings)
        self.assertEqual(card.read(self.local / 'data/state.json'), {'common-state': 'retain'})
        self.assertEqual(steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts']['0'], existing)
        # Undo the update, then the original app install. User sync data remains.
        setup.restore(Path(card.read(self.local / 'installation.json')['backup']))
        setup.restore(Path(first['backup']))
        self.assertEqual(card.read(self.local / 'data/settings.json'), settings)
        self.assertEqual(card.read(self.local / 'data/state.json'), {'common-state': 'retain'})
        self.assertEqual(steam.decode((self.steam / 'shortcuts.vdf').read_bytes())['shortcuts'], {'0': existing})

    def test_without_steam_a_desktop_application_is_installed(self):
        self.install_sync(steam_config=False)
        self.assertTrue((self.home / '.local/share/applications/switch-deck-sync.desktop').is_file())
        self.assertFalse((self.steam / 'shortcuts.vdf').exists())

    def test_pending_sync_blocks_update_without_changing_runtime(self):
        self.install_sync()
        runtime = (self.local / 'sync.sh').read_bytes()
        put(self.local / 'data/pending.json', {'unfinished': True})
        with self.assertRaises(setup.SetupError):
            self.install_sync()
        self.assertEqual((self.local / 'sync.sh').read_bytes(), runtime)

    def test_failed_install_rolls_back_app_and_shortcuts_without_touching_saves(self):
        original = (self.source / 'Config.json').read_bytes()
        real = setup.Transaction.replace
        def fail(tx, path, *args, **kwargs):
            if path.name == 'installation.json':
                raise OSError('full disk')
            return real(tx, path, *args, **kwargs)
        with patch.object(setup.Transaction, 'replace', fail), self.assertRaises(OSError):
            self.install_sync()
        self.assertFalse((self.local / 'sync.sh').exists())
        self.assertFalse((self.steam / 'shortcuts.vdf').exists())
        self.assertEqual((self.source / 'Config.json').read_bytes(), original)

    def test_standalone_runtime_selects_local_data_without_a_reader(self):
        self.install_sync()
        marker = self.base / 'launched.json'
        (self.local / 'switch_save_sync.py').write_text('import os,sys,json\nfrom pathlib import Path\nPath(' + repr(str(marker)) + ').write_text(json.dumps({"data":os.environ["SDS_DATA_DIR"],"args":sys.argv[1:],"portable":os.environ.get("SDS_PORTABLE_LIBRARY")}))\n')
        with patch.object(sync_launcher.shutil, 'which', return_value=None), \
                patch.object(card, 'block_devices', side_effect=AssertionError('No card')), \
                patch.dict(os.environ, {'SDS_PORTABLE_LIBRARY': '1'}):
            result = sync_launcher.standalone(['--cli', '--check'], self.local)
        self.assertEqual(result, 0)
        self.assertEqual(card.read(marker), {'data': str(self.local / 'data'), 'args': ['--cli', '--check'], 'portable': None})

    def test_local_sync_can_be_moved_to_a_new_portable_card_without_losing_history(self):
        self.install_sync()
        settings = card.read(self.local / 'data/settings.json')
        settings['host'] = '10.0.0.50'
        put(self.local / 'data/settings.json', settings)
        put(self.local / 'data/state.json', {'baseline': 'preserved'})
        self.install(mode='prepare', rom_dirs=[self.roms])
        sync = self.mount / card.validated_manifest(self.mount)['sync_dir']
        self.assertEqual(card.read(sync / 'settings.json')['host'], '10.0.0.50')
        self.assertEqual(card.read(sync / 'state.json'), {'baseline': 'preserved'})
        self.assertEqual(card.read(self.local / 'installation.json')['architecture'], 'native-emudeck')

    def test_default_wizard_is_sync_only_and_never_asks_for_a_card(self):
        wizard = setup_wizard.Wizard(PACKAGE)
        wizard.home = self.home
        wizard.dbus = None
        dialogs = []
        def reply(*args):
            dialogs.append(args)
            return '0' if args[0] == '--radiolist' else ''
        with patch.object(wizard, 'dialog', side_effect=reply), patch.object(wizard, 'dependencies'), \
                patch.object(wizard, 'select_card', side_effect=AssertionError('No card choice')), \
                patch.object(wizard, 'steam_profile', return_value=None), \
                patch.object(native_card, 'systemctl', side_effect=AssertionError('No service')):
            wizard.run()
        self.assertEqual(card.read(self.local / 'installation.json')['architecture'], 'sync-only')
        self.assertIn('Wi-Fi', dialogs[1][1])
