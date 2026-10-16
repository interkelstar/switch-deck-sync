"""Migrate the early slot-library prototype; never run its launch helpers."""
import json
import os
from pathlib import Path
import re
import shlex
import xml.etree.ElementTree as ET


PATH_KEYS = ('emulationPath', 'romsPath', 'toolsPath', 'biosPath', 'savesPath', 'storagePath')


def shell_paths(home):
    """Parse only literal path assignments, without sourcing shell configuration."""
    values = {'HOME': str(home)}
    path = home / '.config/EmuDeck/settings.sh'
    if path.is_file():
        for line in path.read_text().splitlines():
            match = re.match(r'^(?:export\s+)?(' + '|'.join(PATH_KEYS) + r')=(.*)$', line.strip())
            if not match:
                continue
            tokens = shlex.split(match[2], comments=True)
            if len(tokens) != 1 or '`' in tokens[0] or '$(' in tokens[0]:
                raise ValueError('Unsupported EmuDeck path assignment: ' + match[1])
            value = tokens[0]
            for key, replacement in values.items():
                value = value.replace('${' + key + '}', replacement).replace('$' + key, replacement)
            if '$' in value or not Path(value).is_absolute():
                raise ValueError('Unsupported EmuDeck path assignment: ' + match[1])
            values[match[1]] = value
    return {key: value for key, value in values.items() if key != 'HOME'}


def detect(home):
    old = home / '.local/share/switch-library'
    native = home / '.local/share/switch-deck-sync/installation.json'
    if native.is_file() or not (old / 'host.json').is_file():
        return None
    host = json.loads((old / 'host.json').read_text())
    if host.get('schema') != 2 or host.get('ryujinx_dir') != str(home / '.config/Ryujinx'):
        raise ValueError('Unrecognised legacy library. Restore its previous settings first.')
    return old, host


def native_paths(home):
    paths = shell_paths(home)
    tools = Path(paths.get('toolsPath', str(home / 'Emulation/tools')))
    if detect(home):
        return home / 'Emulation/roms', tools / 'launchers/ryujinx.sh'
    settings = home / '.config/steam-rom-manager/userData/userSettings.json'
    srm = json.loads(settings.read_text()).get('environmentVariables', {}) if settings.is_file() else {}
    value = paths.get('romsPath') or srm.get('romsDirectory')
    if not value and paths.get('emulationPath'):
        value = str(Path(paths['emulationPath']) / 'roms')
    if not value or not Path(value).is_absolute():
        raise ValueError('Install EmuDeck and Steam ROM Manager first.')
    roms = Path(value)
    if 'toolsPath' not in paths:
        tools = roms.parent / 'tools'
    return roms, tools / 'launchers/ryujinx.sh'


