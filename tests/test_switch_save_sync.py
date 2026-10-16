import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import switch_save_sync as s
import i18n

class DiskStore:
    def __init__(self, root):
        self.root = root
        self.fail_write = False
        self.fail_connect = False
        self.writes = 0
        self.connections = 0

    def connect(self):
        self.connections += 1
        if self.fail_connect and self.connections > 1:
            raise OSError('offline')

    def snapshot(self, remote, dest):
        shutil.copytree(self.root, dest)
        return s.digest_tree(dest)

    def replace(self, remote, source):
        self.writes += 1
        shutil.rmtree(self.root)
        shutil.copytree(source, self.root)
        if self.fail_write and self.writes == 1:
            (self.root / 'progress').write_text('partial transfer')
            raise OSError('simulated broken connection')

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.old_language = i18n.language()
        i18n.set_language('en')
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / 'sync'
        self.home.mkdir()
        self.save = self.root / 'saves/0000000000000001'
        for n in ['0', '1']:
            (self.save / n).mkdir(parents=True)
            (self.save / n / 'progress').write_text('baseline')
        title = 0x01007EF00011E000
        for n in ['ExtraData0', 'ExtraData1']:
            (self.save / n).write_bytes(title.to_bytes(8, 'little') + b'profile metadata' + bytes(488))
        (self.save / '.lock').touch()
        self.remote = self.root / 'remote'
        shutil.copytree(self.save / '0', self.remote)
        self.baseline = s.digest_tree(self.remote)
        self.settings = {'save_root': str(self.save.parent), 'account_path': '/save:/profile/files',
            'games': {'zelda': {'title_id': '01007EF00011E000', 'save_id': self.save.name, 'name': 'Zelda'}}}
        self.old_home = s.HOME
        s.HOME = self.home
        s.atomic_json(self.home / 'state.json', {'zelda': self.baseline})
        self.idle = patch.object(s, 'ensure_idle')
        self.idle.start()
        self.store = DiskStore(self.remote)

    def tearDown(self):
        i18n.set_language(self.old_language)
        self.idle.stop()
        s.HOME = self.old_home
        self.tmp.cleanup()

    def engine(self, choice='skip'):
        return s.Sync(self.settings, self.store, lambda name: choice, lambda text: None)

    def deck_change(self, data='new Deck progress'):
        (self.save / '0/progress').write_text(data)
        (self.save / '1/progress').write_text(data)

    def test_unchanged_no_remote_write(self):
        result = self.engine().run()
        self.assertIn('identical', result[0])
        self.assertEqual(self.store.writes, 0)

    def test_deck_to_switch_and_common_baseline(self):
        self.deck_change()
        self.engine().run()
        expected = s.digest_tree(self.save / '0')
        self.assertEqual(s.digest_tree(self.remote), expected)
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], expected)
        self.assertFalse((self.home / 'pending.json').exists())
        backups = list((self.home / 'backups').glob('*/zelda/switch/progress'))
        self.assertEqual(backups[0].read_text(), 'baseline')

    def test_switch_to_deck_preserves_metadata_both_generations(self):
        metadata = (self.save / 'ExtraData0').read_bytes()
        (self.remote / 'progress').write_text('new Switch progress')
        (self.remote / 'new-directory').mkdir()
        (self.remote / 'new-directory/new-slot').write_text('slot data')
        self.engine().run()
        self.assertEqual(s.digest_tree(self.save / '0'), s.digest_tree(self.remote))
        self.assertEqual(s.digest_tree(self.save / '1'), s.digest_tree(self.remote))
        self.assertEqual((self.save / 'ExtraData0').read_bytes(), metadata)
        self.assertEqual(self.store.writes, 0)

    def test_conflict_skips_without_merging(self):
        self.deck_change()
        (self.remote / 'progress').write_text('different Switch progress')
        self.engine().run()
        self.assertEqual((self.save / '0/progress').read_text(), 'new Deck progress')
        self.assertEqual((self.remote / 'progress').read_text(), 'different Switch progress')
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], self.baseline)
        self.assertEqual(self.store.writes, 0)

    def test_conflict_explicit_switch_choice(self):
        self.deck_change()
        (self.remote / 'progress').write_text('chosen Switch progress')
        self.engine('switch').run()
        self.assertEqual((self.save / '0/progress').read_text(), 'chosen Switch progress')

    def test_same_changes_both_sides_are_already_synced(self):
        self.deck_change('same new progress')
        (self.remote / 'progress').write_text('same new progress')
        self.engine().run()
        self.assertEqual(self.store.writes, 0)
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], s.digest_tree(self.remote))

    def test_dry_run_never_updates_data_or_baseline(self):
        self.deck_change()
        self.engine().run(dry_run=True)
        self.assertEqual((self.remote / 'progress').read_text(), 'baseline')
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], self.baseline)

    def test_failed_remote_write_restores_backup(self):
        self.deck_change()
        self.store.fail_write = True
        with self.assertRaisesRegex(s.SyncError, 'restored'):
            self.engine().run()
        self.assertEqual(s.digest_tree(self.remote), self.baseline)
        self.assertEqual((self.save / '0/progress').read_text(), 'new Deck progress')
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], self.baseline)
        self.assertFalse((self.home / 'pending.json').exists())

    def test_unrecoverable_connection_preserves_pending_then_recovers(self):
        self.deck_change()
        self.store.fail_write = self.store.fail_connect = True
        with self.assertRaisesRegex(s.SyncError, 'Do not start'):
            self.engine().run()
        self.assertTrue((self.home / 'pending.json').exists())
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], self.baseline)
        self.store.fail_connect = False
        self.engine().recover()
        self.assertEqual(s.digest_tree(self.remote), self.baseline)
        self.assertFalse((self.home / 'pending.json').exists())

    def test_power_loss_between_verified_transfer_and_baseline(self):
        self.deck_change()
        shutil.rmtree(self.remote)
        shutil.copytree(self.save / '0', self.remote)
        expected = s.digest_tree(self.remote)
        s.atomic_json(self.home / 'pending.json', {'kind': 'agreed', 'key': 'zelda', 'manifest': expected})
        self.engine().recover()
        self.assertEqual(s.read_json(self.home / 'state.json')['zelda'], expected)
        self.assertEqual(s.digest_tree(self.remote), expected)

    def test_failed_local_swap_restores_original_folder(self):
        (self.remote / 'progress').write_text('Switch change')
        rename = Path.rename
        def failing_rename(path, target):
            if '-sync-' in path.name:
                raise OSError('simulated disk failure')
            return rename(path, target)
        with patch.object(Path, 'rename', failing_rename):
            with self.assertRaises(OSError):
                self.engine().run()
        self.assertEqual(s.digest_tree(self.save / '0'), self.baseline)
        self.assertFalse((self.home / 'pending.json').exists())

    def test_rejects_empty_and_symlinked_save(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaises(s.SyncError):
            s.digest_tree(empty)
        (empty / 'link').symlink_to(self.save / '0/progress')
        with self.assertRaises(s.SyncError):
            s.digest_tree(empty)

    def test_unknown_baseline_requires_choice(self):
        self.assertEqual(s.decide(None, {'a': 1}, {'a': 2}), 'conflict')

if __name__ == '__main__':
    unittest.main(verbosity=2)
