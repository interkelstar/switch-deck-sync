#!/usr/bin/env python3
"""Launch the Switch library inserted in this machine's configured card slot."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

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

def portable_paths(value,alias,mount):
    if isinstance(value,str):
        for base in [str(alias),str(mount)]:
            if value.startswith(base+'/'):return '@CARD@/'+value[len(base)+1:]
        return value
    if isinstance(value,list):return [portable_paths(v,alias,mount) for v in value]
    if isinstance(value,dict):return {k:portable_paths(v,alias,mount) for k,v in value.items()}
    return value

def managed_link(path,target,local):
    if path.is_symlink():
        previous=Path(os.readlink(path));previous=previous if previous.is_absolute() else path.parent/previous
        if not previous.is_relative_to(local):raise LibraryError('Неожиданная ссылка Ryujinx: '+str(path))
        if os.readlink(path)==str(target):return
    elif path.exists():raise LibraryError('Папка Ryujinx ещё не подготовлена: '+str(path))
    stage=path.with_name(path.name+'.switch-library-new')
    if stage.is_symlink():stage.unlink()
    elif stage.exists():raise LibraryError('Временный путь занят: '+str(stage))
    stage.symlink_to(target,target_is_directory=True);stage.replace(path)

def prepare(host,local=LOCAL,allow_mount=True,devices=None):
    mount,manifest,part=locate(host,allow_mount,devices);alias=local/'card'
    manifest=dict(manifest,games=catalog_games(mount,manifest))
    if alias.is_symlink():
        if alias.resolve()!=mount.resolve():
            stage=local/'card.new';stage.unlink(missing_ok=True);stage.symlink_to(mount);stage.replace(alias)
    elif alias.exists():raise LibraryError('Путь подключения карты занят обычной папкой.')
    else:alias.symlink_to(mount)
    root=Path(host['ryujinx_dir']);shared=alias/manifest['data_dir']
    for name in ['bis','system','mods','sdcard']:managed_link(root/name,shared/name,local)
    namespace=local/'libraries'/manifest['library_id'].lower();games=namespace/'games';games.mkdir(parents=True,exist_ok=True)
    managed_link(root/'games',games,local)
    config=read(root/'Config.json');config['game_dirs']=[str(alias/manifest['rom_dir'])];write_changed(root/'Config.json',config)
    templates=manifest.get('game_metadata',{})
    for p in games.glob('*/*.json'):
        if p.name in ['updates.json','dlc.json'] and p.relative_to(games).as_posix() not in templates:p.unlink()
    for relative,template in templates.items():
        target=games/relative_path(relative);target.parent.mkdir(parents=True,exist_ok=True);write_changed(target,map_paths(template,alias))
    app=alias/manifest['sync_dir'];settings=read(app/'settings.json')
    settings['ryujinx_dir']=str(root);settings['save_root']=str(root/'bis/user/save');write_changed(app/'settings.json',settings)
    write_changed(local/'current.json',{'library_id':manifest['library_id'],'mount':str(mount),'slot_device':part['path']})
    return mount,manifest,alias,app

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

def arguments(values,manifest,alias):
    result=[];values=iter(values)
    for value in values:
        if value=='--game':
            title=next(values,'').upper()
            if not re.fullmatch(r'[0-9A-F]{16}',title):raise LibraryError('Не указан идентификатор игры.')
            matches=[g for g in manifest['games'] if game_id(g)==title]
            if len(matches)!=1:raise LibraryError('Этой игры нет на вставленной карте. Открой библиотеку Switch или вставь другую карту.')
            result.append(str(contained(alias,manifest['rom_dir']+'/'+matches[0]['rom'])))
        elif value.startswith('Emulation/'):result.append(str(alias/relative_path(value)))
        elif value.lower().endswith(('.xci','.nsp')) and Path(value).is_absolute():
            if not Path(value).resolve().is_relative_to(alias.resolve()):raise LibraryError('Ярлык указывает на другую карту.')
            result.append(value)
        else:result.append(value)
    for value in result:
        if value.lower().endswith(('.xci','.nsp')) and not Path(value).is_file():raise LibraryError('Не найден файл игры на вставленной карте.')
    return result

def export_metadata(mount,manifest,alias,root):
    # Do not recreate folders at a stale path after unplugging the cartridge.
    if not mount.is_mount():return
    current=read(marker_path(mount))
    if current.get('library_id')!=manifest['library_id']:return
    templates={}
    for p in (root/'games').glob('*/*.json'):
        if p.name in ['updates.json','dlc.json']:templates[p.relative_to(root/'games').as_posix()]=portable_paths(read(p),alias,mount)
    current.update(game_metadata=templates,games=manifest['games'],schema=2,kind='switch-library');current.pop('card_uuid',None)
    write_changed(marker_path(mount),current)

def prepare_frontend(host,alias,manifest):
    path=Path(host['frontend_settings']);text=path.read_text();fragment=False;changed=False
    try:root=ET.fromstring(text)
    except ET.ParseError:
        # ES-DE's native settings format is an XML fragment with sibling options.
        text=re.sub(r'^\s*<\?xml[^>]*\?>','',text)
        root=ET.fromstring('<settings>'+text+'</settings>');fragment=True
    values={'ROMDirectory':str(alias/manifest['rom_dir']).rsplit('/switch',1)[0],
            'MediaDirectory':host['frontend_media']}
    for node in root.iter('string'):
        name=node.get('name')
        if name in values and node.get('value')!=values[name]:node.set('value',values[name]);changed=True
    if changed:
        stage=path.with_name(path.name+'.new')
        if fragment:stage.write_text('<?xml version="1.0"?>\n'+''.join(ET.tostring(n,encoding='unicode') for n in root))
        else:ET.ElementTree(root).write(stage,encoding='utf-8',xml_declaration=True)
        stage.replace(path)

@contextlib.contextmanager
def session_lock(local=LOCAL):
    with (local/'session.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise LibraryError('Сначала полностью закрой игру или синхронизацию.') from None
        yield

def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv);mode=args.pop(0) if args else 'check'
    if mode not in ['check','emulator','sync','frontend']:raise LibraryError('Неизвестный режим запуска.')
    host=read(LOCAL/'host.json')
    with contextlib.ExitStack() as stack:
        stack.enter_context(session_lock())
        from switch_save_sync import ensure_idle
        ensure_idle()
        mount,manifest,alias,app=prepare(host)
        if mode=='check':
            print(json.dumps({'slot':host['slot'],'slot_mount':str(mount),'library_id':manifest['library_id'],
                'save_root':str((Path(host['ryujinx_dir'])/'bis/user/save').resolve()),'sync':str(app.resolve()),
                'games':len(manifest['games'])},ensure_ascii=False,indent=2));return 0
        env=dict(os.environ,LANG='C.UTF-8',LC_ALL='C.UTF-8',DOTNET_EnableAlternateStackCheck='1')
        if mode=='emulator':
            command=[host['emulator_executable']]
            if host.get('root_data_argument'):command+=['--root-data-dir',host['ryujinx_dir']]
            command+=arguments(args,manifest,alias)
            if shutil.which('gamemoderun'):command.insert(0,'gamemoderun')
        elif mode=='sync':
            # Executable code is installed locally; the card carries only user data.
            runtime=Path(host.get('sync_runtime',LOCAL))
            command=['/usr/bin/python3',str(runtime/'switch_save_sync.py')]+args
            env['SDS_DATA_DIR']=str(app)
            if shutil.which('systemd-inhibit'):
                probe=['systemd-inhibit','--no-ask-password','--what=sleep:idle','--mode=block']
                if subprocess.run(probe+['/usr/bin/true'],capture_output=True).returncode==0:
                    command=probe+['--who=Switch Deck Sync','--why=Save synchronisation']+command
        else:
            prepare_frontend(host,alias,manifest)
            command=[host['frontend_executable'],'--ignore-gamelist','--no-update-check']+args
            # The frontend launches games through the guarded emulator wrapper.
            stack.close()
        child=subprocess.Popen(command,env=env)
        def stop(signum,frame):
            if child.poll() is None:child.send_signal(signum)
        previous={sig:signal.signal(sig,stop) for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]}
        try:return child.wait()
        finally:
            for sig,handler in previous.items():signal.signal(sig,handler)
            try:
                if mode!='frontend':export_metadata(mount,manifest,alias,Path(host['ryujinx_dir']))
            except (OSError,ValueError) as ex:print('Не удалось сохранить настройки обновлений: '+str(ex),file=sys.stderr)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (LibraryError,OSError,ValueError) as ex:
        print('Switch Library: '+str(ex),file=sys.stderr,flush=True)
        if shutil.which('notify-send'):subprocess.run(['notify-send','Switch Library',str(ex)],capture_output=True)
        raise SystemExit(1)
