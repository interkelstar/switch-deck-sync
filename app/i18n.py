"""English/Russian text and host-local language preferences."""
import json
import locale
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
PREFERENCES = BASE / 'preferences.json'
LANGUAGES = {'en': 'English', 'ru': 'Русский'}
EN = json.loads((BASE / 'locales/en.json').read_text(encoding='utf-8'))


def system_language(environ=None):
    env = os.environ if environ is None else environ
    value = env.get('LC_ALL') or env.get('LC_MESSAGES') or env.get('LANG') or ''
    if not value:
        try:
            value = locale.getlocale()[0] or ''
        except (ValueError, TypeError):
            value = ''
    return 'ru' if value.lower().startswith('ru') else 'en'


def preferred_language(path=None):
    path = PREFERENCES if path is None else Path(path)
    override = os.environ.get('SDS_LANGUAGE')
    if override in LANGUAGES:
        return override
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8')).get('language')
        if value in LANGUAGES:
            return value
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return system_language()


_language = preferred_language()


def language():
    return _language


def set_language(value, persist=False, path=None):
    path = PREFERENCES if path is None else Path(path)
    if value not in LANGUAGES:
        raise ValueError('Unsupported interface language')
    if persist:
        # Use the same durable file writer as sync, but keep preferences off-card.
        from switch_save_sync import atomic_json
        existing = {}
        try:
            existing = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if not isinstance(existing, dict):
            existing = {}
        atomic_json(Path(path), dict(existing, language=value))
    global _language
    _language = value


def load_language(path=None):
    set_language(preferred_language(path))
    return language()


def tr(message):
    if language() == 'en':
        return EN.get(message, message)
    if ' / ' in message and message in EN:
        return message.split(' / ', 1)[1]
    return message
