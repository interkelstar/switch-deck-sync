"""Discover account saves; no user names, title IDs or addresses are built in."""
import datetime
import ftplib
import json
import ipaddress
from pathlib import Path
import re
import shutil
import struct

import switch_save_sync as core

UID = re.compile(r'\[([0-9a-fA-F]{32})\]')
TITLE = re.compile(r'\[([0-9a-fA-F]{16})\]$')

def emulator_candidates():
    home = Path.home()
    values = [home/'.config/Ryujinx',home/'Applications/publish/portable',
              home/'Applications/Ryujinx/portable']
    values += list((home/'.var/app').glob('*/config/Ryujinx'))
    return [p for p in values if (p/'bis/user/save').is_dir()]

def emulator_root(settings):
    value = settings.get('ryujinx_dir')
    if value:
        return Path(value).expanduser()
    if settings.get('save_root'):
        return Path(settings['save_root']).parents[2]
    options = emulator_candidates()
    return options[0] if options else Path.home()/'.config/Ryujinx'

def local_saves(settings):
    root = emulator_root(settings)
    saves = []
    folder = root/'bis/user/save'
    if not folder.exists():
        raise core.SyncError('Не найдены сейвы Ryujinx. Укажи папку Ryujinx в настройках.')
    for p in sorted(folder.iterdir()):
        if not p.is_dir() or p.is_symlink() or not (p/'ExtraData0').is_file():
            continue
        data = (p/'ExtraData0').read_bytes()
        if len(data)<64 or data[32]!=1 or not any(data[8:24]):
            continue  # User account saves only; exclude BCAT and Device data.
        title = f'{int.from_bytes(data[:8],"little"):016X}'
        if not (p/'0').is_dir():
            continue
        metadata = root/'games'/title.lower()/'gui/metadata.json'
        name = ''
        if metadata.is_file():
            try:name=json.loads(metadata.read_text()).get('title','')
            except (OSError,ValueError):pass
        saves.append({'title_id':title,'save_id':p.name,'user_id':data[8:24].hex(),
                      'name':name,'save_path':str(p)})
    return saves

def local_profiles(settings):
    saves = local_saves(settings)
    owners = {s['user_id'] for s in saves}
    names = {}
    p = emulator_root(settings)/'system/Profiles.json'
    if p.is_file():
        for item in json.loads(p.read_text()).get('profiles',[]):
            value = item.get('user_id','')
            if re.fullmatch('[0-9a-fA-F]{32}',value):
                candidates = [struct.pack('<QQ',int(value[:16],16),int(value[16:],16)).hex(),
                              int(value,16).to_bytes(16,'little').hex()]
                matching = set(candidates)&owners
                if len(matching)==1:names[matching.pop()]=item.get('name','Профиль Ryujinx')
    return [{'uid':uid,'name':names.get(uid,'Профиль '+uid[:8])} for uid in sorted(owners)]

def connect(settings):
    if not settings.get('host'):
        raise core.SyncError('Сначала укажи адрес Switch в настройках подключения.')
    ftp=ftplib.FTP();ftp.connect(settings['host'],settings.get('port',5000),timeout=12);ftp.login()
    return ftp

def parse_endpoint(value):
    try:
        host,port=value.strip().rsplit(':',1)
        host=str(ipaddress.IPv4Address(host.strip()));port=int(port)
        if not 1<=port<=65535:raise ValueError()
        return host,port
    except (ValueError,TypeError):
        raise core.SyncError('Введи IPv4 и порт, например 192.168.1.50:5000.') from None

def switch_profiles(settings):
    with connect(settings) as ftp:
        ftp.cwd('/save:');entries=ftp.nlst()
    profiles=[]
    for entry in entries:
        match=UID.search(entry)
        if match:
            profiles.append({'uid':match.group(1).upper(),'name':entry[:match.start()].strip(),
                             'path':'/save:/'+entry+'/files'})
    if not profiles:
        raise core.SyncError('Сервер не показал профили сохранений. Запусти ftpsrv Save Sync с доступом к сейвам.')
    return profiles

def game_key(game, account_path):
    match=UID.search(account_path)
    if not match:raise core.SyncError('Сначала выбери профиль Switch.')
    return game['title_id'].lower()+'-'+game['user_id']+'-'+match.group(1).lower()

def discover_games(settings):
    if not settings.get('account_path'):
        raise core.SyncError('Сначала выбери профиль Switch в настройках.')
    owner=settings.get('deck_profile_uid')
    if not owner:raise core.SyncError('Сначала выбери профиль Ryujinx в настройках.')
    with connect(settings) as ftp:
        ftp.cwd(settings['account_path']);entries=ftp.nlst()
    remote={}
    for entry in entries:
        match=TITLE.search(entry)
        if match and '/' not in entry and not any(x in entry for x in ['\\','\n','\r']):
            remote[match.group(1).upper()]=(entry[:match.start()].strip(),entry)
    local={item['title_id']:item for item in local_saves(settings) if item['user_id']==owner}
    games=[]
    for title,(remote_title,entry) in remote.items():
        item=local.get(title)
        game=({k:v for k,v in item.items() if k!='save_path'} if item else
              {'title_id':title,'user_id':owner,'name':''})
        game['name']=game['name'] or remote_title or ('Игра '+game['title_id'])
        game['remote_name']=entry
        game['key']=game_key(game,settings['account_path'])
        game['available']=item is not None
        games.append(game)
    return sorted(games,key=lambda g:(not g['available'],g['name'].casefold()))

def load_or_create(home):
    path=home/'settings.json'
    settings=core.read_json(path) if path.exists() else {'host':'','port':5000,'games':{}}
    settings.setdefault('games',{})
    root=emulator_root(settings)
    settings['ryujinx_dir']=str(root)
    settings['save_root']=str(root/'bis/user/save')
    if settings.get('schema')!=2:
        if path.exists():
            stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup=home/'configuration-backups'/stamp;backup.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,backup/'settings.json')
            if (home/'state.json').exists():shutil.copy2(home/'state.json',backup/'state.json')
        try:profiles=local_profiles(settings)
        except (core.SyncError,OSError):profiles=[]
        if len(profiles)==1:
            settings['deck_profile_uid']=profiles[0]['uid'];settings['deck_profile_name']=profiles[0]['name']
        if settings.get('account_path'):
            settings['switch_profile_name']=settings['account_path'].split('/save:/',1)[-1].split(' [',1)[0]
        state=core.read_json(home/'state.json') if (home/'state.json').exists() else {}
        migrated={}
        for old_key,old in settings['games'].items():
            game=dict(old)
            extra=Path(settings['save_root'])/game['save_id']/'ExtraData0'
            if not extra.is_file():continue
            game['user_id']=extra.read_bytes()[8:24].hex()
            key=game_key(game,settings['account_path'])
            migrated[key]=game
            if old_key in state and key not in state:state[key]=state[old_key]
        settings['games']=migrated;settings['schema']=2
        core.atomic_json(home/'state.json',state)
    if not (home/'state.json').exists():core.atomic_json(home/'state.json',{})
    core.atomic_json(path,settings)
    return settings

def save(home,settings):
    settings['save_root']=str(emulator_root(settings)/'bis/user/save')
    core.atomic_json(home/'settings.json',settings)
