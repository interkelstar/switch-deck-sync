#!/usr/bin/env python3
"""Allowlisted, reproducible release archives. Runtime data can never enter by glob."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['install.py', 'install.sh', 'Install.desktop', 'README.md', 'LICENSE', 'VERSION',
         'app/card_library.py', 'app/switch_save_sync.py', 'app/sync_config.py', 'app/sync_ui.py',
         'app/setup_library.py', 'app/setup_wizard.py', 'app/steam_shortcuts.py',
         'app/native_card.py', 'app/legacy_migration.py', 'app/sync_launcher.py',
         'docs/ARCHITECTURE.md', 'docs/SWITCH.md', 'docs/STEAM-MACHINE-TEST.md',
         'switch/ftpsrv-save-sync.nro', 'switch/source.zip', 'switch/save-write.patch',
         'switch/config.ini.example', 'switch/THIRD-PARTY-NOTICES.txt']
ART = ['cover.png', 'hero.png', 'grid.png', 'logo.png', 'logo.svg', 'icon.png', 'icon.svg',
       'icon.ico', 'icon.bmp', 'PROMPTS.txt', 'GRID-PROMPT.txt']
FILES += ['art/' + name for name in ART]
FORBIDDEN = {'settings.json', 'state.json', 'pending.json', 'prod.keys', 'title.keys',
             'host.json', 'installation.json', 'known_hosts', 'deck_access'}


def contents(root=ROOT):
    values = {}
    for name in FILES:
        path = root / name
        if path.is_symlink() or path.name in FORBIDDEN or path.suffix.lower() in ('.xci', '.nsp', '.nca', '.keys'):
            raise ValueError('Private or linked release file: ' + name)
        data = path.read_bytes()
        if path.suffix in ('.py', '.sh', '.desktop', '.md', '.txt', '.patch', '.example'):
            data = data.replace(b'\r\n', b'\n')
        values[name] = data
    for name, data in values.items():
        if name.endswith(('.py', '.sh', '.desktop', '.md', '.txt', '.svg', '.patch', '.example')):
            text = data.decode('utf-8')
            # Project-specific accidental private material, not sample IPs or title IDs.
            for pattern in ('/home/deck/', '192.168.1.90', '192.168.1.60', 'kelstar', 'sudoPass'):
                if pattern in text:
                    raise ValueError('Private string in release file: ' + name)
    values['SHA256SUMS.json'] = (json.dumps({name: hashlib.sha256(data).hexdigest()
                                          for name, data in sorted(values.items())}, indent=2) + '\n').encode()
    return values


def build(root=ROOT):
    version = (root / 'VERSION').read_text().strip()
    if not version or any(c not in '0123456789abcdefghijklmnopqrstuvwxyz.-' for c in version):
        raise ValueError('Invalid version')
    values = contents(root)
    out = root / 'dist'
    out.mkdir(exist_ok=True)
    prefix = 'Switch-Deck-Sync-' + version
    archive = out / (prefix + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(values.items()):
            info = zipfile.ZipInfo(prefix + '/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            mode = 0o755 if name in ('install.sh', 'Install.desktop') else 0o644
            info.create_system = 3
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    tarpath = out / (prefix + '.tar.gz')
    with tarpath.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            for name, data in sorted(values.items()):
                info = tarfile.TarInfo(prefix + '/' + name)
                info.mode = 0o755 if name in ('install.sh', 'Install.desktop') else 0o644
                info.size = len(data)
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
    sums = out / 'SHA256SUMS.txt'
    sums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                            for p in (archive, tarpath)), encoding='utf-8')
    print(json.dumps({'version': version, 'files': len(values), 'archives': [p.name for p in (archive, tarpath)]}))
    return archive, tarpath


if __name__ == '__main__':
    build()
