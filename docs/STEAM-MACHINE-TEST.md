# First Steam Machine acceptance test

Status: **not yet executed on the target machine**.

Use the built release archive exactly as a new user would. No SSH, source edits,
private Deck paths, debug ports or external agent setup should be needed. If something
fails, retain the message and fix the installer before repeating the test.

1. Install EmuDeck to Internal Storage with the prepared card removed and select a
   supported native Ryujinx build. Start and close Ryujinx once; a missing keys warning
   is expected for this empty host. Keep EmuDeck AutoMap enabled for the controller test.
2. Insert the prepared library card. Download/extract the release and open Install.desktop.
3. Choose English or Russian, the real card reader, native executable and the local
   Ryujinx data folder. Confirm attachment. Check that Steam returns with the sync
   cover, hero, logo, landscape image, icon, library shortcut and game shortcuts.
4. Launch Zelda through its Steam shortcut. Confirm familiar progress and controller
   input. Reconnect or change the controller and launch again to check native AutoMap.
   Do not assume Deck-specific gyro services are present on this host.
5. Close the game. Run Switch Deck Sync, select the Switch address/profiles/games and
   perform a comparison with the Switch companion open. First verify matching progress;
   then test one small, known save change with both sides backed up.
6. Close everything, eject the card, and return it to Deck. Verify that progress carries
   over while Deck controls remain unchanged.
7. Rerun the installer on the Steam Machine. Check that Steam IDs, settings, sync
   baseline and saves are retained. Try the restore option and verify old shortcuts.
8. Separately test preparing a fresh ext4 card from an ordinary Ryujinx setup. Check
   DLC/update paths and create one initial emulator save before selecting that game.
9. Test another prepared library in the same slot, and then an unrelated Steam card.
   The helper must not load the previous profile or silently use a USB library.

Record OS version, emulator version/distribution, selected reader type, controller,
test results and any displayed errors. Exclude keys, saves, IP addresses and account
identifiers from public issue attachments.
