# Switch Deck Sync

Sync saves between your Nintendo Switch and Ryujinx over Wi-Fi.
Use it with your existing emulator setup on Steam Deck, Steam Machine or another
Linux computer. A separate memory card is optional.

![Switch Deck Sync](art/grid.png)

**Preview 0.4.0.** Installer: English and Russian. Save-sync interface: Russian.

## Install save sync

1. Close your games and Ryujinx. Download **Switch-Deck-Sync-0.4.0-preview.zip** from
   a release's **Assets** and extract the whole ZIP to Downloads.
2. In Desktop Mode, open **Install.desktop**. If KDE asks, choose **Trust / Execute**.
3. Choose your language, then **Sync saves with Switch**. Setup detects your Ryujinx
   data folder; if you use several installations, choose the one to sync.
4. Confirm setup. If you use Steam, it closes to add the Switch Deck Sync app.
5. Open Steam or the application menu and launch **Switch Deck Sync**.
6. In **Настройки**, enter the Switch address and choose the profiles and games.

On Switch, follow [Switch setup](docs/SWITCH.md) to install **ftpsrv Save Sync**.
Start it before syncing, with games closed on both devices. Press **+** to exit.
This preview uses anonymous FTP on your local network.

The sync-only option uses your existing saves wherever your configured Ryujinx
keeps them. EmuDeck and a removable card are not required. Sync settings, history
and transfer backups stay on this computer.

## How sync works

If one device has changed since the last sync, its complete save is transferred.
If both changed, you choose which version to keep. Both original versions are backed
up, and transfers are verified by reading them back. After an interrupted transfer,
run sync again to recover before opening that game on Switch.

Only account saves are supported. A game needs an existing Ryujinx account-save
container before its first import: launch it once and create a save. Cross-version
save conversion and BCAT/system/device saves are outside scope.

## Optional: carry a library between SteamOS computers

Choose **Portable library on a memory card** in the installer. This option requires
EmuDeck with native Ryujinx and Steam ROM Manager, using **Internal Storage**, and
an ext4 card. Open and close Ryujinx once before setup.

Select the reader with your card. Setup detects a prepared library automatically;
for a new card, it copies and verifies your existing library. Install this option
on each computer where you want to use the card.

Games, saves, profile, keys, firmware and sync history travel on the card. Shader
caches stay on each computer. Close games and save sync, safely eject the card, and
move it to the other computer. Any prepared card works in the selected reader. Keep
a USB reader in the same USB port. To move to a larger ext4 card, copy the complete
**Emulation** folder.

Add games, emulators or ES-DE to Steam using **Steam ROM Manager**. Switch Deck Sync
adds only its own application shortcut and keeps existing game shortcuts in place.

## Optional: carry SRM artwork

Use **Transfer SRM artwork** in the installer. You can copy an existing SRM export
to your card, or follow the displayed paths to export directly through SRM.

The card folder is **Emulation/artwork/srm-image-choices**. On another computer,
generate the app list in SRM, choose **Import image choices**, review the result,
and save the selected games to Steam. See [artwork transfer](docs/ARTWORK.md).

## Requirements and restore

The desktop installer supports Linux with Python 3.10+, KDE kdialog, SDL2/SDL2_ttf
and DejaVu Sans. Steam integration is available when a Steam profile exists. Without
Steam, launch Switch Deck Sync from the application menu. Portable libraries also
require systemd user services, lsblk and udisksctl. Windows and multiple MMC readers
are outside this preview. Use your own dumped games, keys and firmware.

Run **Install.desktop** again to update, manage artwork or **Restore the previous
settings**. Restoration retains saves, card contents and local sync history.
Installer backups are kept in `~/.local/share/switch-deck-sync/backups/`.

For a portable library, run the installer again if an EmuDeck reset changes its
data connections. To add a card to an existing sync-only installation, choose
**Set up a portable card library**. Updates keep the current installation mode.

## Русский

Основное назначение Switch Deck Sync — обмен сейвами между Switch и Ryujinx по
Wi-Fi. EmuDeck и отдельная карта для этого не нужны: достаточно настроенного Ryujinx.

Скачай установочный ZIP из Assets, распакуй в «Загрузки» и открой **Install.desktop**.
Выбери **Обмен сейвами со Switch**. После установки открой Switch Deck Sync в Steam
или меню приложений, укажи адрес Switch, выбери профили и игры. На Switch запусти
ftpsrv Save Sync; на обоих устройствах закрой игры.

**Переносимая библиотека на карте памяти** — дополнительный сценарий для нескольких
компьютеров со SteamOS. Игры, сейвы и настройки обмена путешествуют на карте.
Игровые ярлыки и оформление добавляются через SRM. Для переноса обложек используй
**Перенести обложки SRM**: мастер сохраняет штатный экспорт SRM на карту.

## Development

[Architecture](docs/ARCHITECTURE.md) · [Hardware checklist](docs/STEAM-MACHINE-TEST.md)

Run tests: `PYTHONPATH=app python3 -m unittest discover -s tests -v`.
Build archives: `python3 scripts/build_release.py`.

## Licence

Client and installer: MIT, [LICENSE](LICENSE). Modified ftpsrv: separate MIT project
by TotalJustice; attribution, revision, patch and buildable source are in switch/.
This is an independent, unofficial project.
