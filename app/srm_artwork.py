"""Preserve native SRM image-choice exports on a card, without changing Steam."""
import datetime
import json
import os
from pathlib import Path
import stat
import uuid

import card_library as card

RELATIVE = 'Emulation/artwork/srm-image-choices'
MANIFESTS = ('_selections.json', 'selections.json')
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.bmp', '.tga', '.svg'}


def export_files(source):
    source = Path(source)
    if not any((source / name).is_file() for name in MANIFESTS) and (source / 'srm-image-choices').is_dir():
        source = source / 'srm-image-choices'
    if source.is_symlink() or not source.is_dir():
        raise ValueError('Select the SRM image-choices export folder. / Выбери папку экспорта SRM.')
    manifests = [source / name for name in MANIFESTS if (source / name).is_file()]
    if len(manifests) != 1 or manifests[0].is_symlink() or manifests[0].stat().st_size > 4 * 1024 * 1024:
        raise ValueError('The folder has no unique SRM selections file. / Не найден файл экспорта SRM.')
    selections = json.loads(manifests[0].read_text(encoding='utf-8'))
    if not isinstance(selections, list) or not selections or len(selections) > 10000:
        raise ValueError('Invalid or empty SRM export. / Некорректный или пустой экспорт SRM.')
    files = {manifests[0].name}
    for selection in selections:
        if not isinstance(selection, dict) or not isinstance(selection.get('images'), dict):
            raise ValueError('Invalid SRM image choices')
        for image in selection['images'].values():
            if image is None:
                continue
            if not isinstance(image, dict) or not isinstance(image.get('pool'), str):
                raise ValueError('Invalid SRM image reference')
            relative = card.relative_path(image.get('filename'))
            if relative.suffix.lower() not in EXTENSIONS:
                raise ValueError('Unexpected SRM image type: ' + str(relative))
            path = source / relative
            if any(p.is_symlink() for p in [path, *path.parents] if p != source.parent and p.is_relative_to(source)):
                raise ValueError('Linked SRM export files are not supported')
            if not path.is_file() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 50 * 1024 * 1024:
                raise ValueError('Missing or oversized SRM image: ' + str(relative))
            files.add(relative.as_posix())
    if len(files) > 20000 or sum((source / name).stat().st_size for name in files) > 512 * 1024 * 1024:
        raise ValueError('SRM export is too large')
    return source, sorted(files)


def destination(mount):
    card.validated_manifest(mount)
    return card.contained(mount, RELATIVE)


def save_export(source, mount, copy_file, progress=lambda text: None):
    """Publish verified copies; retain a previous export and the selected source."""
    source, files = export_files(source)
    target = destination(mount)
    if source.resolve() == target.resolve():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError('Unexpected artwork destination link')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    stage = target.with_name('.srm-copy-' + stamp)
    stage.mkdir(mode=0o700)
    previous = target.with_name('srm-image-choices-before-' + stamp)
    for name in files:
        copy_file(source / name, stage / name, progress)
    export_files(stage)
    # Complete export folders are the only things renamed here. No recursive
    # deletion, Steam writes or edits to the SRM selections format are involved.
    if target.exists():
        if not target.is_dir():
            raise ValueError('Artwork destination is not a directory')
        target.rename(previous)
    try:
        stage.rename(target)
    except BaseException:
        if previous.exists() and not target.exists():
            previous.rename(target)
        raise
    fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return target
