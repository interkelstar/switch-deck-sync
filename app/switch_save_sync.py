#!/usr/bin/env python3
"""Manual, whole-save Switch/Ryujinx synchronisation. Python standard library."""
from i18n import tr
import i18n
import argparse
import datetime
import fcntl
import ftplib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import uuid

HOME = Path(os.environ.get('SDS_DATA_DIR', Path(__file__).resolve().parent))

class SyncError(Exception):
    pass

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.new')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest_tree(path):
    if not path.is_dir() or path.is_symlink():
        raise SyncError(tr('Не найдена папка сохранения: ') + str(path))
    result = {}
    total = 0
    for p in sorted(path.rglob('*')):
        if p.is_symlink():
            raise SyncError(tr('В сохранении обнаружена неожиданная ссылка: ') + str(p))
        if p.is_file():
            if any(any(c in part for c in ['\\', '\r', '\n', '\x00'])
                   for part in p.relative_to(path).parts):
                raise SyncError(tr('Некорректное имя файла в сохранении'))
            h = hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(block)
            size = p.stat().st_size
            total += size
            if total > 256 * 1024 * 1024 or len(result) >= 4096:
                raise SyncError(tr('Неожиданно большой размер сохранения'))
            result[p.relative_to(path).as_posix()] = {'size': size, 'sha256': h.hexdigest()}
    if not result:
        raise SyncError(tr('Сохранение пустое; автоматическая замена запрещена'))
    return result

def decide(baseline, deck, switch):
    if deck == switch:
        return 'same'
    if baseline is None:
        return 'conflict'
    if deck == baseline:
        return 'switch'
    if switch == baseline:
        return 'deck'
    return 'conflict'

def ensure_idle():
    # /proc/comm can change for .NET, so inspect command lines, not process names.
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / 'cmdline').read_bytes().split(b'\0')[0].decode(errors='replace')
            if Path(cmd).name.lower() in ('ryujinx', 'ryujinx.headless.sdl2', 'ryujinx.avalonia'):
                raise SyncError(tr('Сначала сохранись и полностью закрой Ryujinx.'))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass

class FTPStore:
    def __init__(self, settings):
        self.settings = settings
        self.ftp = None

    def connect(self):
        self.close()
        self.ftp = ftplib.FTP()
        self.ftp.connect(self.settings['host'], self.settings['port'], timeout=20)
        self.ftp.login()
        self.ftp.encoding = 'utf-8'

    def close(self):
        if self.ftp:
            self.ftp.close()
            self.ftp = None

    def listing(self, remote):
        self.ftp.cwd(remote)
        result = []
        for name in self.ftp.nlst():
            if name in ('.', '..'):
                continue
            if PurePosixPath(name).name != name or any(x in name for x in ['\\', '\r', '\n', '\x00']):
                raise SyncError(tr('Некорректное имя в FTP-папке'))
            if any(name == old[0] for old in result):
                raise SyncError(tr('Повтор имени в FTP-папке'))
            full = remote + '/' + name
            try:
                self.ftp.cwd(full)
                directory = True
            except ftplib.error_perm:
                directory = False
            self.ftp.cwd(remote)
            result.append((name, directory))
        return sorted(result)

    def inventory(self, remote, prefix=''):
        files = {}
        for name, directory in self.listing(remote):
            rel = prefix + name
            if directory:
                if rel.count('/') > 16:
                    raise SyncError(tr('Слишком глубокая FTP-папка'))
                files.update(self.inventory(remote + '/' + name, rel + '/'))
            else:
                self.ftp.voidcmd('TYPE I')
                size = self.ftp.size(remote + '/' + name)
                if size is None or size < 0:
                    raise SyncError(tr('FTP не сообщил размер файла'))
                files[rel] = size
            if len(files) > 4096 or sum(files.values()) > 256 * 1024 * 1024:
                raise SyncError(tr('Неожиданно большое сохранение на Switch'))
        return files

    def snapshot(self, remote, dest):
        inventory = self.inventory(remote)
        dest.mkdir(parents=True, exist_ok=False)
        for rel, size in inventory.items():
            p = dest / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('xb') as out:
                reply = self.ftp.retrbinary('RETR ' + remote + '/' + rel, out.write)
            if not reply.startswith('226') or p.stat().st_size != size:
                raise SyncError(tr('Не полностью прочитан файл Switch: ') + rel)
        if self.inventory(remote) != inventory:
            raise SyncError(tr('Сохранение Switch изменилось во время чтения'))
        return digest_tree(dest)

    def replace(self, remote, source):
        desired = digest_tree(source)
        existing = self.inventory(remote)
        # Delete obsolete files first to free the fixed-size Switch save quota.
        for rel in sorted(set(existing) - set(desired)):
            self.ftp.delete(remote + '/' + rel)
        for rel in desired:
            parent = PurePosixPath(rel).parent
            parents = list(parent.parents)[::-1] + [parent]
            for p in parents:
                if str(p) == '.':
                    continue
                directory = remote + '/' + p.as_posix()
                try:
                    self.ftp.cwd(directory)
                except ftplib.error_perm:
                    self.ftp.mkd(directory)
            with (source / rel).open('rb') as inp:
                reply = self.ftp.storbinary('STOR ' + remote + '/' + rel, inp)
            if not reply.startswith('226'):
                raise SyncError(tr('Switch не подтвердил запись: ') + rel)
        # Empty obsolete directories contain no game data and are harmless.

