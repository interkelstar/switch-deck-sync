# Changes

## 0.5.0-preview

- English/Russian app screens, transfer results, recovery and error messages.
- Host-local language preference, set during installation and editable in Settings.
- Separate English/Russian install guides and Switch configuration instructions.
- Standalone ftpsrv Save Sync NRO, source, config and licence Assets with checksums.
- SDL interface navigation smoke tests in both languages under Xvfb.

## 0.4.1-preview

- Save sync is the default installation; a portable card is optional.
- Game entries and artwork are managed directly through SRM on each host.
- Removed the app's SRM artwork-export feature.
- Ordinary-user Steam Machine installation, SRM entries and three-game transfer
  to Switch accepted without SSH; see the hardware validation notes.


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

Historical 0.2 preview limitations are recorded above. Current support and planned
adapters are described in README.md and ROADMAP.md.

## 0.1.0-preview

- Manual whole-save Wi-Fi sync with conflict selection and backups.
- Game Mode SDL interface and profile/game discovery.
- Modified ftpsrv companion with a save write correction.
