# Switch Deck Sync

Portable Nintendo Switch libraries and manual Wi-Fi save synchronisation for SteamOS.

**Preview 0.2.0.** Supports native Ryujinx / Ryujinx AppImage. The setup wizard is
available in English and Russian; the controller-friendly sync interface is currently
in Russian. Steam Deck hardware was used for the earlier prototype. The unified
installer has Linux integration tests; a fresh Steam Machine installation is the next
hardware acceptance test. This is not yet a stable, broadly tested release.

![Switch Deck Sync](art/grid.png)

## Install on SteamOS

1. Install EmuDeck and a supported Ryujinx build. Start Ryujinx once, configure this
   computer's controls, and install your own dumped keys and firmware.
2. Download a release archive, extract it to a normal writable folder, and open
   **Install.desktop** in Desktop Mode. KDE may ask you to trust or execute this
   downloaded launcher. The terminal alternative is `sh install.sh` in that folder.
3. Choose the card reader, the Ryujinx executable, and its existing data folder
   containing `Config.json`. Detected paths appear in the wizard; browsing is available.
4. A prepared library is attached directly. For a fresh card, choose the game folder(s)
   and let the wizard copy and verify the profile, saves, keys, firmware and selected
   update/DLC files. Source files are retained. No formatting takes place.
5. Close games before continuing. The wizard briefly exits Steam, backs up changed
   files, adds shortcuts and artwork, and reopens Steam.

No SSH, administrator password, system packages or manual configuration edits are
required on a supported SteamOS installation. Runtime prerequisites are Python 3.10+,
KDE `kdialog`, `lsblk`, `udisksctl`, SDL2, SDL2_ttf and DejaVu Sans. Missing dependencies
are reported. The current wizard accepts ext4 cards. Flatpak emulators, other emulator
families, Windows and multiple MMC readers are not supported by this preview.

EmuDeck installation: <https://manual.emudeck.com/install-guide/1_index/>.
EmuDeck and emulator downloads are handled separately; none are bundled here.

## Set up the Switch

Copy `switch/ftpsrv-save-sync.nro` to `/switch/` on the Switch SD card. Merge the
settings from `switch/config.ini.example` into `/config/ftpsrv/config.ini`, keeping
a backup of any existing configuration. The detailed [Switch guide](docs/SWITCH.md)
describes the required settings and the supplied source patch.

Start **ftpsrv Save Sync** through homebrew. Press **+** to exit it. Keep it open only
while syncing on your local network. This preview uses anonymous, unencrypted FTP.

## First synchronisation

Close the game on both devices. In Steam, open **Switch Deck Sync**, then **Настройки**
(Settings). Enter the Switch's displayed IPv4 address and port, choose the Switch and
Ryujinx profiles, and select games. Use **Синхронизировать** (Synchronise).

Games need an existing account save on both sides. If Ryujinx has no save yet, launch
the game through **Switch Library (Ryujinx)** or its new Steam shortcut, create a save,
close the game, and refresh the selection. Automatic creation of emulator save containers
from Switch-only saves is not implemented.

The client compares complete save contents with the last common state. If one side
changed, it copies that whole save. If both changed, or different saves have no common
baseline, you choose which copy to keep. It does not infer progress from file dates or
merge individual files. Both versions are backed up before replacement, and writes are
read back and verified. Interrupted transfers retain a recovery journal. Finish recovery
before launching the affected game on Switch.

Only account saves are included. BCAT, system saves, device saves and cross-version
save conversion are outside the scope of this release. Compatibility depends on the
game and its update/DLC versions. The prototype was tested with Super Mario Odyssey,
Mario Kart 8 Deluxe and Zelda: Breath of the Wild; other games need their own verification.

## Moving between computers or cards

Each computer needs its emulator and a one-time run of this installer. Move the card,
run the installer on the new computer, and choose the existing library. Saves and sync
history stay on the card; controller settings and shader caches stay on each computer.
Once installed, switching prepared cards requires no registration.