def install_local(save, source, game, run):
    ensure_idle()
    title = int(game['title_id'], 16)
    for name in ['ExtraData0', 'ExtraData1']:
        if int.from_bytes((save / name).read_bytes()[:8], 'little') != title:
            raise SyncError(tr('Профиль Ryujinx не соответствует выбранной игре'))
    expected = digest_tree(source)
    stage = save.with_name('.' + save.name + '-sync-' + uuid.uuid4().hex)
    old = save.with_name('.' + save.name + '-before-' + uuid.uuid4().hex)
    shutil.copytree(save, stage)
    for generation in ['0', '1']:
        shutil.rmtree(stage / generation)
        shutil.copytree(source, stage / generation)
        if digest_tree(stage / generation) != expected:
            raise SyncError(tr('Не прошла проверка подготовленной копии Ryujinx'))
    journal = {'kind': 'local', 'save': str(save), 'stage': str(stage), 'old': str(old),
               'source': str(source), 'run': str(run)}
    atomic_json(HOME / 'pending.json', journal)
    ensure_idle()
    save.rename(old)
    try:
        stage.rename(save)
        os.sync()
        for generation in ['0', '1']:
            if digest_tree(save / generation) != expected:
                raise SyncError(tr('Не прошла проверка записанного сейва Ryujinx'))
    except BaseException:
        if save.exists():
            save.rename(run / 'failed-local-save')
        old.rename(save)
        (HOME / 'pending.json').unlink()
        raise
    # Preserve the exact pre-replacement save folder, including emulator metadata.
    shutil.copytree(old, run / 'deck-original-container')
    shutil.rmtree(old)
    return journal

