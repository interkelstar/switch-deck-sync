"""Offline Steam shortcut integration. The caller must stop Steam first."""
import struct
import zlib


class UInt64(int):
    pass


def decode(data):
    offset = 0

    def string():
        nonlocal offset
        end = data.index(0, offset)
        value = data[offset:end].decode('utf-8')
        offset = end + 1
        return value

    def obj():
        nonlocal offset
        result = {}
        while offset < len(data):
            kind = data[offset]
            offset += 1
            if kind == 8:
                return result
            name = string()
            if kind == 0:
                value = obj()
            elif kind == 1:
                value = string()
            elif kind in (2, 7):
                size = 4 if kind == 2 else 8
                value = struct.unpack_from('<I' if size == 4 else '<Q', data, offset)[0]
                if size == 8:
                    value = UInt64(value)
                offset += size
            else:
                raise ValueError('Unsupported Steam shortcut type: ' + str(kind))
            result[name] = value
        raise ValueError('Truncated Steam shortcuts')

    result = obj()
    if offset != len(data):
        raise ValueError('Trailing Steam shortcut data')
    return result


def encode(values):
    result = bytearray()
    for name, value in values.items():
        kind = 0 if isinstance(value, dict) else 1 if isinstance(value, str) else 7 if isinstance(value, UInt64) else 2
        result.append(kind)
        result.extend(str(name).encode() + b'\0')
        if kind == 0:
            result.extend(encode(value))
        elif kind == 1:
            if '\0' in value:
                raise ValueError('NUL in Steam shortcut')
            result.extend(value.encode() + b'\0')
        else:
            if not 0 <= value <= (0xffffffffffffffff if kind == 7 else 0xffffffff):
                raise ValueError('Unsupported integer in Steam shortcuts')
            result.extend(struct.pack('<Q' if kind == 7 else '<I', value))
    result.append(8)
    return bytes(result)


def upsert(data, entries):
    """Preserve existing IDs, artwork associations, input settings and unrelated games."""
    values = decode(data) if data else {'shortcuts': {}}
    shortcuts = values.setdefault('shortcuts', {})
    ids = {}
    for entry in entries:
        title = entry.get('title_id')
        names = [entry['appname'], *entry.get('match_names', [])]
        matches = [s for s in shortcuts.values() if s.get('appname') in names
                   and (not title or 'ryujinx' in s.get('exe', '').lower())]
        if not matches and title:
            matches = [s for s in shortcuts.values()
                       if 'ryujinx' in s.get('exe', '').lower()
                       and title.lower() in s.get('LaunchOptions', '').lower()]
        if len(matches) > 1:
            raise ValueError('Ambiguous Steam shortcut: ' + entry['appname'])
        if matches:
            shortcut = matches[0]
        else:
            appid = zlib.crc32((entry['exe'] + entry['appname']).encode()) | 0x80000000
            used = {s.get('appid') for s in shortcuts.values()}
            if appid in used:
                raise ValueError('Steam shortcut ID collision')
            shortcut = {'appid': appid, 'IsHidden': 0, 'AllowDesktopConfig': 1,
                        'AllowOverlay': 1, 'OpenVR': 0, 'Devkit': 0,
                        'DevkitGameID': '', 'LastPlayTime': 0, 'tags': {}}
            index = max((int(k) for k in shortcuts if k.isdigit()), default=-1) + 1
            shortcuts[str(index)] = shortcut
        shortcut.update({k: v for k, v in entry.items() if k not in ('title_id', 'match_names')})
        ids[entry['appname']] = shortcut['appid']
    return encode(values), ids
