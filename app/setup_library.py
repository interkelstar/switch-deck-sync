"""Installation engine. No downloads, sudo, formatting or deletion of source data."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

import card_library as card
import steam_shortcuts
import native_card
import legacy_migration

VERSION = '0.4.0-preview'
SHARED = ('bis', 'system', 'mods', 'sdcard')
RUNTIME = ('card_library.py', 'native_card.py', 'switch_save_sync.py', 'sync_config.py', 'sync_ui.py',
           'setup_library.py', 'setup_wizard.py', 'steam_shortcuts.py', 'legacy_migration.py',
           'sync_launcher.py', 'srm_artwork.py')


class SetupError(Exception):
    pass


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_verified(source, target, progress=lambda text: None):
    """Sources can contain EmuDeck links. Materialise their content on the card."""
    source = source.resolve(strict=True)
    if not source.is_file():
        raise SetupError('Not a regular file: ' + str(source))
    if target.is_symlink():
        raise SetupError('Unexpected destination link: ' + str(target))
    if target.exists():
        if not target.is_file() or target.stat().st_size != source.stat().st_size or digest(target) != digest(source):
            raise SetupError('Different file already exists: ' + str(target))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + '.sds-copy-' + uuid.uuid4().hex)
    progress('Copy / проверка: ' + source.name)
    try:
        with source.open('rb') as src, temp.open('xb') as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        if digest(source) != digest(temp):
            raise SetupError('Copy verification failed: ' + source.name)
        temp.replace(target)
        sync_dir(target.parent)
    finally:
        temp.unlink(missing_ok=True)


def copy_tree(source, target, progress=lambda text: None, ancestors=frozenset()):
    if target.is_symlink():
        raise SetupError('Unexpected destination directory link: ' + str(target))
    source = source.resolve(strict=True)
    if source in ancestors:
        raise SetupError('Circular source link: ' + str(source))
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for p in sorted(source.iterdir()):
            copy_tree(p, target / p.name, progress, ancestors | {source})
    else:
        copy_verified(source, target, progress)


class Transaction:
    """Durable undo journal. Originals are retained for an explicit restore."""
    def __init__(self, folder):
        self.folder = folder
        folder.mkdir(parents=True, mode=0o700)
        self.items = []
        self.status = 'in-progress'
        self.save()

    def save(self):
        sync_dir(self.folder)
        card.write_changed(self.folder / 'transaction.json',
                           {'schema': 1, 'status': self.status, 'items': self.items})
        sync_dir(self.folder)

    def replace(self, path, data=None, link=None, mode=0o644):
        path = Path(path).absolute()
        if any(i['path'] == str(path) for i in self.items):
            raise SetupError('Duplicate transaction target: ' + str(path))
        if path.is_dir() and not path.is_symlink():
            raise SetupError('Refusing to replace a directory: ' + str(path))
        backup = self.folder / ('original-' + str(len(self.items)))
        existed = path.exists() or path.is_symlink()
        if existed:
            if path.is_symlink():
                backup.symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, backup)
                with backup.open('rb') as f:
                    os.fsync(f.fileno())
        # Journal before changing the path; recovery also handles a power loss here.
        self.items.append({'path': str(path), 'backup': backup.name if existed else None})
        self.save()
        path.parent.mkdir(parents=True, exist_ok=True)
        stage = path.with_name(path.name + '.sds-' + uuid.uuid4().hex)
        try:
            if link is not None:
                stage.symlink_to(link, target_is_directory=True)
            else:
                with stage.open('xb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                stage.chmod(mode)
            stage.replace(path)
            sync_dir(path.parent)
        finally:
            stage.unlink(missing_ok=True)

    def commit(self):
        self.status = 'complete'
        self.save()

    def redirect(self, path, target):
        """Keep existing real directories by rename, then install a data link."""
        path = Path(path).absolute()
        if not path.is_dir() or path.is_symlink():
            return self.replace(path, link=target)
        if path.stat().st_dev != self.folder.stat().st_dev:
            raise SetupError('Cannot safely back up a directory on another filesystem: ' + str(path))
        if any(i['path'] == str(path) for i in self.items):
            raise SetupError('Duplicate transaction target: ' + str(path))
        backup = self.folder / ('original-' + str(len(self.items)))
        self.items.append({'path': str(path), 'backup': backup.name, 'directory': True})
        self.save()
        path.rename(backup)
        sync_dir(path.parent)
        sync_dir(self.folder)
        path.symlink_to(target, target_is_directory=True)
        sync_dir(path.parent)

    def park(self, path):
        """Retire an old runtime by rename; restore uses the same directory journal."""
        path = Path(path).absolute()
        if not path.is_dir() or path.is_symlink() or path.stat().st_dev != self.folder.stat().st_dev:
            raise SetupError('Cannot safely retire legacy runtime: ' + str(path))
        if any(i['path'] == str(path) for i in self.items):
            raise SetupError('Duplicate transaction target: ' + str(path))
        backup = self.folder / ('original-' + str(len(self.items)))
        self.items.append({'path': str(path), 'backup': backup.name, 'directory': True})
        self.save()
        path.rename(backup)
        sync_dir(path.parent)
        sync_dir(self.folder)

    def rollback(self):
        restore(self.folder)
        self.status = 'rolled-back'


def restore(folder):
    """Only installer-owned paths are journalled; no card data is ever removed."""
    journal = card.read(folder / 'transaction.json')
    for item in reversed(journal['items']):
        path = Path(item['path'])
        if item.get('directory'):
            backup = folder / item['backup']
            if backup.exists():
                if path.is_symlink():
                    path.unlink()
                elif path.exists():
                    raise SetupError('Refusing to overwrite a new directory during restore: ' + str(path))
                backup.rename(path)
                sync_dir(path.parent)
                sync_dir(folder)
            elif not path.is_dir() or path.is_symlink():
                raise SetupError('Directory backup is unavailable: ' + str(path))
            continue
        if path.is_dir() and not path.is_symlink():
            raise SetupError('Restore target is now a directory: ' + str(path))
        backup = folder / item['backup'] if item['backup'] else None
        if backup is not None:
            stage = path.with_name(path.name + '.restore-' + uuid.uuid4().hex)
            if backup.is_symlink():
                stage.symlink_to(os.readlink(backup))
            else:
                shutil.copy2(backup, stage)
            stage.replace(path)
        else:
            path.unlink(missing_ok=True)
        sync_dir(path.parent)
    journal['status'] = 'rolled-back'
    card.write_changed(folder / 'transaction.json', journal)
    sync_dir(folder)


def emulator_roots(home):
    candidates = [home / '.config/Ryujinx', home / 'Applications/publish/portable']
    candidates += list((home / 'Applications').glob('**/portable'))
    candidates += list((home / '.var/app').glob('*/config/Ryujinx'))
    return list(dict.fromkeys(p for p in candidates if (p / 'Config.json').is_file()))


def emulator_executables(home):
    candidates = [home / 'Applications/publish/Ryujinx']
    for pattern in ('**/Ryujinx', '*Ryujinx*.AppImage', '*ryujinx*.AppImage'):
        candidates += list((home / 'Applications').glob(pattern))
    return list(dict.fromkeys(p for p in candidates if p.is_file() and os.access(p, os.X_OK)))


def reader_slot(device, by_path=Path('/dev/disk/by-path')):
    if device.get('tran') == 'mmc' and re.fullmatch(r'mmcblk\d+', device['name']):
        return {'kind': 'mmc'}
    links = sorted(p for p in by_path.glob('*')
                   if p.is_symlink() and '-part' not in p.name
                   and str(p.resolve()) == device['path'])
    if not links:
        raise SetupError('No stable hardware path for this reader. / Нет пути считывателя.')
    return {'kind': 'reader-path', 'path': str(links[0])}


def require_idle(proc=Path('/proc'), steam=True):
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = (p / 'cmdline').read_bytes().split(b'\0')
            name = Path(args[0].decode(errors='replace')).name.lower()
            if name in ('ryujinx', 'ryujinx.avalonia', 'ryujinx.headless.sdl2') or any(
                    b'switch_save_sync.py' in a or b'card_library.py' in a for a in args):
                raise SetupError('Close Ryujinx and save sync. / Закрой эмулятор и синхронизацию.')
            if steam and name in ('steam', 'steamwebhelper'):
                raise SetupError('Exit Steam, then continue. / Заверши Steam и продолжи установку.')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def portable_metadata(root, mount, progress):
    templates = {}
    patches = mount / 'Emulation/storage/ryujinx/patchesAndDlc'

    def convert(value):
        if isinstance(value, str) and value.lower().endswith(('.nsp', '.xci')):
            path = Path(value)
            if not path.is_absolute():
                raise SetupError('Update/DLC path is not absolute: ' + value)
            path = path.resolve(strict=True)
            if path.is_relative_to((mount / 'Emulation').resolve()):
                return '@CARD@/' + path.relative_to(mount.resolve()).as_posix()
            # Content hash prefix avoids collisions between equally named DLC files.
            target = patches / (digest(path)[:16] + '-' + path.name)
            copy_verified(path, target, progress)
            return '@CARD@/' + target.relative_to(mount).as_posix()
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    for p in sorted((root / 'games').glob('*/*.json')):
        if p.name in ('updates.json', 'dlc.json'):
            templates[p.relative_to(root / 'games').as_posix()] = convert(card.read(p))
    return templates


def prepare_card(mount, source_root, rom_dirs, progress=lambda text: None, sync_source=None):
    """Publish the marker only after complete, verified copies. Source data stays put."""
    if card.marker_path(mount).exists():
        raise SetupError('Library already exists: use Attach. / Выбери подключение готовой карты.')
    for relative in ('Emulation/storage/ryujinx/data', 'Emulation/storage/ryujinx/.sds-preparing-data',
                     'Emulation/roms/switch', 'Emulation/tools/switch-save-sync'):
        card.contained(mount, relative)
    data = mount / 'Emulation/storage/ryujinx/data'
    pending = mount / 'Emulation/.switch-deck-sync-preparation.json'
    intent = {'source': str(source_root.resolve()), 'roms': [str(p.resolve()) for p in rom_dirs]}
    resuming = pending.is_file() and card.read(pending) == intent
    sync = mount / 'Emulation/tools/switch-save-sync'
    if sync.exists() and not resuming:
        raise SetupError('Unregistered sync folder exists; preserve it before preparing this card.')
    if data.exists() and not resuming:
        raise SetupError('Target data folder already exists. / Папка данных уже занята: ' + str(data))
    if not (source_root / 'system/prod.keys').is_file():
        raise SetupError('Install your dumped prod.keys in Ryujinx first. / Добавь свои ключи в Ryujinx.')
    firmware = source_root / 'bis/system/Contents/registered'
    if not firmware.is_dir() or not any(firmware.iterdir()):
        raise SetupError('Install your dumped firmware in Ryujinx first. / Установи свою прошивку в Ryujinx.')
    if not (source_root / 'system/Profiles.json').is_file():
        raise SetupError('Start Ryujinx once to initialise a user profile. / Один раз запусти Ryujinx.')
    if pending.exists() and not resuming:
        raise SetupError('A different preparation is pending on this card. / На карте другая незавершённая подготовка.')
    stage_path = data.with_name('.sds-preparing-data')
    if stage_path.exists() and not resuming:
        raise SetupError('An unregistered staging folder exists on this card.')
    pending.parent.mkdir(parents=True, exist_ok=True)
    card.write_changed(pending, intent)
    stage = data if data.exists() else data.with_name('.sds-preparing-data')
    if stage.is_symlink():
        raise SetupError('Unexpected preparation symlink')
    stage.mkdir(parents=True, exist_ok=True)
    # Leave an identifiable partial folder on failure; it is never treated as a library.
    for name in SHARED:
        if (source_root / name).exists():
            copy_tree(source_root / name, stage / name, progress)
        else:
            (stage / name).mkdir(exist_ok=True)
    (stage / 'bis/user/save').mkdir(parents=True, exist_ok=True)
    roms = mount / 'Emulation/roms/switch'
    roms.mkdir(parents=True, exist_ok=True)
    for folder in rom_dirs:
        if roms.resolve() != folder.resolve() and roms.resolve().is_relative_to(folder.resolve()):
            raise SetupError('Select the game folder itself, not its parent card folder.')
        for p in sorted(folder.rglob('*')):
            if p.is_file() and p.suffix.lower() in ('.xci', '.nsp'):
                copy_verified(p, roms / p.relative_to(folder), progress)
    metadata = portable_metadata(source_root, mount, progress)
    sync.mkdir(parents=True, exist_ok=True)
    if sync_source is not None:
        copy_tree(sync_source, sync, progress)
    for filename, value in [('settings.json', {'schema': 2, 'host': '', 'port': 5000, 'games': {}}), ('state.json', {})]:
        if not (sync / filename).exists():
            card.write_changed(sync / filename, value)
    if stage != data:
        stage.rename(data)
    value = {'schema': 2, 'kind': 'switch-library', 'library_id': uuid.uuid4().hex,
             'data_dir': data.relative_to(mount).as_posix(), 'rom_dir': roms.relative_to(mount).as_posix(),
             'sync_dir': sync.relative_to(mount).as_posix(), 'games': [], 'game_metadata': metadata}
    value['games'] = card.catalog_games(mount, value)
    # Optional Ryujinx game titles improve filenames without hardcoded game lists.
    for game in value['games']:
        title = card.game_id(game)
        p = source_root / 'games' / (title or '').lower() / 'gui/metadata.json'
        if title and p.is_file():
            game['name'] = card.read(p).get('title') or game['name']
    card.write_changed(mount / 'Emulation/switch-library.json', value)
    sync_dir(mount / 'Emulation')
    pending.unlink()
    sync_dir(mount / 'Emulation')
    return card.validated_manifest(mount)


def quoted_exec(path):
    # Desktop Entry Exec quoting; never interpreted by a shell.
    return '"' + str(path).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def native_paths(home):
    """Read path fields only; never execute or print EmuDeck's shell settings."""
    try:
        roms, launcher = legacy_migration.native_paths(home)
    except ValueError as ex:
        raise SetupError(str(ex)) from ex
    backend = home / '.config/EmuDeck/backend'
    if not launcher.is_file() or not (backend / 'functions/EmuScripts/emuDeckRyujinx.sh').is_file():
        raise SetupError('The stock EmuDeck Ryujinx launcher is missing. Install Ryujinx through EmuDeck first.')
    return roms, launcher


