# Library and host boundary

The host installer creates `~/.local/share/switch-deck-sync/`. Code is installed there;
no executable code from the removable card is launched. Older libraries may still
contain a copy of the original client, which the new host ignores.

```
host/
  host.json                    # reader and local emulator paths
  card -> current mount        # updated at each guarded launch
  ryujinx/
    Config.json                # host controls, graphics and game directory
    bis -> ../card/.../bis
    system -> ../card/.../system
    mods -> ../card/.../mods
    sdcard -> ../card/.../sdcard
    games -> ../libraries/<library-id>/games
  libraries/<library-id>/games # cache and host materialised update/DLC selections
  session.lock                # held throughout emulator/sync lifetime
  backups/<install-id>/       # private installer undo journal

card/Emulation/
  switch-library.json
  roms/switch/
  storage/ryujinx/
    data/{bis,system,mods,sdcard}
    patchesAndDlc/
  tools/switch-save-sync/
    settings.json
    state.json
    backups/
    pending.json              # only while recovering a transfer
```

The manifest supports schema 1 and 2. Its relative `data_dir`, `rom_dir` and `sync_dir`
must remain inside the card. The legacy root `.switch-library.json` is readable; new
libraries use `Emulation/switch-library.json`. A content library ID namespaces local
caches; it is not an allowlist of physical cards. `card_uuid` is ignored.

`lsblk` inventories disks. MMC mode accepts one `mmcblkN` disk. Reader-path mode selects
the current disk behind an explicit `/dev/disk/by-path/` hardware connection. `udisksctl`
mounts a selected partition under normal user permissions. No fallback to another drive
occurs if the configured reader lacks a prepared library.

Ryujinx is invoked with `--root-data-dir <managed-root>`, leaving its original data root
unchanged. Controls are initially copied from this host's existing `Config.json`, with
only `game_dirs` replaced. Additional local controller profiles/mappings are copied if
available. Hardware services such as a DSU gyro server are outside this installer.

Before startup, update/DLC JSON uses manifest templates with `@CARD@/` relative paths.
Selections are exported back to portable templates on emulator exit. CPU/GPU caches
remain local. Title ID shortcuts resolve against actual files on the inserted card.
Duplicate base-game IDs are rejected during setup; unknown IDs use the emulator browser.

The sync process receives `SDS_DATA_DIR` for card-owned settings/history/backups. It runs
from locally installed code. Card settings' machine-specific Ryujinx paths are refreshed
at launch. Interrupted sync journals must be resolved on the original machine before
attaching on another host because they may reference in-flight absolute backup paths.

Setup changes to the host and Steam are journalled before replacement. Regular file
backups, journals, replacements and their directory entries are flushed before commit.
Ordinary failures trigger rollback; the next wizard run offers recovery after a process
interruption. Copies to a new card are SHA-256 verified and published with a manifest
only after all components are ready. Failed card preparation has a resumable intent
file and staging directory. It never deletes original source data or formats storage.

Steam shortcut changes happen only while Steam is stopped and are backed up. The writer
preserves supported binary VDF fields and existing shortcut IDs. Unknown VDF types or
ambiguous matches abort setup. All new shortcuts use installed wrappers, not card paths.
Artwork for the sync app is installed locally; individual game artwork is retained if
already present, but not fetched from third-party services.

The host install does not globally modify EmuDeck or ES-DE. This bounds the first
release to native Ryujinx / AppImage launched through the installed Steam/desktop
shortcuts. The earlier helper's ES-DE functions remain in source for existing host
configurations but the generic installer does not configure that frontend yet.
