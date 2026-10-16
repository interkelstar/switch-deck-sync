# Switch Deck Sync

Keep your Switch games and saves on a memory card. Use that card on your Steam Deck
or another SteamOS computer, and exchange saves with your Switch over Wi-Fi.

![Switch Deck Sync](art/grid.png)

**Preview 0.3.2.** The installer is available in English and Russian. The save-sync
interface is currently Russian. Steam Machine hardware testing is in progress.

## Install

You need EmuDeck with native Ryujinx and Steam ROM Manager, using **Internal Storage**.
Open and close Ryujinx once before installing. Use your own dumped games, keys and
firmware; these are not included in this project.

1. In Desktop Mode, connect your ext4 memory card. Close your games, Ryujinx and
   Switch Deck Sync.
2. Download **Switch-Deck-Sync-0.3.2-preview.zip** from a release's **Assets**. Extract
   the whole archive to an internal folder such as Downloads.
3. Open **Install.desktop**. If KDE asks, choose **Trust / Execute**.
4. Choose your language and the reader holding your card. A prepared card is detected
   automatically. For a new card, the wizard copies and checks your existing library.
5. Review the card and game count, then confirm. Steam closes while setup adds your games.
6. When setup finishes, open Steam from the application menu. Launch a game in Game Mode
   or open **Switch Deck Sync**.

You can also start the installer with `sh install.sh` from its extracted folder.

Setup requires SteamOS/Linux, native EmuDeck Ryujinx, an ext4 card and a completed
EmuDeck installation on internal storage. Flatpak Ryujinx, portable emulator roots,
Windows and multiple MMC readers are outside this preview. The wizard checks for
Python 3.10+, KDE kdialog, systemd user services, lsblk, udisksctl, SDL2/SDL2_ttf and
DejaVu Sans.

## Move your library between computers

Install Switch Deck Sync on each computer and select its card reader. Close your
games and save sync, safely eject the card, and move it to the other computer.

Games, saves, profile, keys, firmware and sync history travel on the card. Shader
caches stay on each computer. Any prepared card works in the selected reader. A USB
reader uses its hardware connection, so keep it in the same USB port.

To move to a larger ext4 card, copy the complete **Emulation** folder. Add new games
to Steam using Steam ROM Manager.

## Sync with your Switch

Follow [Switch setup](docs/SWITCH.md) to install **ftpsrv Save Sync**. Start it through
homebrew; press **+** to exit. This preview uses anonymous FTP on your local network.

Close games on both devices. Open **Switch Deck Sync → Настройки**, enter your Switch
address and port, and select the profiles and games. On a prepared card, these settings
are already saved. Choose **Синхронизировать** to compare and transfer saves.

If one device has changed since the last sync, its complete save is transferred. If
both changed, you choose which version to keep. Both original versions are backed up,
and each transfer is verified by reading it back. After an interrupted transfer, run
sync again to recover before opening that game on Switch.

Only account saves are supported. A game needs an existing Ryujinx account-save
container before its first import: launch it once and create a save. Cross-version
save conversion and BCAT/system/device saves are outside scope. Super Mario Odyssey,
Mario Kart 8 Deluxe and Zelda: Breath of the Wild have been tested on Deck; other
games need their own compatibility check.

## Restore

Run **Install.desktop** again and choose **Restore the previous settings**. The card's
games and saves are retained. Installer backups are kept under
`~/.local/share/switch-deck-sync/backups/`.

If EmuDeck reports a changed connection after an update or reset, close games and run
this installer again to reconnect your card.

## Русский

Храни игры Switch и сейвы на карте памяти, переставляй её между Steam Deck и другими
компьютерами со SteamOS и обменивайся сейвами со Switch по Wi-Fi.

Установи EmuDeck с выбором Internal Storage, Ryujinx и Steam ROM Manager. Один раз
открой и закрой Ryujinx. Подключи карту, скачай установочный ZIP из Assets,
распакуй целиком во внутреннюю папку «Загрузки» и открой **Install.desktop**.

Выбери язык и считыватель. Мастер распознает готовую карту; для новой предложит
скопировать библиотеку. Проверь карту и количество игр, затем подтверди установку.
Steam закроется для добавления игр. После завершения открой его обычным значком
в меню приложений.

Перед перестановкой карты закрывай игры и синхронизацию, затем безопасно извлекай
карту. Настройки и история обмена сейвами хранятся вместе с библиотекой на карте.
На Switch запусти ftpsrv Save Sync, а в Steam — **Switch Deck Sync**.

## Development

[Architecture and migration details](docs/ARCHITECTURE.md) ·
[Hardware test checklist](docs/STEAM-MACHINE-TEST.md)

Run tests with `PYTHONPATH=app python3 -m unittest discover -s tests -v`.
Build the reproducible release archives with `python3 scripts/build_release.py`.

## Licence

Client and installer: MIT, [LICENSE](LICENSE). Modified ftpsrv: separate MIT project
by TotalJustice; attribution, revision, patch and buildable source are in switch/.
This is an independent, unofficial project.
