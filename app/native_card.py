"""Attach card data to stock EmuDeck paths. Never launch an emulator or map inputs."""
from i18n import tr
import i18n
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import card_library as card

LOCAL = Path(__file__).resolve().parent
UNIT = 'switch-deck-sync-card.service'


def active_game(proc=Path('/proc')):
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / 'cmdline').read_bytes().split(b'\0')
            name = Path(args[0].decode(errors='replace')).name.lower()
            if name in ('ryujinx', 'ryujinx.avalonia', 'ryujinx.headless.sdl2'):
                return True
            if any(Path(a.decode(errors='replace')).name == 'switch_save_sync.py' for a in args):
                return True
        except (OSError, ProcessLookupError):
            continue
    return False


def replace_link(path, target):
    if path.exists() and not path.is_symlink():
        raise card.LibraryError(tr('Путь подключения занят обычной папкой: ') + str(path))
    if path.is_symlink() and os.readlink(path) == str(target):
        return
    stage = path.with_name(path.name + '.' + uuid.uuid4().hex)
    try:
        stage.symlink_to(target, target_is_directory=True)
        stage.replace(path)
    finally:
        stage.unlink(missing_ok=True)


class DataManager:
    def __init__(self, host, local=LOCAL):
        self.host = host
        self.local = local
        self.root = Path(host['ryujinx_dir'])
        self.current = None
        self.directory_fd = None
        self.metadata = None
        self.signature = None

    def status(self, state, **details):
        card.write_changed(self.local / 'native-status.json', {'state': state, **details})

    def detach(self, state='absent', message=tr('Вставь подготовленную карту в выбранный слот.')):
        # A file target makes attempts to create a fallback local save fail with
        # ENOTDIR, instead of silently building a second library without the card.
        replace_link(self.local / 'active', Path('/dev/null'))
        if self.directory_fd is not None:
            os.close(self.directory_fd)
            self.directory_fd = None
        self.current = None
        self.metadata = None
        self.signature = None
        self.status(state, message=message)

    def verify_links(self):
        for path, target in self.host['native_links'].items():
            p = Path(path)
            if not p.is_symlink() or os.readlink(p) != target:
                raise card.LibraryError(tr('EmuDeck изменил подключение папок. Повтори установку: ') + str(p))

    def attach(self, mount, manifest, part):
        self.verify_links()
        shared = card.contained(mount, manifest['data_dir'])
        if not (shared / 'system/prod.keys').is_file():
            raise card.LibraryError(tr('На карте отсутствуют ключи Ryujinx.'))
        firmware = shared / 'bis/system/Contents/registered'
        if not firmware.is_dir() or not any(firmware.iterdir()):
            raise card.LibraryError(tr('На карте отсутствует установленная прошивка Ryujinx.'))
        for parent, directories, files in os.walk(shared, followlinks=False):
            for name in directories + files:
                if (Path(parent) / name).is_symlink():
                    raise card.LibraryError(tr('В данных профиля карты обнаружена ссылка. Нужны сами файлы данных.'))
        cache = self.local / 'libraries' / manifest['library_id'].lower() / 'games'
        cache.mkdir(parents=True, exist_ok=True)
        templates = manifest.get('game_metadata', {})
        for p in cache.glob('*/*.json'):
            if p.name in ('updates.json', 'dlc.json') and p.relative_to(cache).as_posix() not in templates:
                p.unlink()
        alias = self.local / 'active' / 'card'
        for relative, template in templates.items():
            target = card.contained(cache, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            card.write_changed(target, card.map_paths(template, alias))
        app = card.contained(mount, manifest['sync_dir'])
        settings = card.read(app / 'settings.json')
        settings.update(ryujinx_dir=str(self.root), save_root=str(self.root / 'bis/user/save'))
        card.write_changed(app / 'settings.json', settings)
        bundle = self.local / 'targets' / uuid.uuid4().hex
        bundle.mkdir(parents=True, mode=0o700)
        patches = card.contained(mount, self.patches_path(manifest))
        patches.mkdir(parents=True, exist_ok=True)
        targets = {name: shared / name for name in ('bis', 'system', 'mods', 'sdcard')}
        targets.update(card=mount, roms=card.contained(mount, manifest['rom_dir']), games=cache, sync=app, patches=patches)
        for name, target in targets.items():
            (bundle / name).symlink_to(target, target_is_directory=True)
        # This descriptor pins only the LOCAL bundle, not the mounted card. Normal
        # eject is not blocked. If the service crashes or the computer restarts,
        # /proc refuses directory creation behind this now-dead alias.
        new_fd = os.open(bundle, os.O_RDONLY | os.O_DIRECTORY)
        try:
            replace_link(self.local / 'active', Path('/proc') / str(os.getpid()) / 'fd' / str(new_fd))
        except BaseException:
            os.close(new_fd)
            raise
        if self.directory_fd is not None:
            os.close(self.directory_fd)
        self.directory_fd = new_fd
        self.current = (mount, manifest, part)
        self.signature = self.identity(mount, manifest, part)
        self.metadata = self.metadata_contents(cache)
        self.status('ready', library_id=manifest['library_id'], mount=str(mount))
        # Old bundles contain links only. They are never followed or recursively removed.
        for old in bundle.parent.iterdir():
            if old != bundle and old.is_dir() and not old.is_symlink():
                for link in old.iterdir():
                    if link.is_symlink():
                        link.unlink()
                try:
                    old.rmdir()
                except OSError:
                    pass

    @staticmethod
    def patches_path(manifest):
        return str(card.relative_path(manifest['data_dir']).parent / 'patchesAndDlc')

    @staticmethod
    def identity(mount, manifest, part):
        return (str(mount), part['path'], part.get('uuid'), manifest['library_id'],
                manifest['data_dir'], manifest['rom_dir'], manifest['sync_dir'], mount.stat().st_dev)

    @staticmethod
    def metadata_contents(cache):
        return {p.relative_to(cache).as_posix(): card.read(p) for p in cache.glob('*/*.json')
                if p.name in ('updates.json', 'dlc.json')}

    def export_changes(self):
        mount, manifest, _ = self.current
        cache = self.local / 'libraries' / manifest['library_id'].lower() / 'games'
        values = self.metadata_contents(cache)
        if values != self.metadata:
            extra = [(self.host['roms_dir'], manifest['rom_dir']),
                     (self.host['patches_dir'], self.patches_path(manifest))]
            card.export_metadata(mount, manifest, self.local / 'active/card', self.root, extra)
            self.metadata = values
            # Our own export becomes the baseline for detecting another host.
            updated = card.read(card.marker_path(mount))
            self.current = (mount, updated, self.current[2])

    def tick(self, devices=None, busy=None, allow_mount=True):
        try:
            self.verify_links()
            mount, manifest, part = card.locate(self.host, allow_mount, devices)
            signature = self.identity(mount, manifest, part)
            if signature == self.signature:
                # A sleeping host can miss removal and reinsertion of the same
                # card. Its filesystem identity stays the same, while another
                # host may have added or removed updates/DLC in the meantime.
                previous = self.current[1]
                if any(manifest.get(k) != previous.get(k) for k in ('game_metadata', 'games')):
                    if not (active_game() if busy is None else busy):
                        self.attach(mount, manifest, part)
                    return
                try:
                    self.export_changes()
                except (OSError, ValueError):
                    pass  # Ryujinx can be in the middle of replacing a metadata JSON.
                return
            is_busy = active_game() if busy is None else busy
            if is_busy:
                self.detach('busy', tr('Закрой Ryujinx и синхронизацию перед сменой библиотеки.'))
                return
            self.attach(mount, manifest, part)
        except (card.LibraryError, OSError, ValueError) as ex:
            self.detach('absent' if isinstance(ex, card.LibraryError) else 'error', str(ex))

    def close(self):
        self.detach('stopped', tr('Служба подключения карты остановлена.'))


def systemctl(*args, check=True):
    return subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, check=check)


