"""SDL window for Steam Deck Game Mode. Uses the system SDL2 and SDL2_ttf."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import queue
import struct
import threading

class Rect(C.Structure):
    _fields_ = [('x', C.c_int), ('y', C.c_int), ('w', C.c_int), ('h', C.c_int)]

class Color(C.Structure):
    _fields_ = [('r', C.c_uint8), ('g', C.c_uint8), ('b', C.c_uint8), ('a', C.c_uint8)]

def run_gui(check=False):
    import switch_save_sync as core
    os.environ['SDL_VIDEODRIVER'] = 'x11'
    appid = os.environ.get('SteamAppId')
    os.environ['SDL_VIDEO_X11_WMCLASS'] = ('steam_app_' + appid) if appid else 'SwitchDeckSync'
    sdl = C.CDLL(ctypes.util.find_library('SDL2'))
    ttf = C.CDLL(ctypes.util.find_library('SDL2_ttf'))
    def bind(lib, name, restype, args):
        fn = getattr(lib, name);fn.restype = restype;fn.argtypes = args;return fn
    P=C.c_void_p;I=C.c_int;U=C.c_uint32;S=C.c_char_p
    bind(sdl,'SDL_Init',I,[U]);bind(sdl,'SDL_Quit',None,[])
    bind(sdl,'SDL_GetError',S,[]);bind(sdl,'SDL_GetTicks',U,[])
    bind(sdl,'SDL_SetHint',I,[S,S])
    bind(sdl,'SDL_CreateWindow',P,[S,I,I,I,I,U]);bind(sdl,'SDL_DestroyWindow',None,[P])
    bind(sdl,'SDL_RWFromFile',P,[S,S]);bind(sdl,'SDL_LoadBMP_RW',P,[P,I])
    bind(sdl,'SDL_SetWindowIcon',None,[P,P])
    bind(sdl,'SDL_CreateRenderer',P,[P,I,U]);bind(sdl,'SDL_DestroyRenderer',None,[P])
    bind(sdl,'SDL_RenderSetLogicalSize',I,[P,I,I])
    bind(sdl,'SDL_SetRenderDrawColor',I,[P,C.c_uint8,C.c_uint8,C.c_uint8,C.c_uint8])
    bind(sdl,'SDL_RenderClear',I,[P]);bind(sdl,'SDL_RenderPresent',None,[P])
    bind(sdl,'SDL_RenderFillRect',I,[P,C.POINTER(Rect)])
    bind(sdl,'SDL_CreateTextureFromSurface',P,[P,P]);bind(sdl,'SDL_FreeSurface',None,[P])
    bind(sdl,'SDL_QueryTexture',I,[P,P,P,C.POINTER(I),C.POINTER(I)])
    bind(sdl,'SDL_RenderCopy',I,[P,P,P,C.POINTER(Rect)])
    bind(sdl,'SDL_DestroyTexture',None,[P]);bind(sdl,'SDL_PollEvent',I,[P])
    bind(sdl,'SDL_NumJoysticks',I,[]);bind(sdl,'SDL_IsGameController',I,[I])
    bind(sdl,'SDL_GameControllerOpen',P,[I]);bind(sdl,'SDL_GameControllerClose',None,[P])
    bind(sdl,'SDL_StartTextInput',None,[]);bind(sdl,'SDL_StopTextInput',None,[])
    bind(sdl,'SDL_GetRendererOutputSize',I,[P,C.POINTER(I),C.POINTER(I)])
    bind(ttf,'TTF_Init',I,[]);bind(ttf,'TTF_Quit',None,[])
    bind(ttf,'TTF_OpenFont',P,[S,I]);bind(ttf,'TTF_CloseFont',None,[P])
    bind(ttf,'TTF_SizeUTF8',I,[P,S,C.POINTER(I),C.POINTER(I)])
    bind(ttf,'TTF_RenderUTF8_Blended',P,[P,S,Color])
    sdl.SDL_SetHint(b'SDL_RENDER_DRIVER',b'opengl')
    if sdl.SDL_Init(0x6020):raise RuntimeError(sdl.SDL_GetError().decode())
    if ttf.TTF_Init():raise RuntimeError('Не удалось открыть шрифты')
    window=sdl.SDL_CreateWindow(b'Switch Deck Sync',0x2FFF0000,0x2FFF0000,1280,800,0x1007)
    renderer=sdl.SDL_CreateRenderer(window,-1,6)
    if not window or not renderer:raise RuntimeError(sdl.SDL_GetError().decode())
    for icon_path in [Path(__file__).resolve().parent/'art/icon.bmp',core.HOME/'art/icon.bmp',core.HOME/'icon.bmp']:
        if icon_path.is_file():
            icon_surface=sdl.SDL_LoadBMP_RW(sdl.SDL_RWFromFile(str(icon_path).encode(),b'rb'),1)
            if icon_surface:sdl.SDL_SetWindowIcon(window,icon_surface);sdl.SDL_FreeSurface(icon_surface)
            break
    sdl.SDL_RenderSetLogicalSize(renderer,1280,800)
    sdl.SDL_StopTextInput()
    candidates=[Path('/usr/share/fonts/TTF/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
    fontpath=next((x for x in candidates if x.exists()),None)
    if not fontpath:fontpath=next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'))
    fonts={size:ttf.TTF_OpenFont(str(fontpath).encode(),size) for size in [22,26,32,42]}
    if not all(fonts.values()):raise RuntimeError('Не удалось открыть шрифт')
    controllers=[]
    def open_controller(index):
        if sdl.SDL_IsGameController(index):
            c=sdl.SDL_GameControllerOpen(index)
            if c:controllers.append(c)
    for i in range(sdl.SDL_NumJoysticks()):open_controller(i)
    import sync_config as config
    import copy
    cache={};messages=queue.Queue();phase='home';status=''
    results=[];selection=0;buttons=[];reply=None;running=True;entry='';error='';last_axis=0
    settings=config.load_or_create(core.HOME)
    choices=[];selected=set();page=0;pick_kind='';edit_kind=''
    def persist():config.save(core.HOME,settings)
    def go(where):
        nonlocal phase,selection,error
        sdl.SDL_StopTextInput();phase=where;selection=0;error=''
    def worker(snapshot):
        store=core.FTPStore(snapshot)
        try:
            def choose(name):
                event=threading.Event();answer={}
                messages.put(('conflict',name,event,answer));event.wait()
                return answer['choice']
            answer=core.Sync(snapshot,store,choose,lambda text:messages.put(('status',text))).run(check)
            messages.put(('done',answer))
        except Exception as ex:
            message=str(ex)
            if (core.HOME/'pending.json').exists():
                message+=' Не запускай игру на Switch. Повтори синхронизацию для восстановления.'
            messages.put(('error',message))
        finally:store.close()
    def start():
        nonlocal status,results
        go('working');status='Подключаюсь к Switch…';results=[]
        threading.Thread(target=worker,args=(copy.deepcopy(settings),),daemon=True).start()
    def discover(kind):
        nonlocal status,pick_kind
        pick_kind=kind;go('loading');status='Читаю профили и сохранения…'
        snapshot=copy.deepcopy(settings)
        def fetch():
            try:
                fn={'switch':config.switch_profiles,'deck':config.local_profiles,'games':config.discover_games}[kind]
                messages.put(('choices',fn(snapshot)))
            except Exception as ex:messages.put(('error',str(ex)))
        threading.Thread(target=fetch,daemon=True).start()
    def fill(rect,rgb):
        sdl.SDL_SetRenderDrawColor(renderer,*rgb,255);sdl.SDL_RenderFillRect(renderer,C.byref(Rect(*rect)))
    def text(value,x,y,size=26,rgb=(229,235,243),width=1136):
        font=fonts[size];line='';lines=[]
        for paragraph in str(value).split('\n'):
            for word in paragraph.split(' '):
                candidate=(line+' '+word).strip();w=I();h=I()
                ttf.TTF_SizeUTF8(font,candidate.encode(),C.byref(w),C.byref(h))
                if w.value>width and line:lines.append(line);line=word
                else:line=candidate
            lines.append(line);line=''
        for line in lines:
            if line:
                key=(line,size,rgb)
                if key not in cache:
                    surf=ttf.TTF_RenderUTF8_Blended(font,line.encode(),Color(*rgb,255))
                    texture=sdl.SDL_CreateTextureFromSurface(renderer,surf);sdl.SDL_FreeSurface(surf)
                    w=I();h=I();sdl.SDL_QueryTexture(texture,None,None,C.byref(w),C.byref(h))
                    cache[key]=(texture,w.value,h.value)
                texture,w,h=cache[key]
                sdl.SDL_RenderCopy(renderer,texture,None,C.byref(Rect(x,y,w,h)))
            y+=size+12
        return y
    def edit(kind):
        nonlocal edit_kind,entry
        edit_kind=kind;go('edit')
        entry=(settings.get('host','')+':'+str(settings.get('port',5000))) if kind=='server' else settings['ryujinx_dir']
        sdl.SDL_StartTextInput()
    def back():
        if phase in ['working','loading']:return
        if phase=='conflict':activate(2)
        elif phase=='home':activate(2)
        elif phase in ['settings','done','error']:go('home')
        else:go('settings')
    def activate(index):
        nonlocal running,phase,selection,entry,reply,status,error,page,selected
        if phase=='home':
            if index==0:start()
            elif index==1:go('settings')
            else:running=False
        elif phase=='settings':
            if index in [1,2,3,4] and (core.HOME/'pending.json').exists():
                go('error');error='Сначала повтори синхронизацию для восстановления прерванной передачи.'
                return
            if index==0:edit('server')
            elif index==1:
                if os.environ.get('SDS_DATA_DIR'):
                    go('error');error='Папкой Ryujinx управляет библиотека на карте. Для изменения подключения используй установщик.'
                else:edit('path')
            elif index==2:discover('switch')
            elif index==3:discover('deck')
            elif index==4:discover('games')
            else:go('home')
        elif phase=='done':go('home')
        elif phase=='conflict':
            event,answer=reply;answer['choice']=['switch','deck','skip'][index];event.set()
            go('working');status='Продолжаю синхронизацию…'
        elif phase=='error':
            if index==0:go('settings')
            else:go('home')
        elif phase=='edit':
            if index==1:go('settings');return
            try:
                if edit_kind=='server':
                    host,port=config.parse_endpoint(entry)
                    settings.update(host=host,port=port)
                else:
                    root=Path(entry.strip()).expanduser()
                    if not (root/'bis/user/save').is_dir():raise ValueError('В этой папке нет bis/user/save.')
                    if str(root)!=settings['ryujinx_dir']:
                        settings['games']={};settings.pop('deck_profile_uid',None);settings.pop('deck_profile_name',None)
                    settings['ryujinx_dir']=str(root)
                persist();go('settings')
            except (ValueError,core.SyncError) as ex:error=str(ex)
        elif phase=='pick':
            visible=choices[page*4:page*4+4];n=len(visible)
            if index<n:
                item=visible[index]
                if pick_kind=='games':
                    if not item.get('available',True):
                        error='Сначала запусти эту игру в Ryujinx и создай сохранение.'
                        return
                    error=''
                    if item['key'] in selected:selected.remove(item['key'])
                    else:selected.add(item['key'])
                else:
                    if pick_kind=='switch':
                        if settings.get('account_path')!=item['path']:settings['games']={}
                        settings.update(account_path=item['path'],switch_profile_name=item['name'])
                    else:
                        if settings.get('deck_profile_uid')!=item['uid']:settings['games']={}
                        settings.update(deck_profile_uid=item['uid'],deck_profile_name=item['name'])
                    persist();go('settings')
            elif index==n:page=max(0,page-1);selection=0
            elif index==n+1:page=min(max(0,(len(choices)-1)//4),page+1);selection=0
            elif index==n+2:
                if pick_kind=='games':
                    settings['games']={g['key']:{k:v for k,v in g.items() if k not in ['key','available']} for g in choices if g['key'] in selected and g.get('available',True)}
                    persist()
                go('settings')
            else:go('settings')
    event=C.create_string_buffer(64)
    try:
        while running:
            while True:
                try:message=messages.get_nowait()
                except queue.Empty:break
                if message[0]=='status':status=message[1]
                elif message[0]=='done':go('done');results=message[1]
                elif message[0]=='error':go('error');error=message[1]
                elif message[0]=='conflict':go('conflict');status=message[1];reply=message[2:];selection=2
                elif message[0]=='choices':
                    choices=message[1];selected=set(settings['games']);page=0;go('pick')
            while sdl.SDL_PollEvent(event):
                raw=event.raw;kind=struct.unpack_from('<I',raw)[0]
                if kind==0x100:
                    if phase not in ['working','conflict','loading']:running=False
                elif kind==0x303 and phase=='edit':entry+=raw[12:44].split(b'\0')[0].decode('utf-8',errors='ignore')
                elif kind==0x300:
                    key=struct.unpack_from('<i',raw,20)[0]
                    if key==8 and phase=='edit':entry=entry[:-1]
                    elif key==13 and buttons:activate(selection)
                    elif key==27:back()
                    elif key in [1073741903,1073741905,9] and buttons:selection=(selection+1)%len(buttons)
                    elif key in [1073741904,1073741906] and buttons:selection=(selection-1)%len(buttons)
                elif kind==0x651:
                    button=raw[12]
                    if button==0 and buttons:activate(selection)
                    elif button==1:back()
                    elif button in [12,14] and buttons:selection=(selection+1)%len(buttons)
                    elif button in [11,13] and buttons:selection=(selection-1)%len(buttons)
                elif kind==0x653:open_controller(struct.unpack_from('<i',raw,8)[0])
                elif kind==0x650 and buttons:
                    axis=raw[12];value=struct.unpack_from('<h',raw,16)[0];now=sdl.SDL_GetTicks()
                    if axis in [0,1] and abs(value)>18000 and now-last_axis>250:
                        selection=(selection+(1 if value>0 else -1))%len(buttons);last_axis=now
                elif kind==0x401:
                    x,y=struct.unpack_from('<ii',raw,20)
                    for index,(bx,by,bw,bh,label) in enumerate(buttons):
                        if bx<=x<bx+bw and by<=y<by+bh:activate(index);break
            sdl.SDL_SetRenderDrawColor(renderer,13,20,31,255);sdl.SDL_RenderClear(renderer)
            fill((0,0,640,7),(52,202,221));fill((640,0,640,7),(249,108,101))
            text('Switch Deck Sync',64,42,42)
            text('Сохранения рядом, прогресс с собой',66,106,22,(147,174,195))
            buttons=[]
            if phase=='home':
                text('Готов к синхронизации',66,210,32)
                address=settings.get('host') or 'Адрес пока не указан'
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
                buttons=[(66,630,350,82,'Взять Switch'),(465,630,350,82,'Взять Deck'),(864,630,350,82,'Пропустить')]
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
