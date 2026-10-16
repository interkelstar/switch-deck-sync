# Changes

## 0.3.0-preview

- Attach portable card data to the original EmuDeck/Ryujinx paths.
- Direct stock EmuDeck launchers for all game/emulator shortcuts.
- No custom emulator launcher, alternate root or AutoMap hook.
- Background user service for reader-based data links only.
- Preserve all controller/graphics settings and back up original data directories.
- Automatic path discovery and graphical restore.
- Fresh Steam Machine hardware acceptance remains pending.

## 0.2.1-preview — withdrawn

- Experimental AutoMap bridge was reverted because native EmuDeck must own startup.
- Do not install this version.

## 0.2.0-preview

- One Desktop Mode setup wizard for an existing card or a new portable library.
- English/Russian installer, automatic emulator/data discovery and explicit reader choice.
- Separate host Ryujinx configuration, local executable code and per-library caches.
- Card-owned saves, profile, keys, firmware, update/DLC paths and sync history.
- Steam shortcuts and sync artwork, preserving matching shortcut IDs.
- Verified copies, resumable card preparation, host rollback and a graphical restore option.
- Clean reproducible release archives, Linux tests and GitHub prerelease workflows.

The Steam Machine hardware acceptance test is pending. Other emulator families,
Flatpak distribution, generic ES-DE setup and client English translation remain future work.

## 0.1.0-preview

- Manual whole-save Wi-Fi sync with conflict selection and backups.
- Game Mode SDL interface and profile/game discovery.
- Modified ftpsrv companion with a save write correction.