class Sync:
    def __init__(self, settings, store, choose, progress=print):
        self.settings, self.store, self.choose, self.progress = settings, store, choose, progress
        self.state_file = HOME / 'state.json'
        self.pending = HOME / 'pending.json'

    def recover(self):
        if not self.pending.exists():
            return
        ensure_idle()
        p = read_json(self.pending)
        if p['kind'] == 'agreed':
            state = read_json(self.state_file)
            state[p['key']] = p['manifest']
            atomic_json(self.state_file, state)
        elif p['kind'] == 'remote':
            self.progress(tr('Восстанавливаю Switch после прерванной передачи…'))
            source = Path(p['backup'])
            if digest_tree(source) != p['backup_manifest']:
                raise SyncError(tr('Повреждена резервная копия для восстановления Switch'))
            self.store.replace(p['remote'], source)
            check = Path(p['run']) / ('recovery-check-' + uuid.uuid4().hex)
            if self.store.snapshot(p['remote'], check) != p['backup_manifest']:
                raise SyncError(tr('Не удалось проверить восстановление Switch'))
        else:
            save, old, stage = map(Path, [p['save'], p['old'], p['stage']])
            if old.exists():
                if save.exists():
                    save.rename(Path(p['run']) / ('interrupted-local-' + uuid.uuid4().hex))
                old.rename(save)
            if stage.exists():
                shutil.rmtree(stage)
            if not save.is_dir():
                raise SyncError(tr('Не удалось восстановить папку сохранений Ryujinx'))
        self.pending.unlink()

    def run(self, dry_run=False):
        ensure_idle()
        if not self.settings.get('games'):
            raise SyncError(tr('Выбери игры в настройках перед синхронизацией.'))
        self.store.connect()
        if self.pending.exists() and dry_run:
            raise SyncError(tr('Есть прерванная передача. Запусти обычную синхронизацию для восстановления.'))
        self.recover()
        state = read_json(self.state_file)
        results = []
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        run = HOME / 'backups' / (stamp + '-' + uuid.uuid4().hex[:6])
        run.mkdir(parents=True)
        for key, game in self.settings['games'].items():
            ensure_idle()
            self.progress(tr('Проверяю ') + game['name'] + '…')
            work = run / key
            work.mkdir()
            save = Path(self.settings['save_root']) / game['save_id']
            if save.is_symlink():
                raise SyncError(tr('Неожиданная ссылка вместо папки сохранения Ryujinx'))
            for name in ['ExtraData0', 'ExtraData1']:
                extra = save / name
                if extra.is_symlink() or int.from_bytes(extra.read_bytes()[:8], 'little') != int(game['title_id'], 16):
                    raise SyncError(tr('Папка сохранения Ryujinx принадлежит другой игре: ') + game['name'])
                if game.get('user_id') and extra.read_bytes()[8:24].hex() != game['user_id']:
                    raise SyncError(tr('Папка сохранения принадлежит другому профилю: ') + game['name'])
            local_source = save / '0'
            before = digest_tree(local_source)
            shutil.copytree(local_source, work / 'deck')
            if digest_tree(work / 'deck') != before or digest_tree(local_source) != before:
                raise SyncError(tr('Сохранение Ryujinx изменилось при копировании'))
            remote = self.settings['account_path'] + '/' + game.get('remote_name', '[' + game['title_id'] + ']')
            switch = self.store.snapshot(remote, work / 'switch')
            direction = decide(state.get(key), before, switch)
            atomic_json(work / 'comparison.json', {'deck': before, 'switch': switch, 'decision': direction})
            if direction == 'conflict':
                if dry_run:
                    results.append(game['name'] + tr(': конфликт; сохранены обе копии'))
                    continue
                direction = self.choose(game['name'])
            if direction == 'skip':
                results.append(game['name'] + tr(': пропущено, обе копии сохранены'))
                continue
            if dry_run:
                results.append(game['name'] + ': ' + {'same': tr('совпадают'), 'deck': 'Ryujinx → Switch', 'switch': 'Switch → Ryujinx'}[direction])
                continue
            if direction != 'same':
                ensure_idle()
                if digest_tree(local_source) != before:
                    raise SyncError(tr('Сохранение Ryujinx изменилось; запусти синхронизацию заново'))
                confirm = self.store.snapshot(remote, work / 'switch-before-write')
                if confirm != switch:
                    raise SyncError(tr('Сохранение Switch изменилось; запусти синхронизацию заново'))
                if direction == 'switch':
                    self.progress(game['name'] + ': Switch → Ryujinx…')
                    install_local(save, work / 'switch', game, work)
                    agreed = switch
                elif direction == 'deck':
                    self.progress(game['name'] + ': Ryujinx → Switch…')
                    # Journal is durable before the first remote write. Recovery
                    # always uses the complete pre-transfer snapshot.
                    atomic_json(self.pending, {'kind': 'remote', 'remote': remote,
                        'backup': str(work / 'switch'), 'backup_manifest': switch, 'run': str(work)})
                    try:
                        self.store.replace(remote, work / 'deck')
                        check = self.store.snapshot(remote, work / 'switch-after-write')
                        if check != before:
                            raise SyncError(tr('Не совпала проверочная копия Switch после записи'))
                    except BaseException as original:
                        try:
                            self.store.connect()
                            self.recover()
                        except BaseException as recovery:
                            raise SyncError(tr('Передача прервана. Не запускай эту игру на Switch. '
                                'Оставь ftpsrv Save Sync открытым и повтори синхронизацию: '
                                'она восстановит резервную копию. ') + str(recovery)) from original
                        raise SyncError(tr('Передача не удалась; прежний сейв Switch восстановлен. ') + str(original)) from original
                    agreed = before
                else:
                    raise SyncError(tr('Неизвестное направление синхронизации'))
            else:
                agreed = switch
            if direction != 'same':
                # Advance the baseline and retire the transfer journal as a
                # recoverable transaction, including a power loss in between.
                atomic_json(self.pending, {'kind': 'agreed', 'key': key, 'manifest': agreed})
            state[key] = agreed
            atomic_json(self.state_file, state)
            if self.pending.exists():
                self.pending.unlink()
            results.append(game['name'] + ': ' + {'same': tr('совпадают'), 'deck': 'Ryujinx → Switch ✓', 'switch': 'Switch → Ryujinx ✓'}[direction])
        atomic_json(run / 'result.json', {'results': results, 'dry_run': dry_run})
        if not dry_run:
            atomic_json(HOME / 'last-result.json', {'results': results,
                'completed': datetime.datetime.now(datetime.timezone.utc).isoformat()})
        return results

def main():
    parser = argparse.ArgumentParser(description='Switch Deck Sync')
    parser.add_argument('--check', action='store_true', help='Download and compare only')
    parser.add_argument('--cli', action='store_true', help='Console mode; conflicting saves are skipped')
    parser.add_argument('--language', choices=('en','ru'), help='Interface language for this run')
    args = parser.parse_args()
    if args.language:
        i18n.set_language(args.language)
    lock = (HOME / 'sync.lock').open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(tr('Switch Deck Sync уже запущен.'), file=sys.stderr)
        return 2
    if not args.cli:
        from sync_ui import run_gui
        return run_gui(args.check)
    store = None
    try:
        from sync_config import load_or_create
        settings = load_or_create(HOME)
        store = FTPStore(settings)
        results = Sync(settings, store, lambda name: 'skip',
                       lambda text: print(text, flush=True)).run(args.check)
        print('\n'.join(results), flush=True)
        return 0
    except Exception as ex:
        message = str(ex)
        if (HOME / 'pending.json').exists():
            message += tr(' Есть прерванная передача. Не запускай игру на Switch; повтори синхронизацию для восстановления.')
        print(tr('ОШИБКА: ') + message, file=sys.stderr, flush=True)
        return 1
    finally:
        if store:store.close()

if __name__ == '__main__':
    raise SystemExit(main())
