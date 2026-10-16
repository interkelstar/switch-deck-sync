# Switch Deck Sync

Portable Nintendo Switch card data and manual Wi-Fi save synchronisation for SteamOS.

**Preview 0.3.1.** Games launch directly through the existing EmuDeck Ryujinx launcher.
This application does not launch the emulator, call AutoMap, replace controller
settings, patch the EmuDeck backend, or add a root-data argument to game shortcuts.
The setup wizard is English/Russian; the save-sync interface is currently Russian.

![Switch Deck Sync](art/grid.png)

## Install on a new SteamOS computer

1. With the prepared card removed, install EmuDeck using **Custom Mode**, **Internal
   Storage**, **Ryujinx**, and **Steam ROM Manager**. ES-DE is optional. The internal
   Emulation folder is a stable host entry point; actual Switch content stays on the card.
2. Open and close Ryujinx once using the application menu. For an existing prepared
   card, a missing prod.keys warning at this empty first launch is expected. The card
   already contains its dumped keys, installed firmware and profile.
3. Insert the card. Download the named installer ZIP from a release's **Assets**,
   extract it to a writable folder, and open **Install.desktop** in Desktop Mode.
   KDE may ask you to trust or execute the downloaded launcher. Terminal alternative:
   run sh install.sh from the extracted folder.
4. Choose English or Russian and the card reader. EmuDeck's standard paths are
   detected automatically. A prepared card is attached directly. On a fresh ext4 card
   the wizard can copy and verify your existing Ryujinx data and game folders;
   prepare that original emulator with your own keys and firmware first.
5. Close games and allow the wizard to briefly exit Steam. It backs up the affected
   host folders, attaches card data, installs the separate save-sync app and creates
   shortcuts pointing straight to the stock EmuDeck launcher. Steam reopens.
6. Launch a game normally in Game Mode. AutoMap, manual controls, graphics and launch
   fixes remain under EmuDeck/Ryujinx control. If AutoMap was disabled, it stays disabled.

No SSH, administrator password, system package installation or manual path editing is
needed on a supported SteamOS installation. This version requires the base EmuDeck
library on Internal Storage, native EmuDeck Ryujinx, an ext4 card, Python 3.10+, KDE
kdialog, systemd user services, lsblk, udisksctl, SDL2/SDL2_ttf and DejaVu Sans.
Flatpak Ryujinx, portable emulator roots, Windows and multiple MMC readers are outside
this preview. Missing prerequisites stop setup with a message.

## What is installed

EmuDeck's launcher files and backend are unchanged. The existing Ryujinx Config.json
retains every setting except its game-directory list, which is set to EmuDeck's normal
roms/switch location. Existing saves/profile folders are kept in installer backups.

A small **user data service** connects the selected reader to these ordinary paths.
It only manages data links and portable update/DLC metadata. It never starts an
emulator or runs controller/graphics configuration. Steam ROM Manager and ES-DE can
see the same roms/switch directory. EmuDeck's standard patchesAndDlc folder is linked to the card
as well, so new update/DLC selections can remain portable. New titles or renamed ROM files can be added or
refreshed through Steam ROM Manager as usual.

The reader, not a particular card UUID, selects the library. Any prepared card can be
used in that reader. A USB reader is associated with its hardware connection; keep it
in the same USB port. If the slot contains an ordinary Steam card, the service does
not fall back to a Switch card in another reader.

Saves, profile, keys, firmware and sync history stay on the card. Controller settings
and shader caches stay on each computer. Cache folders are separate for different
library identities. Copying the complete Emulation folder to a larger ext4 card is
enough; no UUID registration is required.

Close Ryujinx and save sync before ejecting or changing cards. The service refuses to
attach a different profile while either is running. Without a prepared card the data
links cannot create a substitute local save library. Physical removal during writes
is unsupported. A controller or resolution issue remains a normal EmuDeck/Ryujinx
setting; this service does not repair it.

## Set up the physical Switch

Copy switch/ftpsrv-save-sync.nro to /switch/ on the Switch SD card. Merge the supplied
switch/config.ini.example settings into /config/ftpsrv/config.ini, preserving a backup.
See [Switch setup](docs/SWITCH.md) for the required settings, source and patch.

