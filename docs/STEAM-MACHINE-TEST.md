# First Steam Machine acceptance test

Status: ordinary-user installation and all three games/saves/controls passed on the
first Steam Machine with 0.3.1. Its Wi-Fi sync check and 0.4 installer acceptance
remain pending. Gyro is a separate host/controller setup.

1. Install EmuDeck in Custom Mode to Internal Storage with the prepared card removed.
   Select Ryujinx and Steam ROM Manager; ES-DE is optional.
2. Open and close Ryujinx from the application menu. AutoMap enabled notice is native
   EmuDeck behavior; a missing keys warning is expected on the empty host.
3. Insert the prepared card. Extract the 0.4.0 installer ZIP and open Install.desktop.
   Choose the optional portable library and its reader. Existing installations use
   Update current installation to keep their mode.
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
sync settings/history, desktop/Steam entry, update and restore. For artwork, export
with SRM, save the complete native export on the card and import it in SRM on the
other host; review matched artwork before saving.

Automated Linux checks use synthetic games, keys/firmware and launcher fixtures.
They validate data ownership and direct command routing, not hardware performance
or the correctness of EmuDeck's own controller-detection implementation.
