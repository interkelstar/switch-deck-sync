# First Steam Machine acceptance test

Status: ordinary-user installation and all three games/saves/controls passed on the
first Steam Machine with 0.3.1. The user then updated to 0.4.0, removed the four
old game/emulator entries, and recreated them with chosen artwork using SRM. All
four entries work. The Switch address, profiles and three games are retained in
save-sync settings. On 2026-10-17 the user ran sync in the installed 0.4.0 app:
all three games reported transfer from Ryujinx to Switch with a success checkmark.
The sync engine reads saves back after writing before reporting success. This is
user-observed UI acceptance; no SSH inspection or separate on-console save-load
check was performed on the Steam Machine test. Setup and testing used no SSH.
Gyro is a separate host/controller setup. Remaining checklist items below are
additional coverage, not claims of completed hardware tests.

1. Install EmuDeck in Custom Mode to Internal Storage with the prepared card removed.
   Select Ryujinx and Steam ROM Manager; ES-DE is optional.
2. Open and close Ryujinx from the application menu. AutoMap enabled notice is native
   EmuDeck behavior; a missing keys warning is expected on the empty host.
3. Insert the prepared card. Extract the current installer ZIP and open Install.desktop.
   Choose the optional portable library and its reader. Existing installations use
   Update save sync to keep their mode.
4. Confirm attachment. After setup completes, open Steam from its normal application
   menu icon. Check Switch Deck Sync appears and existing game shortcuts are retained.
   On a fresh host, choose games/emulators in SRM and save those to Steam.
5. Launch Zelda from Game Mode. Confirm familiar save progress and controller input.
   If AutoMap was disabled, verify the manual setting stays disabled.
6. Close the game. Open native Ryujinx from the application menu and confirm the
   same games/profile are visible. ES-DE and SRM use the normal roms/switch location.
7. Close games, run Switch Deck Sync, and check the existing Switch/profile/game
   settings are retained. Check one small save change with both sides backed up.
8. Close games/sync and eject. Return the card to Deck and verify progress carries.
9. On the Steam Machine, check another prepared card and then an ordinary Steam card.
   No USB fallback or cross-profile mapping is allowed.
10. Rerun the installer to check idempotence, then check Restore. Original host
    configuration/folders must return without changing card saves.

Also test the default sync-only choice on a host with configured Ryujinx and no
card/EmuDeck. No reader selection or card service should be required. Check local
sync settings/history, desktop/Steam entry, update and restore. Game selection,
Steam game entries and artwork are managed directly with SRM on each host.

Automated Linux checks use synthetic games, keys/firmware and launcher fixtures.
They validate data ownership and direct command routing, not hardware performance
or the correctness of EmuDeck's own controller-detection implementation.

## 0.5.1-preview portable-card fix

The metadata-refresh fix was installed on a Steam Deck and a second SteamOS host.
The Deck imported the new update/DLC metadata; the owner confirmed Smash fighters
and built-in controls on Deck. A separate filesystem repair was needed during
that session and is not a capability or claimed effect of this patch.

Synthetic regression tests reproduce a returned card with unchanged device identity,
verify external metadata is imported before stale local changes can be exported,
and check that refresh waits for a running game to exit. The normal local-export
control also passes. Fresh installation of the 0.5.1 package on physical hardware
and a complete post-repair Switch synchronization round trip have not been tested.
