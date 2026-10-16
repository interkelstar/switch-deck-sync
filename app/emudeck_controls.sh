#!/usr/bin/env bash
# Reuse the installed EmuDeck AutoMap implementation for our local configuration.
# Do not run EmuDeck's migration, save-link setup, updates or cloud synchronisation.
sds_controls_config=$1
sds_controls_backend=$2
shift 2
sds_controls_command=("$@")

if [ ! -r "$sds_controls_config" ] || [ ! -r "$sds_controls_backend/functions/all.sh" ]; then
    echo 'Switch Deck Sync: EmuDeck configuration is unavailable. Reinstall or repair the host setup.' >&2
    exit 1
fi

sds_controls_dir=$(mktemp -d /tmp/switch-deck-sync-controls.XXXXXXXX) || exit 1
trap 'rm -rf -- "$sds_controls_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
cp -- "$sds_controls_config" "$sds_controls_dir/Config.json" || exit 1

# all.sh reads this host's EmuDeck settings. Keep its output private and do not
# include it in public diagnostics: those settings can contain credentials.
if ! source "$sds_controls_backend/functions/all.sh" >"$sds_controls_dir/load.log" 2>&1; then
    echo 'Switch Deck Sync: could not load the installed EmuDeck controller support.' >&2
    exit 1
fi
if ! declare -F Ryujinx_set_gamepad_name >/dev/null; then
    echo 'Switch Deck Sync: update EmuDeck to a version with Ryujinx AutoMap support.' >&2
    exit 1
fi

# Upstream uses this variable for its edits. Work on a private temporary copy;
# neither the original EmuDeck profile nor the card is a configuration target.
Ryujinx_configFile="$sds_controls_dir/Config.json"
if ! Ryujinx_set_gamepad_name >"$sds_controls_dir/automap.log" 2>&1; then
    # Desktop Mode can legitimately have no gamepad. EmuDeck retains the current
    # mapping in that case; the next Game Mode launch tries detection again.
    echo 'Switch Deck Sync: AutoMap could not detect a controller; keeping the current host mapping.' >&2
fi

/usr/bin/python3 - "$sds_controls_config" "$sds_controls_dir/Config.json" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

target, staged = map(Path, sys.argv[1:])
original = json.loads(target.read_text())
updated = json.loads(staged.read_text())
controls = updated.get('input_config')
if not isinstance(controls, list) or not all(isinstance(c, dict) for c in controls):
    raise SystemExit('Switch Deck Sync: invalid controller configuration returned by EmuDeck.')
if original.get('input_config') != controls:
    original['input_config'] = controls
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                     prefix='.controls-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(original, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
PY
if [ "$?" -ne 0 ]; then exit 1; fi

rm -rf -- "$sds_controls_dir"
trap - EXIT INT TERM HUP
# Keep SDL device filters exported by the native AutoMap hook for the emulator.
exec "${sds_controls_command[@]}"