def install_app(tx, package, home, local, steam_config, original_shortcuts, sync_module, repairs=()):
    """Install the sync application; game-library management belongs to SRM."""
    for name in RUNTIME:
        tx.replace(local / name, (package / 'app' / name).read_bytes())
    for path in sorted((package / 'art').iterdir()):
        if path.is_file():
            tx.replace(local / 'art' / path.name, path.read_bytes())
    for name in ('LICENSE', 'VERSION'):
        tx.replace(local / name, (package / name).read_bytes())
    mode = ' sync' if sync_module == 'native_card.py' else ''
    script = '#!/bin/sh\nset -eu\nBASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec /usr/bin/python3 "$BASE/' + sync_module + '"' + mode + ' "$@"\n'
    tx.replace(local / 'sync.sh', script.encode(), mode=0o755)
    if steam_config is not None:
        entry = {'appname': 'Switch Deck Sync', 'exe': '"' + str(local / 'sync.sh') + '"',
                 'StartDir': '"' + str(local) + '"', 'LaunchOptions': '', 'icon': str(local / 'art/icon.ico')}
        data, ids = steam_shortcuts.upsert(original_shortcuts, [entry, *repairs])
        tx.replace(steam_config / 'shortcuts.vdf', data)
        for source, suffix in [('cover', 'p'), ('hero', '_hero'), ('logo', '_logo'), ('grid', '')]:
            tx.replace(steam_config / 'grid' / (str(ids['Switch Deck Sync']) + suffix + '.png'),
                       (package / 'art' / (source + '.png')).read_bytes())
    text = '[Desktop Entry]\nType=Application\nName=Switch Deck Sync\nExec=' + quoted_exec(local / 'sync.sh') + '\nIcon=' + str(local / 'art/icon.png') + '\nTerminal=false\nCategories=Game;Utility;\n'
    tx.replace(home / '.local/share/applications/switch-deck-sync.desktop', text.encode())


