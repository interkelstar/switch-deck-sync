import ast
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import i18n
import sync_config
import switch_save_sync


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.previous = i18n.language()
        i18n.set_language('en')

    def tearDown(self):
        i18n.set_language(self.previous)

    def test_all_runtime_russian_text_has_an_english_translation_and_is_wrapped(self):
        root = Path(__file__).resolve().parents[1] / 'app'
        for name in ('sync_ui.py', 'sync_config.py', 'switch_save_sync.py',
                     'sync_launcher.py', 'card_library.py', 'native_card.py', 'setup_library.py'):
            tree = ast.parse((root / name).read_text(encoding='utf-8'))
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search('[А-Яа-яЁё]', node.value):
                    with self.subTest(file=name, message=node.value):
                        self.assertIn(node.value, i18n.EN)
                        self.assertFalse(re.search('[А-Яа-яЁё]', i18n.EN[node.value]))
                        parent = parents[node]
                        self.assertIsInstance(parent, ast.Call)
                        self.assertEqual(getattr(parent.func, 'id', ''), 'tr')

    def test_ui_and_recovery_messages_switch_together_without_translating_names(self):
        for lang, word in [('en', 'Settings'), ('ru', 'Настройки')]:
            i18n.set_language(lang)
            self.assertEqual(i18n.tr('Настройки'), word)
            self.assertEqual(i18n.tr('User-created profile'), 'User-created profile')
        i18n.set_language('en')
        with self.assertRaisesRegex(switch_save_sync.SyncError, 'IPv4 address and port'):
            sync_config.parse_endpoint('invalid')
        self.assertIn('Do not start', i18n.tr('Передача прервана. Не запускай эту игру на Switch. Оставь ftpsrv Save Sync открытым и повтори синхронизацию: она восстановит резервную копию. '))

    def test_host_preference_survives_restart_and_does_not_live_in_card_data(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LANG': 'en_US.UTF-8'}, clear=True):
            host = Path(folder) / 'host/preferences.json'
            card = Path(folder) / 'card/settings.json'
            card.parent.mkdir()
            original = b'{"schema":2,"host":"10.0.0.50","games":{}}'
            card.write_bytes(original)
            with patch.object(i18n, 'PREFERENCES', host):
                i18n.set_language('ru', persist=True)
                self.assertEqual(json.loads(host.read_text()), {'language': 'ru'})
                i18n.set_language('en')
                self.assertEqual(i18n.load_language(), 'ru')
                self.assertEqual(card.read_bytes(), original)
                i18n.set_language('en', persist=True)
                self.assertEqual(i18n.load_language(), 'en')

    def test_locale_fallback_and_invalid_preference_are_predictable(self):
        self.assertEqual(i18n.system_language({'LANG': 'ru_RU.UTF-8'}), 'ru')
        self.assertEqual(i18n.system_language({'LANG': 'de_DE.UTF-8'}), 'en')
        self.assertEqual(i18n.system_language({'LC_ALL': 'C', 'LANG': 'ru_RU.UTF-8'}), 'en')
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LANG': 'en_US.UTF-8'}, clear=True):
            path = Path(folder) / 'preferences.json'
            for data in ('broken JSON', '[]', '{"language":"xx"}'):
                path.write_text(data)
                self.assertEqual(i18n.preferred_language(path), 'en')
            path.write_text('{"language":"ru"}')
            with patch.dict(os.environ, {'SDS_LANGUAGE': 'en'}):
                self.assertEqual(i18n.preferred_language(path), 'en')

    def test_bilingual_installer_errors_use_only_the_selected_language(self):
        message = 'Exit Steam, then continue. / Заверши Steam и продолжи установку.'
        self.assertEqual(i18n.tr(message), 'Exit Steam, then continue.')
        i18n.set_language('ru')
        self.assertEqual(i18n.tr(message), 'Заверши Steam и продолжи установку.')