def plan(home, root, launcher, copy_tree, local, library_id, progress):
    """Validate the entire legacy migration before any functional changes."""
    detected = detect(home)
    if not detected:
        return None
    old, host = detected
    for name in ('bis', 'system', 'mods', 'sdcard'):
        p = root / name
        if not p.is_symlink() or not Path(os.readlink(p)).is_relative_to(old / 'card'):
            raise ValueError('Legacy data link changed; inspect before migration: ' + str(p))
    executable = Path(host['emulator_executable'])
    if executable != home / 'Applications/publish/Ryujinx' or not executable.is_file():
        raise ValueError('Unsupported legacy emulator location')
    wrapper = executable.with_suffix('.sh')
    if str(old) not in wrapper.read_text():
        raise ValueError('Legacy emulator wrapper changed; inspect before migration')
    candidates = list((home / 'Emulation/backups').glob('*/Ryujinx.before-switch-library.sh'))
    candidates += [executable.with_name('Ryujinx.before-switch-library.sh')]
    originals = {p.read_bytes() for p in candidates if p.is_file()}
    if len(originals) != 1:
        raise ValueError('A unique original Ryujinx startup script is required for migration')
    original = originals.pop()
    if b'"$SCRIPT_DIR/Ryujinx" "$@"' not in original or b'switch-library' in original:
        raise ValueError('Original Ryujinx startup script could not be verified')
    tools = launcher.parent.parent
    frontend = tools / 'launchers/es-de/es-de.sh'
    if not frontend.is_file():
        raise ValueError('Stock EmuDeck ES-DE launcher is missing')
    changes = {wrapper: (original, 0o755)}
    # Edit only path fields; controller choices and all other settings stay intact.
    settings = home / '.config/EmuDeck/settings.sh'
    replacements = {key: str(home / 'Emulation' / suffix) for key, suffix in
                    [('emulationPath', ''), ('romsPath', 'roms'), ('biosPath', 'bios'),
                     ('savesPath', 'saves'), ('storagePath', 'storage')]}
    text = settings.read_text()
    for key, value in replacements.items():
        text, count = re.subn(r'(?m)^(?:export\s+)?' + key + r'=.*$', key + '=' + shlex.quote(value), text)
        if count != 1:
            raise ValueError('Missing or duplicate EmuDeck path: ' + key)
    changes[settings] = (text.encode(), 0o600)
    settings_json = settings.with_suffix('.json')
    if settings_json.is_file():
        value = json.loads(settings_json.read_text())
        # EmuDeck UI storagePath is the volume containing Emulation, not the
        # shell storagePath (which points to Emulation/storage).
        value['storagePath'] = str(home)
        changes[settings_json] = ((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode(), 0o600)
    srm = home / '.config/steam-rom-manager/userData'
    user_settings = srm / 'userSettings.json'
    value = json.loads(user_settings.read_text())
    env = value.setdefault('environmentVariables', {})
    old_roms = env.get('romsDirectory', '')
    env['romsDirectory'] = str(home / 'Emulation/roms')
    env['retroarchPath'] = str(tools / 'launchers/retroarch.sh')
    changes[user_settings] = ((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode(), 0o600)
    # Existing parser entries can contain literal paths as well as variables.
    parser = srm / 'userConfigurations.json'
    if parser.is_file():
        value = json.loads(parser.read_text())
        def convert(v):
            if isinstance(v, str):
                if old_roms:
                    v = v.replace(str(Path(old_roms).parent / 'tools/launchers'), str(tools / 'launchers'))
                    v = v.replace(old_roms, str(home / 'Emulation/roms'))
                return v.replace(str(old / 'ryujinx.sh'), str(launcher))
            if isinstance(v, dict):
                return {k: convert(x) for k, x in v.items()}
            if isinstance(v, list):
                return [convert(x) for x in v]
            return v
        changes[parser] = ((json.dumps(convert(value), ensure_ascii=False, indent=2) + '\n').encode(), 0o600)
    xml = home / 'ES-DE/custom_systems/es_find_rules.xml'
    if xml.is_file():
        text = xml.read_text().replace(str(old / 'ryujinx.sh'), str(launcher))
        ET.fromstring(text)
        changes[xml] = (text.encode(), 0o644)
    xml = home / 'ES-DE/settings/es_settings.xml'
    if xml.is_file():
        # Preserve the original XML representation and every other preference.
        text, count = re.subn(r'(<string\s+name="ROMDirectory"\s+value=")[^"]*("\s*/>)',
                             lambda m: m[1] + str(home / 'Emulation/roms').replace('&', '&amp;').replace('"', '&quot;') + m[2], xml.read_text())
        if count != 1:
            raise ValueError('Cannot determine ES-DE ROMDirectory')
        # ES-DE writes settings as XML fragments, without a common root.
        ET.fromstring('<settings>' + re.sub(r'^\s*<\?xml[^?]*\?>', '', text) + '</settings>')
        changes[xml] = (text.encode(), 0o644)
    # Repair all desktop entry points created by the old prototype.
    for folder in (home / '.local/share/applications', home / 'Desktop'):
        for desktop in folder.glob('*.desktop'):
            text = desktop.read_text()
            if str(old) not in text:
                continue
            if desktop == home / '.local/share/applications/switch-deck-sync.desktop':
                continue  # Replaced by the installer's normal desktop entry.
            sync = str(old / 'sync.sh') in text
            if sync:
                target = local / 'sync.sh'
            elif str(old / 'ryujinx.sh') in text:
                target = launcher
            elif str(old / 'frontend.sh') in text:
                target = frontend
            else:
                raise ValueError('Unknown legacy desktop entry: ' + str(desktop))
            lines = []
            for line in text.splitlines():
                if line.startswith('Exec='):
                    line = 'Exec="' + str(target).replace('"', '\\"') + '"'
                elif line.startswith('Path='):
                    line = 'Path=' + str(target.parent)
                elif sync and line.startswith('Icon='):
                    line = 'Icon=' + str(local / 'art/icon.png')
                lines.append(line)
            changes[desktop] = (('\n'.join(lines) + '\n').encode(), 0o755)
    # Cache copies are verified; old files remain available for rollback. A
    # failed preparation may leave an identical cache copy, never changed saves.
    cache = old / 'libraries' / library_id.lower() / 'games'
    if not cache.is_dir() or (root / 'games').resolve() != cache.resolve():
        raise ValueError('Legacy game cache does not match the selected card')
    destination = local / 'libraries' / library_id.lower() / 'games'
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(cache.rglob('*')):
        # DLC/update JSON comes from the card's portable manifest, not the old
        # host path. A failed service start may already have materialised it in
        # the new cache; do not compare it to obsolete absolute paths on retry.
        if entry.is_file() and entry.name not in ('updates.json', 'dlc.json'):
            copy_tree(entry, destination / entry.relative_to(cache), progress)
    return {'old': old, 'changes': changes, 'frontend': frontend,
            'sync_alias': home / 'Emulation/tools/switch-save-sync'}


def apply(tx, migration, local):
    if not migration:
        return
    for path, (data, mode) in migration['changes'].items():
        tx.replace(path, data, mode=mode)
    alias = migration['sync_alias']
    if alias.is_symlink() and str(migration['old']) in os.readlink(alias):
        tx.replace(alias, link=local / 'active/sync')
    # Keep a complete undoable copy, but remove the old runtime from its live
    # location so no surviving shortcut can accidentally execute it.
    tx.park(migration['old'])