def check_pending_setup(local):
    for pending in (local / 'backups').glob('*/transaction.json'):
        if card.read(pending)['status'] == 'in-progress':
            raise SetupError('Interrupted setup: restore it first. / Восстанови прерванную установку: ' + str(pending.parent))


def install_sync_only(package, home, source_root, steam_config=None, idle_check=None):
    """Add save sync to an existing Ryujinx setup without requiring a card/EmuDeck."""
    idle_check = idle_check or (lambda: require_idle(steam=steam_config is not None))
    idle_check()
    if not (source_root / 'Config.json').is_file() or not (source_root / 'bis/user/save').is_dir():
        raise SetupError('Start Ryujinx once and select its data folder. / Один раз запусти Ryujinx и выбери его папку данных.')
    local = home / '.local/share/switch-deck-sync'
    local.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (home / '.config/systemd/user' / native_card.UNIT).exists() or legacy_migration.detect(home):
        raise SetupError('Update the existing card installation, or restore it before choosing standalone sync.')
    info = local / 'installation.json'
    if info.is_file() and card.read(info).get('architecture') != 'sync-only':
        raise SetupError('Restore the existing installation before changing its mode.')
    check_pending_setup(local)
    data_dir = local / 'data'
    if data_dir.is_symlink():
        raise SetupError('Unexpected local sync data link')
    if (data_dir / 'pending.json').exists():
        raise SetupError('Finish the interrupted sync before updating. / Сначала восстанови прерванную передачу.')
    settings_path = data_dir / 'settings.json'
    if settings_path.is_file() and Path(card.read(settings_path).get('ryujinx_dir', '')).absolute() != source_root.absolute():
        raise SetupError('Keep the same Ryujinx data folder when updating this installation.')
    shortcut_path = steam_config / 'shortcuts.vdf' if steam_config else None
    original = shortcut_path.read_bytes() if shortcut_path and shortcut_path.exists() else b''
    if original:
        steam_shortcuts.decode(original)
    with card.session_lock(local):
        # User settings/history outlive restoring the application installation.
        data_dir.mkdir(mode=0o700, exist_ok=True)
        if not settings_path.exists():
            card.write_changed(settings_path, {'schema': 2, 'host': '', 'port': 5000, 'games': {},
                               'ryujinx_dir': str(source_root), 'save_root': str(source_root / 'bis/user/save')})
            settings_path.chmod(0o600)
        if not (data_dir / 'state.json').exists():
            card.write_changed(data_dir / 'state.json', {})
            (data_dir / 'state.json').chmod(0o600)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
        tx = Transaction(local / 'backups' / stamp)
        try:
            idle_check()
            current = shortcut_path.read_bytes() if shortcut_path and shortcut_path.exists() else b''
            if current != original:
                raise SetupError('Steam shortcuts changed during setup. Close Steam and retry.')
            install_app(tx, package, home, local, steam_config, original, 'sync_launcher.py')
            tx.replace(info, json_bytes({'version': VERSION, 'architecture': 'sync-only',
                       'backup': str(tx.folder), 'source_root': str(source_root),
                       'steam_config': str(steam_config) if steam_config else None}))
            tx.commit()
            return {'local': str(local), 'backup': str(tx.folder)}
        except BaseException:
            tx.rollback()
            raise


