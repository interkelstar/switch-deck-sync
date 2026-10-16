"""Installation engine. No downloads, sudo, formatting or deletion of source data."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

import card_library as card
import steam_shortcuts

VERSION = '0.2.0-preview'
SHARED = ('bis', 'system', 'mods', 'sdcard')
RUNTIME = ('card_library.py', 'switch_save_sync.py', 'sync_config.py', 'sync_ui.py',
           'setup_library.py', 'setup_wizard.py', 'steam_shortcuts.py')


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

    def rollback(self):
        restore(self.folder)
        self.status = 'rolled-back'


def restore(folder):
    """Only installer-owned paths are journalled; no card data is ever removed."""
    journal = card.read(folder / 'transaction.json')
    for item in reversed(journal['items']):
        path = Path(item['path'])
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


def prepare_card(mount, source_root, rom_dirs, progress=lambda text: None):
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


def install(package, home, mount, slot, executable, source_root, steam_config,
            mode='attach', rom_dirs=(), progress=lambda text: None, idle_check=require_idle):
    idle_check()
    local = home / '.local/share/switch-deck-sync'
    local.mkdir(parents=True, exist_ok=True)
    # Protect installation against a concurrent managed emulator/session and another installer.
    with card.session_lock(local):
        return _install(package, home, mount, slot, executable, source_root, steam_config,
                        mode, rom_dirs, progress, idle_check, local)


def _install(package, home, mount, slot, executable, source_root, steam_config,
             mode, rom_dirs, progress, idle_check, local):
    for pending in (local / 'backups').glob('*/transaction.json'):
        if card.read(pending)['status'] == 'in-progress':
            raise SetupError('Interrupted setup: restore it first. / Восстанови прерванную установку: ' + str(pending.parent))
    if mode not in ('attach', 'prepare'):
        raise SetupError('Unknown setup mode')
    if not mount.is_mount():
        raise SetupError('Selected card is not mounted. / Карта не подключена.')
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SetupError('Select the native Ryujinx executable or AppImage.')
    if executable.suffix.lower() in ('.sh', '.desktop') or executable.is_relative_to(local):
        raise SetupError('Select Ryujinx itself, not a launcher. / Нужен сам эмулятор, не ярлык.')
    source_config = card.read(source_root / 'Config.json')
    # Validate Steam before copying large files or publishing a new card.
    original_shortcuts = (steam_config / 'shortcuts.vdf').read_bytes() if (steam_config / 'shortcuts.vdf').exists() else b''
    if original_shortcuts:
        steam_shortcuts.decode(original_shortcuts)
    manifest = prepare_card(mount, source_root, rom_dirs, progress) if mode == 'prepare' else card.validated_manifest(mount)
    catalog = card.catalog_games(mount, manifest)
    titles = [card.game_id(game) for game in catalog if card.game_id(game)]
    if len(titles) != len(set(titles)):
        raise SetupError('Multiple base games share a title ID. Keep one base file per game. / Для каждой игры оставь один базовый файл.')
    sync = card.contained(mount, manifest['sync_dir'])
    if (sync / 'pending.json').exists():
        raise SetupError('Finish the interrupted sync on the previous computer first. / Сначала восстанови прерванную синхронизацию.')
    root = local / 'ryujinx'
    root.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    tx = Transaction(local / 'backups' / stamp)
    try:
        for name in RUNTIME:
            tx.replace(local / name, (package / 'app' / name).read_bytes())
        for p in sorted((package / 'art').iterdir()):
            if p.is_file():
                tx.replace(local / 'art' / p.name, p.read_bytes())
        for name in ('LICENSE', 'VERSION'):
            tx.replace(local / name, (package / name).read_bytes())
        # A separate managed root makes the original EmuDeck profile a recovery source.
        config = card.read(root / 'Config.json') if (root / 'Config.json').exists() else source_config
        alias = local / 'card'
        config['game_dirs'] = [str(alias / manifest['rom_dir'])]
        tx.replace(root / 'Config.json', json_bytes(config))
        tx.replace(alias, link=mount)
        for name in SHARED:
            tx.replace(root / name, link=alias / manifest['data_dir'] / name)
        games = local / 'libraries' / manifest['library_id'].lower() / 'games'
        games.mkdir(parents=True, exist_ok=True)
        tx.replace(root / 'games', link=games)
        for relative, template in manifest.get('game_metadata', {}).items():
            target = card.contained(games, relative)
            tx.replace(target, json_bytes(card.map_paths(template, alias)))
        # Controller profiles and mapping databases are host-specific.
        if not (root / 'profiles').exists() and (source_root / 'profiles').is_dir():
            for p in (source_root / 'profiles').rglob('*'):
                if p.is_file():
                    tx.replace(root / 'profiles' / p.relative_to(source_root / 'profiles'), p.read_bytes())
        if not (root / 'gamecontrollerdb.txt').exists() and (source_root / 'gamecontrollerdb.txt').is_file():
            tx.replace(root / 'gamecontrollerdb.txt', (source_root / 'gamecontrollerdb.txt').read_bytes())
        host = {'schema': 2, 'slot': slot, 'ryujinx_dir': str(root),
                'emulator_executable': str(executable), 'root_data_argument': True,
                'sync_runtime': str(local), 'version': VERSION}
        tx.replace(local / 'host.json', json_bytes(host))
        for name, command in [('ryujinx.sh', 'emulator'), ('sync.sh', 'sync')]:
            # Runtime-relative shell entry; paths containing spaces and quotes work.
            text = '#!/bin/sh\nset -eu\nBASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec /usr/bin/python3 "$BASE/card_library.py" ' + command + ' "$@"\n'
            tx.replace(local / name, text.encode(), mode=0o755)
        apps = [('Switch Deck Sync', 'sync.sh', ''), ('Switch Library (Ryujinx)', 'ryujinx.sh', '')]
        entries = [{'appname': name, 'exe': '"' + str(local / script) + '"',
                    'StartDir': '"' + str(local) + '"', 'LaunchOptions': options,
                    'icon': str(local / 'art/icon.ico') if script == 'sync.sh' else ''}
                   for name, script, options in apps]
        for game in catalog:
            title = card.game_id(game)
            if title:
                entries.append({'appname': game.get('name', title), 'title_id': title,
                                'exe': '"' + str(local / 'ryujinx.sh') + '"', 'StartDir': '"' + str(local) + '"',
                                'LaunchOptions': '--fullscreen --game ' + title})
        idle_check()
        # Detect a Steam write or profile change since the initial read.
        current = (steam_config / 'shortcuts.vdf').read_bytes() if (steam_config / 'shortcuts.vdf').exists() else b''
        if current != original_shortcuts:
            raise SetupError('Steam shortcuts changed during setup. Close Steam and retry.')
        data, ids = steam_shortcuts.upsert(original_shortcuts, entries)
        tx.replace(steam_config / 'shortcuts.vdf', data)
        for source, suffix in [('cover', 'p'), ('hero', '_hero'), ('logo', '_logo'), ('grid', '')]:
            tx.replace(steam_config / 'grid' / (str(ids['Switch Deck Sync']) + suffix + '.png'),
                       (package / 'art' / (source + '.png')).read_bytes())
        for name, script, _ in apps:
            filename = 'switch-deck-sync.desktop' if script == 'sync.sh' else 'switch-library.desktop'
            text = '[Desktop Entry]\nType=Application\nName=' + name + '\nExec=' + quoted_exec(local / script) + '\nIcon=' + str(local / 'art/icon.png') + '\nTerminal=false\nCategories=Game;Utility;\n'
            tx.replace(home / '.local/share/applications' / filename, text.encode())
        tx.replace(local / 'installation.json', json_bytes({'version': VERSION, 'backup': str(tx.folder),
                   'steam_config': str(steam_config), 'source_root': str(source_root)}))
        tx.commit()
        return {'local': str(local), 'backup': str(tx.folder), 'games': len(entries) - 2}
    except BaseException:
        tx.rollback()
        raise
