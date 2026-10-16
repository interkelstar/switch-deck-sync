"""KDE Desktop Mode setup wizard. All dialogs are provided by kdialog."""
import ctypes.util
import json
import locale
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import card_library as card
import setup_library as setup
import native_card


class Cancelled(Exception):
    pass


class Wizard:
    def __init__(self, package):
        self.package = package
        self.home = Path.home()
        self.ru = (os.environ.get('LANG', '') or locale.getlocale()[0] or '').lower().startswith('ru')
        self.progress_address = None
        self.dbus = shutil.which('qdbus6') or shutil.which('qdbus')

    def t(self, en, ru):
        return ru if self.ru else en

    def dialog(self, *args):
        result = subprocess.run(['kdialog', '--title', 'Switch Deck Sync', *map(str, args)],
                                capture_output=True, text=True)
        if result.returncode:
            raise Cancelled()
        return result.stdout.strip()

    def choose(self, heading, choices):
        if not choices:
            raise setup.SetupError(heading + ': ' + self.t('nothing found', 'ничего не найдено'))
        if len(choices) == 1:
            return choices[0][0]
        args = ['--radiolist', heading]
        for i, (_, label) in enumerate(choices):
            args += [str(i), label, 'on' if i == 0 else 'off']
        return choices[int(self.dialog(*args))][0]

    def file(self, heading, default):
        return Path(self.dialog('--getopenfilename', default, '*', '--title', heading))

    def directory(self, heading, default):
        return Path(self.dialog('--getexistingdirectory', default, '--title', heading))

    def progress(self, text):
        print(text, flush=True)
        if self.progress_address and self.dbus:
            subprocess.run([self.dbus, *self.progress_address, 'setLabelText', text], capture_output=True)

    def busy(self):
        if not self.dbus:
            return
        try:
            value = self.dialog('--progressbar', self.t('Installing and checking files…', 'Установка и проверка файлов…'), '0')
            self.progress_address = value.split()
            if self.dbus:
                subprocess.run([self.dbus, *self.progress_address, 'showCancelButton', 'false'], capture_output=True)
        except Cancelled:
            pass

    def end_busy(self):
        if self.progress_address and self.dbus:
            subprocess.run([self.dbus, *self.progress_address, 'close'], capture_output=True)
        self.progress_address = None

    def dependencies(self):
        missing = [name for name in ('lsblk', 'udisksctl', 'systemctl') if not shutil.which(name)]
        missing += [name for name in ('SDL2', 'SDL2_ttf') if not ctypes.util.find_library(name)]
        fonts = Path('/usr/share/fonts')
        if not any(fonts.rglob('DejaVuSans.ttf')):
            missing.append('DejaVu Sans')
        if missing:
            raise setup.SetupError(self.t('Missing dependencies: ', 'Не найдены зависимости: ') + ', '.join(missing))

    def close_steam(self):
        self.dialog('--msgbox', self.t(
            'Save and close your games and Switch Deck Sync. Steam will close to update your library. Open Steam again after setup.',
            'Сохранись и закрой игры и Switch Deck Sync. Steam закроется для обновления библиотеки. После установки открой Steam снова.'))
        setup.require_idle(steam=False)
        if shutil.which('steam'):
            subprocess.run(['steam', '-shutdown'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        for _ in range(40):
            try:
                setup.require_idle()
                return
            except setup.SetupError:
                time.sleep(0.5)
        raise setup.SetupError(self.t('Steam is still running. Exit it from its menu and retry.', 'Steam всё ещё работает. Заверши его через меню и повтори установку.'))

    def select_card(self):
        devices = [d for d in card.block_devices() if d.get('type') == 'disk' and
                   (d.get('tran') == 'mmc' or d.get('rm') or d.get('tran') == 'usb')]
        # lsblk does not always expose RM in our minimal inventory; USB choice is explicit.
        choices = []
        for d in devices:
            parts = card.partitions(d)
            mounts = [m for p in parts for m in p.get('mountpoints', []) if m]
            choices.append((d, d['path'] + ' — ' + str(d.get('size', '')) + ' ' + (d.get('model') or '') + ' — ' +
                            (', '.join(mounts) or self.t('not mounted', 'не подключена'))))
        device = self.choose(self.t('Select the card reader to use for Switch libraries', 'Выбери считыватель для карт с библиотеками Switch'), choices)
        slot = setup.reader_slot(device)
        if slot['kind'] == 'mmc' and len([d for d in devices if d.get('tran') == 'mmc']) > 1:
            raise setup.SetupError('Multiple MMC readers are not yet supported by this setup wizard.')
        parts = [(p, p['path'] + ' — ' + (p.get('fstype') or '?')) for p in card.partitions(device)
                 if p.get('fstype') not in (None, 'crypto_LUKS', 'swap')]
        part = self.choose(self.t('Select the library partition', 'Выбери раздел с библиотекой'), parts)
        if part.get('fstype') != 'ext4':
            raise setup.SetupError(self.t('This preview requires an ext4 card, as formatted by SteamOS. The installer does not format cards.', 'Для этой версии нужна карта ext4, как после форматирования в SteamOS. Установщик карты не форматирует.'))
        mounts = [m for m in part.get('mountpoints', []) if m]
        if not mounts:
            subprocess.run(['udisksctl', 'mount', '--no-user-interaction', '-b', part['path']], check=True, capture_output=True)
            part = next(p for d in card.block_devices() for p in card.partitions(d) if p['path'] == part['path'])
            mounts = [m for m in part.get('mountpoints', []) if m]
        if len(mounts) != 1:
            raise setup.SetupError('Cannot determine the mount point / Не удалось определить папку карты')
        return Path(mounts[0]), slot

    def steam_profile(self):
        bases = [self.home / '.local/share/Steam', self.home / '.steam/steam']
        configs = list(dict.fromkeys(p.resolve() for base in bases for p in base.glob('userdata/*/config')
                                    if p.parent.name.isdigit() and p.parent.name != '0'))
        if not configs:
            raise setup.SetupError(self.t('Sign into Steam once before installing.', 'Перед установкой один раз войди в Steam.'))
        if len(configs) == 1:
            return configs[0]
        names = {}
        for base in bases:
            login = base / 'config/loginusers.vdf'
            if not login.is_file():
                continue
            for match in re.finditer(r'"(\d{17})"\s*\{([^{}]*)\}', login.read_text(encoding='utf-8')):
                name = re.search(r'"PersonaName"\s*"((?:\\.|[^"\\])*)"', match[2])
                if name:
                    names[str(int(match[1]) - 76561197960265728)] = name[1].replace('\\"', '"').replace('\\\\', '\\')
        return self.choose(self.t('Steam account for shortcuts', 'Аккаунт Steam для ярлыков'),
                           [(p, names.get(p.parent.name, p.parent.name)) for p in configs])

    def recover(self):
        local = self.home / '.local/share/switch-deck-sync'
        pending = [p.parent for p in (local / 'backups').glob('*/transaction.json')
                   if card.read(p).get('status') == 'in-progress']
        if not pending:
            return
        self.dialog('--msgbox', self.t('A previous setup was interrupted. Its changes will be rolled back before retrying.', 'Предыдущая установка прервалась. Сначала восстановим прежние настройки.'))
        self.close_steam()
        native_card.stop_service()
        with card.session_lock(local):
            for folder in sorted(pending, reverse=True):
                setup.restore(folder)
        native_card.systemctl('daemon-reload')
        if (self.home / '.config/systemd/user' / native_card.UNIT).is_file():
            native_card.systemctl('restart', native_card.UNIT)

    def restore_previous(self):
        local = self.home / '.local/share/switch-deck-sync'
        info = card.read(local / 'installation.json')
        folder = Path(info['backup'])
        self.dialog('--yesno', self.t('Restore settings and Steam shortcuts from before the last installation? Card games and saves will be retained.', 'Восстановить настройки и ярлыки Steam до последней установки? Игры и сейвы на карте сохранятся.'))
        self.close_steam()
        native_card.stop_service()
        with card.session_lock(local):
            setup.restore(folder)
        native_card.systemctl('daemon-reload')
        if (self.home / '.config/systemd/user' / native_card.UNIT).is_file():
            native_card.systemctl('restart', native_card.UNIT)
        self.dialog('--msgbox', self.t('Previous settings restored. Open Steam from the application menu.', 'Прежние настройки восстановлены. Открой Steam через меню приложений.'))

    def run(self):
        self.dependencies()
        self.ru = self.choose('Language / Язык', [(False, 'English'), (True, 'Русский')])
        self.dialog('--msgbox', self.t(
            'Set up your Switch game library and Wi-Fi save sync on this computer. Connect your memory card to get started.',
            'Настрой библиотеку игр Switch и обмен сейвами по Wi-Fi на этом компьютере. Для начала подключи карту памяти.'))
        self.recover()
        if (self.home / '.local/share/switch-deck-sync/installation.json').is_file():
            action = self.choose(self.t('Choose an action', 'Выбери действие'),
                                 [('install', self.t('Install or update', 'Установить или обновить')),
                                  ('restore', self.t('Restore the previous settings', 'Восстановить прежние настройки'))])
            if action == 'restore':
                self.restore_previous()
                return
        mount, slot = self.select_card()
        ready = card.marker_path(mount).is_file()
        if ready:
            mode = 'attach'
            manifest = card.validated_manifest(mount)
        else:
            mode = self.choose(self.t('This card has no portable library yet', 'На карте пока нет переносимой библиотеки'),
                               [('prepare', self.t('Prepare from my Ryujinx installation', 'Подготовить из моей установки Ryujinx'))])
            manifest = None
        roms, executable = setup.native_paths(self.home)
        root = self.home / '.config/Ryujinx'
        if not (root / 'Config.json').is_file():
            raise setup.SetupError(self.t('Start and close Ryujinx once from the application menu, then retry.', 'Один раз открой и закрой Ryujinx через меню приложений, затем повтори установку.'))
        config = card.read(root / 'Config.json')
        rom_dirs = []
        if mode == 'prepare':
            options = list(dict.fromkeys([Path(p) for p in config.get('game_dirs', []) if Path(p).is_dir()] +
                                         ([mount / 'Emulation/roms/switch'] if (mount / 'Emulation/roms/switch').is_dir() else [])))
            use_all = self.t('Use all detected game folders', 'Использовать все найденные папки с играми')
            selected = self.choose(self.t('Games to include', 'Какие игры включить'),
                                   ([(options, use_all + ': ' + ', '.join(map(str, options)))] if options else []) + [(None, self.t('Browse…', 'Выбрать папку…'))])
            rom_dirs = selected or [self.directory(self.t('Folder with your Switch games', 'Папка с твоими играми Switch'), mount)]
        steam_config = self.steam_profile()
        count = len(card.catalog_games(mount, manifest)) if ready else self.t('from selected folders', 'из выбранных папок')
        details = self.t('Connect existing card', 'Подключить готовую карту') if ready else self.t('Copy and verify data; originals are retained', 'Скопировать и проверить данные; оригиналы сохраняются')
        self.dialog('--yesno', self.t('Install Switch Deck Sync?', 'Установить Switch Deck Sync?') + '\n\n' +
                    details + '\n' + str(mount) + '\n' + self.t('Games: ', 'Игры: ') + str(count) + '\n\n' +
                    self.t('Your games and Switch Deck Sync will appear in Steam. A backup will be saved so you can undo setup.',
                           'В Steam появятся игры и Switch Deck Sync. Для отмены установки будет сохранена резервная копия.'))
        self.close_steam()
        self.busy()
        try:
            setup.install(self.package, self.home, mount, slot, executable, root, steam_config,
                          mode, rom_dirs, self.progress)
        finally:
            self.end_busy()
        if ready:
            message = self.t(
                'Setup complete. Open Steam from the application menu to play your games or launch Switch Deck Sync. Your card’s sync settings are ready to use.',
                'Установка завершена. Открой Steam через меню приложений, чтобы играть или запустить Switch Deck Sync. Настройки синхронизации с карты уже готовы к использованию.')
        else:
            message = self.t(
                'Setup complete. Open Steam from the application menu, then launch Switch Deck Sync to choose your Switch address, profiles and games. For Switch setup, see docs/SWITCH.md in this folder.',
                'Установка завершена. Открой Steam через меню приложений, затем запусти Switch Deck Sync и выбери адрес Switch, профили и игры. Настройка самого Switch описана в docs/SWITCH.md в этой папке.')
        self.dialog('--msgbox', message)


def main(package):
    if sys.platform != 'linux':
        raise SystemExit('Run this installer on SteamOS / Linux, in Desktop Mode.')
    if not shutil.which('kdialog'):
        raise SystemExit('KDE kdialog is required. Run on SteamOS in Desktop Mode.')
    wizard = Wizard(package)
    try:
        wizard.run()
    except Cancelled:
        return 0
    except Exception as ex:
        wizard.end_busy()
        subprocess.run(['kdialog', '--title', 'Switch Deck Sync', '--error', str(ex)], check=False)
        return 1
    return 0