def start_service(local, expected_id):
    systemctl('daemon-reload')
    systemctl('restart', UNIT)
    for _ in range(40):
        try:
            status = card.read(local / 'native-status.json')
            if status.get('state') == 'ready' and status.get('library_id') == expected_id:
                if (local / 'active/system/prod.keys').is_file():
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.25)
    raise card.LibraryError(tr('Не удалось подключить карту. Проверь, что она открывается в файловом менеджере, и повтори установку.'))


def stop_service():
    systemctl('stop', UNIT, check=False)


def watch(local=LOCAL):
    manager = DataManager(card.read(local / 'host.json'), local)
    stop = False

    def stopping(signum, frame):
        nonlocal stop
        stop = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stopping)
    manager.detach()
    inventory = None
    last_mounts = None
    next_scan = 0
    try:
        while not stop:
            try:
                with card.session_lock(local):
                    mounts = Path('/proc/self/mountinfo').read_bytes()
                    if mounts != last_mounts or time.monotonic() >= next_scan:
                        inventory = card.block_devices()
                        last_mounts = mounts
                        next_scan = time.monotonic() + 5
                    manager.tick(devices=inventory)
            except card.LibraryError:
                pass  # The sync application or setup currently owns the data mapping.
            time.sleep(0.5)
    finally:
        manager.close()


def run_sync(args, local=LOCAL):
    i18n.load_language(local / 'preferences.json')
    from switch_save_sync import ensure_idle
    ensure_idle()
    host = card.read(local / 'host.json')
    with card.session_lock(local):
        mount, manifest, _ = card.locate(host)
        status = card.read(local / 'native-status.json')
        if status.get('state') != 'ready' or status.get('library_id') != manifest['library_id'] or status.get('mount') != str(mount):
            raise card.LibraryError(tr('Карта ещё не подключена. Закрой игры и повтори запуск через секунду.'))
        if not (local / 'active').resolve().is_dir():
            raise card.LibraryError(tr('Карта ещё не подключена. Повтори запуск через секунду.'))
        if not (Path(host['ryujinx_dir']) / 'bis').resolve().is_relative_to(mount.resolve()):
            raise card.LibraryError(tr('Подключена другая библиотека. Закрой игры и подожди подключения карты.'))
        from sync_launcher import launch
        return launch(local / 'active/sync', args, local, portable=True)


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    mode = args.pop(0) if args else 'status'
    if mode == 'watch':
        watch()
        return 0
    if mode == 'sync':
        return run_sync(args)
    if mode == 'detach':
        replace_link(LOCAL / 'active', Path('/dev/null'))
        return 0
    if mode == 'status':
        print(json.dumps(card.read(LOCAL / 'native-status.json'), ensure_ascii=False))
        return 0
    raise card.LibraryError(tr('Неизвестное действие подключения карты.'))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (card.LibraryError, OSError, ValueError) as ex:
        if sys.argv[1:2] == ['sync']:
            subprocess.run(['kdialog', '--title', 'Switch Deck Sync', '--error', str(ex)], check=False)
        print(str(ex), file=sys.stderr)
        raise SystemExit(1)