def unit_contents(local):
    # systemd quoting is not shell quoting. Double percent signs are literals.
    path = str(local / 'native_card.py').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return ('[Unit]\nDescription=Switch Deck Sync card data attachment\n'
            '[Service]\nType=simple\nExecStart=/usr/bin/python3 "' + path + '" watch\n'
            'ExecStopPost=/usr/bin/python3 "' + path + '" detach\nRestart=on-failure\nRestartSec=1\n'
            'UMask=0077\n[Install]\nWantedBy=default.target\n').encode()


def install(package, home, mount, slot, executable, source_root, steam_config,
            mode='attach', rom_dirs=(), progress=lambda text: None, idle_check=require_idle,
            service_start=None, service_stop=None):
    idle_check()
    service_start = native_card.start_service if service_start is None else service_start
    service_stop = native_card.stop_service if service_stop is None else service_stop
    local = home / '.local/share/switch-deck-sync'
    local.mkdir(parents=True, exist_ok=True)
    previous_unit = (home / '.config/systemd/user' / native_card.UNIT).is_file()
    service_stop()
    tx = None
    try:
        with card.session_lock(local):
            result, tx, library_id = _install(package, home, mount, slot, executable, source_root,
                                              steam_config, mode, rom_dirs, progress, idle_check, local)
        service_start(local, library_id)
        tx.commit()
        return result
    except BaseException:
        service_stop()
        if tx is not None:
            with card.session_lock(local):
                tx.rollback()
        if previous_unit:
            try:
                native_card.systemctl('daemon-reload')
                native_card.systemctl('restart', native_card.UNIT)
            except (OSError, native_card.subprocess.SubprocessError):
                pass
        raise


