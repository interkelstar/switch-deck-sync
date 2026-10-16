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
import srm_artwork


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

    def dependencies(self, portable=False):
        missing = [name for name in ('lsblk', 'udisksctl', 'systemctl') if not shutil.which(name)] if portable else []
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
        try:
            setup.require_idle()
            return
        except setup.SetupError:
            pass
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

    def steam_profile(self, required=True):
        bases = [self.home / '.local/share/Steam', self.home / '.steam/steam']
        configs = list(dict.fromkeys(p.resolve() for base in bases for p in base.glob('userdata/*/config')
                                    if p.parent.name.isdigit() and p.parent.name != '0'))
        if not configs:
            if not required:
                return None
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
        had_unit = (self.home / '.config/systemd/user' / native_card.UNIT).is_file()
        if had_unit:
            native_card.stop_service()
        with card.session_lock(local):
            for folder in sorted(pending, reverse=True):
                setup.restore(folder)
        if had_unit:
   …14848 tokens truncated…0дрес пока не указан'
                text('Switch: '+address+((':'+str(settings['port'])) if settings.get('host') else ''),66,278)
                text('Профили: '+settings.get('switch_profile_name','не выбран')+'  ↔  '+settings.get('deck_profile_name','не выбран'),66,326)
                text('Выбрано игр: '+str(len(settings['games'])),66,374)
                text('Закрой игры на обоих устройствах. На Switch открой ftpsrv Save Sync.',66,462,26,(166,185,203))
                if (core.HOME/'pending.json').exists():text('Есть прерванная передача — повтори синхронизацию.',66,546,22,(250,174,117))
                buttons=[(66,646,410,76,'Синхронизировать'),(506,646,350,76,'Настройки'),(886,646,328,76,'Выход')]
            elif phase=='settings':
                labels=[('Адрес Switch',settings.get('host','')+':'+str(settings['port'])),('Папка Ryujinx',settings['ryujinx_dir']),('Профиль Switch',settings.get('switch_profile_name','Выбрать')),('Профиль Ryujinx',settings.get('deck_profile_name','Выбрать')),('Игры',str(len(settings['games']))+' выбрано')]
                for i,(label,value) in enumerate(labels):buttons.append((66,184+i*85,1148,70,label+'   ·   '+value))
                buttons.append((864,646,350,76,'Назад'))
            elif phase in ['working','loading']:
                text('Синхронизация' if phase=='working' else 'Поиск',66,224,32)
                text(status,66,294,26)
                fill((66,395,1148,12),(43,53,68));pos=int((sdl.SDL_GetTicks()%2400)/2400*900)
                fill((66+pos,395,240,12),(52,202,221))
                text('Оставь ftpsrv Save Sync открытым на Switch.',66,475,26,(168,183,202))
                text('Перед заменой сохраняются резервные копии.',66,520,22,(145,164,187))
            elif phase=='done':
                text('Проверка завершена',66,188,32,(114,220,169))
                y=245
                for result in results[:5]:text(result,66,y,22);y+=66
                if len(results)>5:text('Ещё '+str(len(results)-5)+' игр. Полный итог сохранён в журнале.',66,580,22)
                else:text('Можно закрыть ftpsrv и запускать игру.',66,582,26,(168,183,202))
                buttons=[(864,646,350,76,'Готово')]
            elif phase=='conflict':
                text('Нужно выбрать копию',66,210,32,(245,193,104));text(status,66,270,26)
                text('Выбери прогресс для обоих устройств. Обе версии уже сохранены в резерве. Даты файлов не определяют выбор.',66,330,26)
                buttons=[(66,630,350,82,'Взять Switch'),(465,630,350,82,'Взять Ryujinx'),(864,630,350,82,'Пропустить')]
            elif phase=='error':
                text('Не удалось завершить',66,200,32,(245,158,137));text(error,66,270,26)
                buttons=[(465,646,350,76,'Настройки'),(864,646,350,76,'На главный')]
            elif phase=='edit':
                text('Адрес Switch' if edit_kind=='server' else 'Папка данных Ryujinx',66,180,32)
                text('Steam + X — клавиатура. B — отменить.',66,236,22,(168,183,202))
                fill((66,295,1148,90),(34,48,64));text(entry+'|',84,312,26,width=1100)
                text(error,66,408,22,(245,193,104))
                buttons=[(465,646,350,76,'Сохранить'),(864,646,350,76,'Отмена')]
            elif phase=='pick':
                title={'switch':'Выбери профиль Switch','deck':'Выбери профиль Ryujinx','games':'Игры для синхронизации'}[pick_kind]
                text(title,66,160,32)
                if pick_kind=='games':text('Все сейвы Switch. Для синхронизации нужен сейв и в Ryujinx.',66,204,22,(147,174,195))
                if not choices:text('Общих сохранений пока нет. Запусти игру и создай сейв на обоих устройствах.',66,270,26)
                for i,item in enumerate(choices[page*4:page*4+4]):
                    mark=('[✓] ' if item['key'] in selected else '[  ] ') if pick_kind=='games' else ''
                    if pick_kind=='games' and not item['available']:mark='Нет сейва Ryujinx · '
                    buttons.append((66,247+i*78,1148,65,mark+item['name']))
                text(error or ('Страница '+str(page+1)+' / '+str(max(1,(len(choices)+3)//4))),66,584,22,(245,193,104) if error else (147,174,195))
                buttons.extend([(66,646,250,76,'← Назад'),(346,646,250,76,'Вперёд →'),(626,646,285,76,'Применить'),(941,646,273,76,'Отмена')])
            selection=min(selection,max(0,len(buttons)-1))
            for i,(x,y,w,h,label) in enumerate(buttons):
                fill((x,y,w,h),(34,112,140) if i==selection else (30,44,61))
                width=I();height=I();original=label
                while label:
                    ttf.TTF_SizeUTF8(fonts[22],label.encode(),C.byref(width),C.byref(height))
                    if width.value<=w-40:break
                    original=original[:-1];label=original+'…'
                text(label,x+20,y+18,22,width=w-35)
            if buttons:text('A — выбрать     B — назад     Крестовина — перемещение',66,756,22,(145,164,187))
            sdl.SDL_RenderPresent(renderer)
    finally:
        sdl.SDL_StopTextInput()
        for texture,_,_ in cache.values():sdl.SDL_DestroyTexture(texture)
        for font in fonts.values():ttf.TTF_CloseFont(font)
        for controller in controllers:sdl.SDL_GameControllerClose(controller)
        sdl.SDL_DestroyRenderer(renderer);sdl.SDL_DestroyWindow(window);ttf.TTF_Quit();sdl.SDL_Quit()
    return 0
