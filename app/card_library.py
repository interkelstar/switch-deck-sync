#!/usr/bin/env python3
"""Validate and describe card-owned library data; no emulator launch path."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess

LOCAL=Path(__file__).resolve().parent
TITLE=re.compile(r'[\[(]([0-9a-fA-F]{16})[\])]')
class LibraryError(Exception):pass

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def write_changed(path,value):
    if path.is_file() and read(path)==value:return
    tmp=path.with_name(path.name+'.new')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    tmp.replace(path)

def relative_path(value):
    if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:raise LibraryError('Некорректный путь библиотеки.')
    p=Path(value)
    if p.is_absolute() or '..' in p.parts:raise LibraryError('Путь библиотеки выходит за пределы карты.')
    return p

def contained(base,value):
    target=base/relative_path(value)
    if not target.resolve().is_relative_to(base.resolve()):raise LibraryError('Данные библиотеки ссылаются за пределы карты.')
    return target

def slot_devices(devices,slot):
    # Reader selection does not depend on a card UUID, capacity or label.
    if slot.get('kind','mmc')=='mmc':
        return [d for d in devices if d.get('type','disk')=='disk' and d.get('tran')=='mmc'
                and re.fullmatch(r'mmcblk\d+',d.get('name',Path(d['path']).name))]
    if slot.get('kind')=='reader-path':
        path=Path(slot.get('path',''))
        if not str(path).startswith('/dev/disk/by-path/'):raise LibraryError('Нужен путь считывателя /dev/disk/by-path/.')
        return [d for d in devices if d['path']==str(path.resolve())]
    raise LibraryError('Не настроен встроенный слот карт памяти.')

def partitions(device):
    result=[]
    for child in device.get('children',[]):
        if child.get('type','part')=='part':result.append(child)
        result.extend(partitions(child))
    return result

def block_devices():
    return json.loads(subprocess.check_output(['lsblk','-J','-o','NAME,PATH,TYPE,TRAN,FSTYPE,UUID,MOUNTPOINTS,RM,SIZE,MODEL'],text=True))['blockdevices']

def marker_path(mount):
    visible=mount/'Emulation/switch-library.json'
    return visible if visible.is_file() else mount/'.switch-library.json'

def validated_manifest(mount):
    marker=marker_path(mount)
    if not marker.is_file() or marker.is_symlink():raise LibraryError('На карте в слоте нет описания библиотеки Switch.')
    value=read(marker)
    if value.get('schema') not in [1,2]:raise LibraryError('Неизвестная версия библиотеки Switch.')
    if not re.fullmatch(r'[0-9a-fA-F]{32}',value.get('library_id','')):raise LibraryError('Отсутствует идентификатор содержимого библиотеки.')
    for key in ['data_dir','rom_dir','sync_dir']:
        if not contained(mount,value.get(key)).is_dir():raise LibraryError('Не найдена папка библиотеки: '+key)
    for name in ['bis/user/save','system','mods','sdcard']:
        if not contained(mount,value['data_dir']+'/'+name).is_dir():raise LibraryError('Не найдены данные профиля: '+name)
    if not contained(mount,value['sync_dir']+'/settings.json').is_file():raise LibraryError('Не найдены настройки синхронизации этой библиотеки.')
    if not isinstance(value.get('game_metadata',{}),dict) or not isinstance(value.get('games'),list):raise LibraryError('Некорректный список игр.')
    for relative in value.get('game_metadata',{}):relative_path(relative)
    for game in value['games']:relative_path(game['rom'])
    # A legacy card_uuid is intentionally ignored. Cloning to another card works.
    return value

def locate(host,allow_mount=True,devices=None):
    readers=slot_devices(block_devices() if devices is None else devices,host.get('slot',{'kind':'mmc'}))
    if not readers:raise LibraryError('Вставь карту с библиотекой Switch во встроенный слот.')
    if len(readers)!=1:raise LibraryError('Нужно выбрать один встроенный считыватель карт.')
    candidates=[];errors=[]
    for part in partitions(readers[0]):
        if part.get('fstype') in [None,'swap','crypto_LUKS']:continue
        mounts=[Path(p) for p in part.get('mountpoints',[]) if p]
        if not mounts and allow_mount:
            r=subprocess.run(['udisksctl','mount','--no-user-interaction','-b',part['path']],capture_output=True,text=True)
            if r.returncode:errors.append('Не удалось подключить карту из слота.');continue
            refreshed=slot_devices(block_devices(),host.get('slot',{'kind':'mmc'}))
            part=next((p for d in refreshed for p in partitions(d) if p['path']==part['path']),part)
            mounts=[Path(p) for p in part.get('mountpoints',[]) if p]
        for mount in mounts:
            if marker_path(mount).is_file():candidates.append((mount,validated_manifest(mount),part))
    if len(candidates)>1:raise LibraryError('В слоте несколько библиотек Switch; нужен один раздел.')
    if not candidates:raise LibraryError(errors[0] if errors else 'На карте во встроенном слоте нет библиотеки Switch.')
    return candidates[0]

def map_paths(value,alias):
    if isinstance(value,str) and value.startswith('@CARD@/'):return str(alias/relative_path(value[7:]))
    if isinstance(value,list):return [map_paths(v,alias) for v in value]
    if isinstance(value,dict):return {k:map_paths(v,alias) for k,v in value.items()}
    return value

def portable_paths(value,alias,mount,extra_paths=()):
    if isinstance(value,str):
        for base,prefix in [(str(alias),''),(str(mount),''),*extra_paths]:
            if value.startswith(base+'/'):return '@CARD@/'+prefix+('/' if prefix else '')+value[len(base)+1:]
        return value
    if isinstance(value,list):return [portable_paths(v,alias,mount,extra_paths) for v in value]
    if isinstance(value,dict):return {k:portable_paths(v,alias,mount,extra_paths) for k,v in value.items()}
    return value

def game_id(game):
    value=game.get('title_id')
    if value and re.fullmatch(r'[0-9a-fA-F]{16}',value):return value.upper()
    match=TITLE.search(game.get('rom',''));return match.group(1).upper() if match else None

def catalog_games(mount,manifest):
    """Actual ROMs define the cartridge's catalog, not a host registry."""
    folder=contained(mount,manifest['rom_dir'])
    known={g['rom']:g for g in manifest['games']};by_id={game_id(g):g for g in manifest['games'] if game_id(g)}
    patch_paths=set();prefix='@CARD@/'+manifest['rom_dir'].rstrip('/')+'/'
    def referenced(value):
        if isinstance(value,str) and value.startswith(prefix):patch_paths.add(value[len(prefix):])
        elif isinstance(value,list):
            for item in value:referenced(item)
        elif isinstance(value,dict):
            for item in value.values():referenced(item)
    referenced(manifest.get('game_metadata',{}))
    catalog=[]
    for p in sorted(folder.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in ['.xci','.nsp']:continue
        relative=p.relative_to(folder).as_posix();contained(folder,relative)
        title=game_id({'rom':relative})
        if relative in patch_paths and relative not in known:continue
        if title and title not in by_id and int(title,16)&0xfff:continue
        if any(tag in p.name.lower() for tag in ['[update]','[dlc']):continue
        game=dict(known.get(relative) or by_id.get(title) or {})
        game['rom']=relative
        if title:game['title_id']=title
        game.setdefault('name',p.stem);catalog.append(game)
    return catalog

def export_metadata(mount,manifest,alias,root,extra_paths=()):
    # Do not recreate folders at a stale path after unplugging the cartridge.
    if not mount.is_mount():return
    current=read(marker_path(mount))
    if current.get('library_id')!=manifest['library_id']:return
    templates={}
    for p in (root/'games').glob('*/*.json'):
        if p.name in ['updates.json','dlc.json']:templates[p.relative_to(root/'games').as_posix()]=portable_paths(read(p),alias,mount,extra_paths)
    current.update(game_metadata=templates,games=manifest['games'],schema=2,kind='switch-library');current.pop('card_uuid',None)
    write_changed(marker_path(mount),current)

@contextlib.contextmanager
def session_lock(local=LOCAL):
    with (local/'session.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise LibraryError('Сначала полностью закрой игру или синхронизацию.') from None
        yield