The configured **reader/slot**, not the card UUID, selects the library. A USB reader can
be selected explicitly and is identified by its hardware connection path. Keep it in
the same port. An unrelated Steam-games card does not cause fallback to another drive.

To move to a larger card, copy the complete `Emulation` folder to a suitably formatted
card while games and sync are closed. No card UUID changes are needed. Swapping cards
while an emulator or sync is running is unsupported. Eject the card normally.

Existing standalone Ryujinx setup is retained. This installer creates a separate
managed Ryujinx configuration and Steam shortcuts. It does **not** rewrite EmuDeck's
global paths or automatically integrate every frontend. Use the installed shortcuts
for the portable library. ES-DE integration remains a separate future installer feature.
New games appear in Ryujinx's library; rerun this installer to add their individual
Steam shortcuts. Files with title IDs in their names support those shortcuts; files
without identifiable IDs remain available in Ryujinx's browser. Existing shortcuts for
the same name or recognisable Ryujinx title ID keep their Steam IDs and input settings.

## Restore and troubleshooting

Rerun the installer and choose **Restore the previous settings** to undo the last
installation. This restores changed settings and shortcuts and keeps card games/saves.
An interrupted installation is detected and offered recovery on the next run. If the
initial card copy was interrupted, repeat preparation with the same source folders;
verified staging files are reused. Original source data is never removed automatically.

Computer files: `~/.local/share/switch-deck-sync/`.
Private setup backups: `~/.local/share/switch-deck-sync/backups/`.
Card data and layout: [architecture](docs/ARCHITECTURE.md).
Hardware acceptance procedure: [Steam Machine test](docs/STEAM-MACHINE-TEST.md).

The installer's restore does not revert progress made by playing or syncing after
installation. Back up important saves separately. Do not share your installed card
or its runtime settings/backups as a clean distribution.

## Development

```sh
PYTHONPATH=app python3 -m unittest discover -s tests -v
python3 scripts/build_release.py
```

Run these commands from a source checkout, rather than the installer artifact.
Tests run on Linux with synthetic games, keys, firmware and profiles. No proprietary
assets are included. The release builder uses an allowlist, checks for private runtime
files and emits ZIP, tar.gz and SHA-256 checksums. GitHub Actions runs tests on Python
3.10 and 3.12; a `v*` tag builds a GitHub prerelease. See [publishing](docs/PUBLISHING.md).

## Русский

Установка в Desktop Mode: распакуй архив и открой **Install.desktop**. Мастер найдёт
эмулятор, предложит выбрать считыватель и подключит готовую карту либо подготовит новую
библиотеку из твоих данных Ryujinx. Оригиналы сохраняются. На время добавления ярлыков
Steam завершится и затем откроется снова. SSH и ручные правки не нужны.

На Switch установи `switch/ftpsrv-save-sync.nro` и внеси параметры из примера конфигурации.
Запусти сервер. В Steam открой **Switch Deck Sync → Настройки**, укажи адрес сервера,
выбери профили и игры. Если сейва Ryujinx пока нет, сначала создай его запуском игры.
Перед синхронизацией полностью закрывай игру на обоих устройствах.

На новом компьютере повтори установку с готовой картой. Данные и история синхронизации
поедут с картой, управление и кеши останутся локальными. Привязки к UUID карты нет.
Для отката снова открой установщик и выбери восстановление прежних настроек.

Первая версия поддерживает обычный Ryujinx и AppImage, карты ext4 и запуск через
созданные ярлыки Steam. Интеграция ES-DE, другие эмуляторы и английский интерфейс
самой синхронизации пока в планах. Мастер установки уже двуязычный.

## Licence

Client and installer: MIT, [LICENSE](LICENSE). Modified ftpsrv: separate MIT project by
TotalJustice; attribution, upstream revision, patch and buildable source are in `switch/`.
Artwork files and generation prompts are included in `art/`. This is an independent,
unofficial project. Keys, firmware, games, DLC, emulator binaries and user saves are
not distributed.
