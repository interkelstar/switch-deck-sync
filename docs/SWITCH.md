# Set up ftpsrv Save Sync on Switch

[Русский](#русский) · [Computer installation](INSTALL.md)

This companion is required for the current preview. It is a modified build of
[ITotalJustice/ftpsrv](https://github.com/ITotalJustice/ftpsrv), based on release
1.2.2. It exposes account saves for the desktop app to read and write over Wi-Fi.
Use a Switch where homebrew is already configured.

## Download and configure

1. Download **ftpsrv-save-sync.nro** from the release's **Assets**, or use the same
   file in the installer's **switch/** folder. Copy it to **/switch/** on your
   Switch SD card. It appears as **ftpsrv Save Sync** in the homebrew menu.
2. The configuration path is **/config/ftpsrv/config.ini** on that SD card. Back
   up an existing file before editing: standard ftpsrv builds share this path.
3. If no configuration exists, copy **ftpsrv-config.ini.example** from Assets
   (or **switch/config.ini.example** from the installer) to that path and rename
   it **config.ini**. Create the directories if needed.
4. For an existing configuration, merge these values into their named sections.
   Do not duplicate sections or replace unrelated settings:

```ini
[Login]
anon = 1

[Network]
port = 5000
timeout = 30

[Nx]
mount_devices = 1
save_writable = 1
mount_bis = 0
```

## Use it

1. Fully close the game on Switch and the emulator on the computer.
2. Start **ftpsrv Save Sync** from homebrew and leave it open.
3. Enter its displayed IPv4 and port in **Switch Deck Sync → Settings**. Both
   devices must be reachable on the same local network.
4. Choose the Switch/Ryujinx profiles and games in the desktop app, then sync.
5. After success, press **+** on Switch to exit the server before playing. After
   an interrupted transfer, keep the server open and rerun sync to recover first.

FTP is anonymous and unencrypted. Run the server only during transfers on a
trusted local network. The companion is a homebrew app, not a sysmodule.

## Source and attribution

Assets include **ftpsrv-save-sync-source.zip** and
**ftpsrv-THIRD-PARTY-NOTICES.txt**. The source ZIP contains upstream source,
modified files and build notes. The installer also includes them in **switch/**,
along with **save-write.patch** and the upstream revision identifier.

The modification corrects a save-file write type check. It also changes the
application label and disables USBHSFS/game-card features for this Wi-Fi build.
**SHA256SUMS.txt** covers the standalone NRO, source, config example and notices.

DBI and other FTP save servers are not supported by this preview. See the
[roadmap](../ROADMAP.md).

## Русский

Нужен **ftpsrv Save Sync** на Switch с уже настроенным homebrew.

1. Скачай **ftpsrv-save-sync.nro** из **Assets** или возьми тот же файл из папки
   **switch/** установочного ZIP. Скопируй в **/switch/** на карте Switch.
2. Конфигурация: **/config/ftpsrv/config.ini**. Если файл есть, сначала сохрани
   резервную копию: его использует и обычный ftpsrv.
3. Если файла нет, скопируй **ftpsrv-config.ini.example** из Assets (или
   **switch/config.ini.example** из установщика) в эту папку и переименуй в
   **config.ini**. При необходимости создай папки.
4. Для существующей конфигурации внеси значения из примера выше в соответствующие
   секции, не дублируя их и сохраняя остальные настройки.
5. Полностью закрой игры на обоих устройствах. Запусти **ftpsrv Save Sync**,
   укажи показанные IPv4 и порт в настройках приложения на компьютере, выбери
   профили и игры и запусти синхронизацию.
6. После успеха выйди из сервера кнопкой **+** перед игрой. При прерванной
   передаче сначала повтори синхронизацию для восстановления.

Сервер используй только на время обмена в доверенной локальной сети: FTP здесь
анонимный и без шифрования. Исходники, сведения об авторстве и контрольные суммы
доступны в Assets рядом с NRO.
