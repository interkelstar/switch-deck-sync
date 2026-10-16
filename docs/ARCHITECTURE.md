# Native EmuDeck data attachment

## Ownership

Game shortcuts point directly to the existing EmuDeck tools/launchers/ryujinx.sh.
There is no installed game-launch wrapper, alternate Ryujinx root, per-game Python
resolver, AutoMap bridge, backend patch or emulator executable call in this project.
Native EmuDeck/Ryujinx retains startup, updates, controls, gyro and graphics settings.

The installer detects the host EmuDeck ROM directory from Steam ROM Manager settings
or narrowly parses EmuDeck's path assignments. It never sources shell settings.
The base Emulation location must be Internal Storage for this preview.

## Host and card layout

The original ~/.config/Ryujinx/Config.json remains the active configuration. Only
game_dirs changes to EmuDeck's existing roms/switch path. No input, graphics or
other configuration fields change during attachment.

Host data links:
- ~/.config/Ryujinx/{bis,system,mods,sdcard,games} -> local/active/<name>
- EmuDeck's Emulation/roms/switch -> local/active/roms
- EmuDeck's Emulation/storage/ryujinx/patchesAndDlc -> local/active/patches

local is ~/.local/share/switch-deck-sync/.
A systemd user service, switch-deck-sync-card.service, maintains active data links.
The service never launches the emulator, sources EmuDeck functions or changes input.

A local target bundle links card-owned bis/system/mods/sdcard/roms/sync and the
host-owned libraries/<library-id>/games cache. active is atomically switched to
/proc/<service-pid>/fd/<bundle-fd>. The descriptor pins the LOCAL target directory,
not the card mount; normal eject is not held busy. When the service dies, /proc cannot
create fallback folders behind its dead descriptor. A clean stop/absent card points
active to /dev/null, also preventing substitute local save creation.

The service polls the configured reader every half second. MMC readers are detected
by transport; USB readers use a stable /dev/disk/by-path connection. UUID is only a
change signal, never an allowlist. Libraries are validated before attachment, and
card links escaping the card are rejected. There is no fallback to a different reader.

Card data remains:
- Emulation/switch-library.json (schema 1/2 accepted)
- Emulation/roms/switch/
- Emulation/storage/ryujinx/data/{bis,system,mods,sdcard}/
- Emulation/storage/ryujinx/patchesAndDlc/
- Emulation/tools/switch-save-sync/{settings.json,state.json,backups,...}

Update/DLC selections are materialised in host games caches using the stable
active/card prefix. Metadata changes are exported to portable @CARD@ templates.
Partial JSON writes are retried without disconnecting an active game. Physical card
removal during writes is unsupported; close games/sync and eject normally.

The service never switches to a different profile while Ryujinx/save sync is running.
A missing/replaced card invalidates attachment instead of mixing data. EmuDeck
reset changes to the managed data links are detected and require reinstalling this
attachment, not overriding the native configuration.

## Installation and rollback

Existing real host directories are renamed into durable transaction backups on the
same filesystem. Links/files are replaced with their originals journalled first.
Restore removes data links and moves the original directories back; it never copies
the card saves over the original host data or deletes card content. Crash recovery
handles directory moves before and after link publication.

Setup exits Steam before editing shortcuts, preserves recognised shortcut IDs/input
settings, and adds direct native emulator/game shortcuts plus the standalone sync app.
Existing EmuDeck launcher/backend bytes and global paths remain unchanged. New ROM
files and renamed files use ordinary Steam ROM Manager refresh.

The installed executable code is local. No code is executed from the card.
Only native_card.py sync starts this project's separate save-sync application.
The watch mode starts no emulator process.

## Boundaries

This is a SteamOS/native Ryujinx/ext4/Internal Storage preview. It does not integrate
Flatpak/portable roots, multiple MMC readers or Windows. Old custom-launcher hosts
must use their previous restore before installing. Dedicated hardware gyro services
remain managed by EmuDeck. A fresh Steam Machine hardware acceptance run is pending.
