"""Drive the actual SDL interface in Xvfb with synthetic data and no network."""
import base64
import ctypes as C
import ctypes.util
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

import i18n
import sync_config
import sync_ui
import switch_save_sync as core


def renderer_png(renderer, sdl):
    width = C.c_int()
    height = C.c_int()
    sdl.SDL_GetRendererOutputSize(renderer, C.byref(width), C.byref(height))
    pixels = C.create_string_buffer(width.value * height.value * 4)
    read = sdl.SDL_RenderReadPixels
    read.restype = C.c_int
    read.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32, C.c_void_p, C.c_int]
    if read(renderer, None, 0x16762004, pixels, width.value * 4):
        raise RuntimeError(sdl.SDL_GetError().decode())
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\0' + pixels.raw[row * width.value * 4:(row + 1) * width.value * 4]
                   for row in range(height.value))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', width.value, height.value, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


class InterfaceSmokeTests(unittest.TestCase):
    def test_english_and_russian_screens_navigation_and_language_persistence(self):
        available = os.environ.get('DISPLAY') and ctypes.util.find_library('SDL2') and ctypes.util.find_library('SDL2_ttf')
        if os.environ.get('SDS_REQUIRE_UI_TESTS'):
            self.assertTrue(available, 'The Linux acceptance job must supply SDL2, fonts and Xvfb')
        elif not available:
            self.skipTest('SDL/Xvfb UI smoke test runs in Linux CI')
        old_language = i18n.language()
        self.addCleanup(i18n.set_language, old_language)
        i18n.set_language('en')
        TAB, ENTER, ESC = 9, 13, 27
        # Each tuple describes one observed frame, then input for the next frame.
        steps = [
            ('home','en',[TAB,ENTER]), ('settings','en',[TAB]*5+[ENTER]),
            ('language','en',[TAB,ENTER]), ('settings','ru',[ESC]),
            ('home','ru',[TAB,ENTER]), ('settings','ru',[ENTER]), ('edit','ru',[ESC]),
            ('settings','ru',[TAB,TAB,ENTER]), ('pick','ru',[ESC]),
            ('settings','ru',[TAB]*5+[ENTER]), ('language','ru',[ENTER]),
            ('settings','en',[ENTER]), ('edit','en',[ESC]),
            ('settings','en',[TAB,TAB,ENTER]), ('pick','en',[ESC]),
            ('settings','en',[ESC]), ('home','en',[ENTER]),
            ('conflict','en',[ENTER]), ('done','en',[ENTER]),
            ('home','en',[ENTER]), ('error','en',[ESC]),
            ('home','en',[TAB,ENTER]), ('settings','en',[TAB]*5+[ENTER]),
            ('language','en',[TAB,ENTER]), ('settings','ru',[ESC]),
            ('home','ru',[ENTER]), ('error','ru',[ESC]),
            ('home','ru',[ENTER]), ('conflict','ru',[ENTER]),
            ('done','ru',[ENTER]), ('home','ru',[ESC]),
        ]
        state = {'index': 0, 'fail': False}
        proofs = {}
        observed = set()
        class Store:
            def __init__(self, settings): pass
            def close(self): pass
        class Engine:
            def __init__(self, settings, store, choose, progress):
                self.choose = choose
            def run(self, check):
                if state['fail']:
                    raise core.SyncError(i18n.tr('Сначала укажи адрес Switch в настройках подключения.'))
                self.choose('Example Game')
                return ['Example Game' + i18n.tr(': пропущено, обе копии сохранены')]
        deadline = time.monotonic() + 30
        def frame(phase, buttons, renderer, sdl):
            if state['index'] >= len(steps):
                return
            if time.monotonic() > deadline:
                self.fail('UI did not reach step ' + repr(steps[state['index']]))
            expected_phase, lang, keys = steps[state['index']]
            if phase != expected_phase or i18n.language() != lang:
                return
            observed.add((phase, lang))
            for x, y, w, h, label in buttons:
                self.assertTrue(0 <= x < x+w <= 1280 and 0 <= y < y+h <= 800, label)
            for i, a in enumerate(buttons):
                for b in buttons[i+1:]:
                    self.assertFalse(a[0] < b[0]+b[2] and b[0] < a[0]+a[2] and
                                     a[1] < b[1]+b[3] and b[1] < a[1]+a[3], (a[-1], b[-1]))
            if phase in ('settings','conflict') and lang == 'en' and phase not in proofs:
                proofs[phase] = renderer_png(renderer, sdl)
            if state['index'] in (19,25):
                state['fail'] = True
            elif state['index'] == 27:
                state['fail'] = False
            push = sdl.SDL_PushEvent
            push.restype = C.c_int
            push.argtypes = [C.c_void_p]
            for key in keys:
                event = C.create_string_buffer(64)
                struct.pack_into('<I', event, 0, 0x300)
                struct.pack_into('<i', event, 20, key)
                self.assertEqual(push(event), 1)
            state['index'] += 1
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / 'card-sync'
            home.mkdir()
            settings = {'schema':2, 'host':'10.0.0.50', 'port':5000, 'ryujinx_dir':str(Path(folder)/'Ryujinx'),
                        'switch_profile_name':'Switch Player', 'deck_profile_name':'Ryujinx Player',
                        'games':{'example':{'name':'Example Game'}}}
            (home / 'settings.json').write_text(json.dumps(settings))
            (home / 'state.json').write_text('{}')
            preferences = Path(folder) / 'host/preferences.json'
            with patch.object(core, 'HOME', home), patch.object(core, 'FTPStore', Store), patch.object(core, 'Sync', Engine), \
                    patch.object(i18n, 'PREFERENCES', preferences), \
                    patch.object(sync_config, 'switch_profiles', return_value=[{'name':'Switch Player','path':'/save:/Example/files'}]):
                self.assertEqual(sync_ui.run_gui(frame_hook=frame), 0)
            self.assertEqual(state['index'], len(steps))
            self.assertEqual(json.loads(preferences.read_text()), {'language':'ru'})
            self.assertNotIn('language', json.loads((home/'settings.json').read_text()))
        for phase in ('home','settings','language','edit','pick','conflict','done','error'):
            for lang in ('en','ru'):
                self.assertIn((phase,lang), observed)
        if os.environ.get('SDS_UI_PROOF') == '1':
            for name, data in proofs.items():
                print('UI_PROOF_' + name.upper() + '=' + base64.b64encode(data).decode(), flush=True)
