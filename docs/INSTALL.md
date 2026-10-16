# Install Switch Deck Sync

[Русская инструкция](INSTALL.ru.md) · [README](../README.md)

## Before you start

Use Desktop Mode on SteamOS or another Linux desktop with KDE. Configure Ryujinx
and create an account save in each game you want to sync. Normal sync works with
internal storage or your existing Ryujinx data folder on a card; EmuDeck is optional.

Dependencies: Python 3.10+, kdialog, SDL2, SDL2_ttf and DejaVu Sans. The installer
checks them. Sign into Steam once for its library shortcut. Without a Steam
profile, the application-menu entry is still installed.

## Install on your computer

1. Download **Switch-Deck-Sync-0.5.0-preview.zip** from the release's **Assets**.
   Extract the whole ZIP to an internal folder such as **Downloads**.
2. Close games, Ryujinx and any running copy of Switch Deck Sync.
3. Open **Install.desktop** in the extracted folder. If KDE asks, choose
   **Trust / Execute**. Keep all extracted files together during setup.
4. Choose **English** or **Русский**, then **Sync saves with Switch**.
5. Select the detected Ryujinx data folder. If you use several installations,
   choose the one you play with. When browsing, select the folder containing
   **Config.json** and **bis/user/save**.
6. Confirm. Steam closes while its app entry is updated. After setup, open Steam
   from its normal application-menu icon.
7. Launch **Switch Deck Sync** in Steam (including Game Mode) or the application
   menu. After successful installation, the extracted download is no longer needed.

## Connect your Switch

1. Follow [Switch setup](SWITCH.md) to install **ftpsrv Save Sync**. Close the game
   completely and leave the server open.
2. Connect both devices to the same reachable local network. Guest Wi-Fi or client
   isolation may prevent them from reaching each other.
3. Open **Settings → Switch address**. Enter the displayed IPv4 and port, such as
   **192.168.1.50:5000**. Update this field if the Switch address changes.
4. Choose **Switch profile**, **Ryujinx profile**, then **Games**. Select games and
   press **Apply**. A game without a Ryujinx save is shown but cannot be selected
   yet: start that game in Ryujinx and create its save first.
5. Return home and press **Sync saves**. Keep games closed and the server open
   until the result appears.

The first run may ask you to choose **Use Switch save**, **Use Ryujinx save** or
**Skip**. Choose the progress you want; dates do not decide which save is newer.
Both originals are backed up. Later runs compare content with the last shared state.

After success, exit ftpsrv with **+** before playing on Switch. If a transfer fails,
follow the recovery message and run sync again. Do not start the affected Switch
game while recovery is pending.

Controls: **A** selects, **B** goes back, D-pad navigates. Mouse and keyboard also
work. **Steam + X** opens the Steam keyboard. Change the language under
**Settings → Language**; it is saved on this computer.

## Optional portable card

This option shares a card's saves, profile and sync history across SteamOS hosts.
It also carries the games, firmware, keys and data that the shared Ryujinx profile
needs. Emulator executables, graphics/controller settings and shader caches stay local.

1. Install native **Ryujinx** through **EmuDeck**, choosing **Internal Storage**.
   Open and close Ryujinx once. Do this on each new host.
2. Connect an **ext4** card formatted through SteamOS. This installer never formats
   a card. Use a built-in reader or a USB reader with a stable hardware path; keep
   a USB reader in the same USB port. Multiple MMC readers are outside this preview.
3. Run **Install.desktop → Portable library on a memory card**. From an existing
   sync-only installation, choose **Set up a portable card library**.
4. Select the reader and partition. For a new library, choose source game folders
   and review the copy operation. Copies are verified and originals are retained.
   For a prepared card, review the detected library and confirm.
5. On another host, connect the prepared card and repeat the optional portable
   setup. The card's saves and sync settings will be used.
6. Choose game/emulator entries and artwork through **Steam ROM Manager** on each host.

The prepared library is under **Emulation** on the card. Attachment selects a reader,
not a card UUID: another prepared card can use the same reader. To move to a larger
ext4 card, copy the **complete Emulation folder** with games/sync closed. Keep one
prepared library partition in the reader.

Before moving a card, close Ryujinx and sync and safely eject it in SteamOS. Wait
for attachment on the next host before playing. If an EmuDeck reset changes the
data connections, rerun this installer with the prepared card.

## Backups and restore

The app is installed under **~/.local/share/switch-deck-sync/**.

| Data | Sync-only setup | Portable-card setup |
| --- | --- | --- |
| Settings, state, results and transfer backups | `~/.local/share/switch-deck-sync/data/` | Card: `Emulation/tools/switch-save-sync/` |
| Language preference | `~/.local/share/switch-deck-sync/preferences.json` | Same host-local file |
| Installer rollback backups | `~/.local/share/switch-deck-sync/backups/` | Same host-local folder |

The sync data folder contains **backups/**, **last-result.json** and, after an
interrupted transfer, **pending.json**. Keep these: sync uses them for recovery.
Backups consume space over time.

**Install.desktop → Restore the previous settings** undoes the last installer
transaction, restoring host configuration and shortcut state. Saves, card contents
and sync history are retained. For a failed save transfer, use sync recovery first;
installer restore is a separate action.

## Update

Extract a newer named installer ZIP, close games and the app, then run
**Install.desktop → Update save sync**. Storage mode, profiles, game selection and
sync history are retained. The installer language also sets the app language on
this computer; change it again in Settings if needed.