def _install(package, home, mount, slot, executable, source_root, steam_config,
             mode, rom_dirs, progress, idle_check, local):
    check_pending_setup(local)
    if mode not in ('attach', 'prepare'):
        raise SetupError('Unknown setup mode')
    if not mount.is_mount():
        raise SetupError('Selected card is not mounted. / Карта не подключена.')
    roms, launcher = native_paths(home)
    if roms.resolve().is_relative_to(mount.resolve()):
        raise SetupError('For portable cards, select Internal Storage in EmuDeck first. / Для сменных карт выбери Internal Storage в EmuDeck.')
    root = home / '.config/Ryujinx'
    if source_root.absolute() != root.absolute() or root.is_symlink():
        raise SetupError('Use the standard EmuDeck Ryujinx data folder. Portable/managed emulator roots are not supported.')
    previous = None
    if (local / 'installation.json').is_file():
        previous = card.read(local / 'installation.json')
        if previous.get('architecture') not in ('native-emudeck', 'sync-only'):
            raise SetupError('Restore the older custom-launcher installation before installing this version.')
    source_config = card.read(root / 'Config.json')
    if not isinstance(source_config, dict):
        raise SetupError('Invalid Ryujinx configuration')
    original_shortcuts = (steam_config / 'shortcuts.vdf').read_bytes() if (steam_config / 'shortcuts.vdf').exists() else b''
    if original_shortcuts:
        steam_shortcuts.decode(original_shortcuts)
    local_data = local / 'data'
    if (local_data / 'pending.json').exists():
        raise SetupError('Finish the interrupted local sync before connecting a portable library.')
    sync_source = local_data if previous and previous.get('architecture') == 'sync-only' and (local_data / 'settings.json').is_file() else None
    manifest = prepare_card(mount, source_root, rom_dirs, progress, sync_source) if mode == 'prepare' else card.validated_manifest(mount)
    if not (card.contained(mount, manifest['data_dir']) / 'system/prod.keys').is_file():
        raise SetupError('The card has no dumped prod.keys. / На подготовленной карте отсутствуют ключи.')
    firmware = card.contained(mount, manifest['data_dir']) / 'bis/system/Contents/registered'
    if not firmware.is_dir() or not any(firmware.iterdir()):
        raise SetupError('The card has no installed firmware. / На карте отсутствует установленная прошивка.')
    catalog = card.catalog_games(mount, manifest)
    titles = [card.game_id(game) for game in catalog if card.game_id(game)]
    if len(titles) != len(set(titles)):
        raise SetupError('Multiple base games share a title ID. Keep one base file per game.')
    sync = card.contained(mount, manifest['sync_dir'])
    if (sync / 'pending.json').exists():
        raise SetupError('Finish the interrupted sync on the previous computer first. / Сначала восстанови прерванную синхронизацию.')
    migration = legacy_migration.plan(home, root, launcher, copy_tree, local, manifest['library_id'], progress)
    repairs = legacy_migration.shortcut_repairs(original_shortcuts, migration, launcher, roms, catalog)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    tx = Transaction(local / 'backups' / stamp)
    try:
        active = local / 'active'
        tx.replace(active, link=Path('/dev/null'))
        config = dict(source_config)
        config['game_dirs'] = [str(roms / 'switch')]
        tx.replace(root / 'Config.json', json_bytes(config))
        links = {str(root / name): str(active / name) for name in SHARED + ('games',)}
        links[str(roms / 'switch')] = str(active / 'roms')
        patches = roms.parent / 'storage/ryujinx/patchesAndDlc'
        links[str(patches)] = str(active / 'patches')
        for path, target in links.items():
            tx.redirect(Path(path), Path(target))
        host = {'schema': 3, 'architecture': 'native-emudeck', 'slot': slot,
                'ryujinx_dir': str(root), 'native_launcher': str(launcher),
                'roms_dir': str(roms / 'switch'), 'patches_dir': str(patches),
                'native_links': links, 'version': VERSION}
        tx.replace(local / 'host.json', json_bytes(host))
        idle_check()
        current = (steam_config / 'shortcuts.vdf').read_bytes() if (steam_config / 'shortcuts.vdf').exists() else b''
        if current != original_shortcuts:
            raise SetupError('Steam shortcuts changed during setup. Close Steam and retry.')
        install_app(tx, package, home, local, steam_config, original_shortcuts, 'native_card.py', repairs)
        unit = home / '.config/systemd/user' / native_card.UNIT
        tx.replace(unit, unit_contents(local))
        tx.replace(unit.parent / 'default.target.wants' / native_card.UNIT, link=unit)
        legacy_migration.apply(tx, migration, local)
        tx.replace(local / 'installation.json', json_bytes({'version': VERSION, 'architecture': 'native-emudeck',
                   'backup': str(tx.folder), 'steam_config': str(steam_config), 'source_root': str(source_root)}))
        return {'local': str(local), 'backup': str(tx.folder), 'games': len(catalog)}, tx, manifest['library_id']
    except BaseException:
        tx.rollback()
        raise
