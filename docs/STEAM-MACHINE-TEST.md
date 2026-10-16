# First Steam Machine acceptance test

Status: not yet completed on target hardware.

1. Install EmuDeck in Custom Mode to Internal Storage with the prepared card removed.
   Select Ryujinx and Steam ROM Manager; ES-DE is optional.
2. Open and close Ryujinx from the application menu. AutoMap enabled notice is native
   EmuDeck behavior; a missing keys warning is expected on the empty host.
3. Insert the prepared card. Extract the 0.3.1 installer ZIP and open Install.desktop.
   Choose language/reader; no SSH, source edits, paths or emulator binary selection.
4. Confirm attachment. Steam reopens with the sync artwork and direct native shortcuts.
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

Automated Linux checks use synthetic games, keys/firmware and launcher fixtures.
They validate data ownership and direct command routing, not hardware performance
or the correctness of EmuDeck's own controller-detection implementation.