Start **ftpsrv Save Sync** through homebrew. Press **+** to exit. This preview uses
anonymous, unencrypted FTP on your local network.

In Steam, open **Switch Deck Sync → Настройки**. Enter the Switch address and port,
choose both profiles and the games, then synchronise with games closed on both sides.
On an already prepared card these settings and sync history are retained.

Whole-save contents are compared against the last common state. If only one side
changed, that complete save is copied. If both changed, or no common baseline exists,
you choose which version to keep. File timestamps do not decide progress. Both
versions are backed up and writes are read back and verified. Interrupted transfers
retain a recovery journal: repeat sync to recover before launching that Switch game.

Only account saves are included. BCAT/system/device saves and cross-version conversion
are outside scope. Games need an existing Ryujinx account-save container before a
first import; automatic creation of those containers is not implemented. Tested
prototype titles were Super Mario Odyssey, Mario Kart 8 Deluxe and Zelda: Breath of
the Wild; other games require their own compatibility check.

## Restore and maintenance

Rerun Install.desktop and choose **Restore the previous settings**. Games on the card
are retained; original host data directories, settings and Steam shortcuts are restored.
An interrupted installation is detected and offers recovery before retrying.

Host files: ~/.local/share/switch-deck-sync/
User service: switch-deck-sync-card.service
Backups: ~/.local/share/switch-deck-sync/backups/

An EmuDeck reset/update may recreate its data links. The service detects a changed
connection and stops attaching card data instead of overriding EmuDeck. Close games
and rerun this installer to reconnect. Your card and original host data are retained.

The early schema-2 slot-library Deck prototype is recognised automatically. Setup
recovers the retained original Ryujinx startup script, preserves warm caches and
Steam shortcut IDs, repairs stale library paths in EmuDeck/SRM/ES-DE, and retires
the old helper into its rollback backup. Controller and graphics preferences are
retained. Migration stops if the original startup script is missing or ambiguous.
The independently installed 0.2.x previews must still be restored using their
original installer first; they use a different managed emulator-root layout.

The 0.2.1 preview was withdrawn because its AutoMap bridge did not meet this
architecture. Do not use it for installation.

## Validation and development

Linux integration tests cover native shortcuts, preservation of AutoMap/manual
settings, directory backups/rollback, prepared-card attachment, reader/card changes,
missing cards, data-service restart, profile/cache separation and save transfer.
A fresh Steam Machine hardware acceptance run is still pending.
The schema-2 migration is covered by synthetic success, repeat-install and rollback
tests. Physical Deck game, gyro and Wi-Fi acceptance are recorded separately.

PYTHONPATH=app python3 -m unittest discover -s tests -v
python3 scripts/build_release.py

The release builder uses an allowlist and reproducible ZIP/tar.gz archives. Keys,
firmware, games, emulator binaries and personal saves/settings are not distributed.

## Русский

На новом компьютере сначала установи EmuDeck с выбором Internal Storage, Ryujinx и
Steam ROM Manager, без вставленной подготовленной карты. Один раз открой и закрой
Ryujinx; отсутствие ключей при первом пустом запуске ожидаемо. Вставь карту,
скачай установочный ZIP из Assets, распакуй и открой Install.desktop.

Мастер сам найдёт пути EmuDeck. Выбери считыватель и подтверди подключение готовой
карты. SSH, ручные команды и копирование папок не нужны. Прежние папки компьютера
сохранятся для восстановления. Игры будут запускаться напрямую штатным способом
EmuDeck; AutoMap, ручные настройки управления и графики останутся у EmuDeck/Ryujinx.

Фоновая служба отвечает только за подключение данных сменной карты. Сейвы и профиль
живут на карте, настройки управления и кеши — на компьютере. Перед извлечением карты
закрывай игры и синхронизацию. Для добавления новых игр используй обычный Steam ROM
Manager. Восстановление прежней настройки доступно через повторный запуск мастера.

Для обмена с настоящим Switch открой Switch Deck Sync, укажи адрес ftpsrv Save Sync,
выбери профили и игры. Настройки и история синхронизации готовой карты сохраняются.

## Licence

Client and installer: MIT, [LICENSE](LICENSE). Modified ftpsrv: separate MIT project
by TotalJustice; attribution, revision, patch and buildable source are in switch/.
This is an independent, unofficial project.
