"""Run save sync with either local settings or an attached card's settings."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import card_library as card

LOCAL = Path(__file__).resolve().parent


def launch(data, args, local=LOCAL, portable=False):
    env = dict(os.environ, SDS_DATA_DIR=str(data))
    env.pop('SDS_PORTABLE_LIBRARY', None)
    if portable:
        env['SDS_PORTABLE_LIBRARY'] = '1'
    command = ['/usr/bin/python3', str(local / 'switch_save_sync.py'), *args]
    if shutil.which('systemd-inhibit'):
        prefix = ['systemd-inhibit', '--no-ask-password', '--what=sleep:idle', '--mode=block']
        if subprocess.run([*prefix, '/usr/bin/true'], capture_output=True).returncode == 0:
            command = [*prefix, '--who=Switch Deck Sync', '--why=Save synchronisation', *command]
    child = subprocess.Popen(command, env=env)
    previous = {sig: signal.signal(sig, lambda s, f: child.send_signal(s))
                for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        return child.wait()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def standalone(args, local=LOCAL):
    from switch_save_sync import ensure_idle
    ensure_idle()
    with card.session_lock(local):
        if card.read(local / 'installation.json').get('architecture') != 'sync-only':
            raise card.LibraryError('Открой Switch Deck Sync установленным ярлыком.')
        data = local / 'data'
        if not (data / 'settings.json').is_file():
            raise card.LibraryError('Не найдены настройки. Повтори установку Switch Deck Sync.')
        return launch(data, args, local)


if __name__ == '__main__':
    try:
        raise SystemExit(standalone(sys.argv[1:]))
    except (card.LibraryError, OSError, ValueError) as ex:
        subprocess.run(['kdialog', '--title', 'Switch Deck Sync', '--error', str(ex)], check=False)
        raise SystemExit(1)
