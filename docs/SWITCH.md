# Switch companion

This preview uses a modified build of [ITotalJustice/ftpsrv](https://github.com/ITotalJustice/ftpsrv).
Base: release 1.2.2, revision recorded in `switch/THIRD-PARTY-NOTICES.txt`.

1. Copy `switch/ftpsrv-save-sync.nro` to `/switch/` on your Switch SD card.
2. Keep a backup of `/config/ftpsrv/config.ini`, if present.
3. Merge `switch/config.ini.example` into that configuration. Important settings are
   `anon=1`, `port=5000`, `mount_devices=1`, `save_writable=1`, `mount_bis=0`.
4. Close the game and start **ftpsrv Save Sync** through homebrew.
5. Enter its displayed IPv4 address and port in the desktop client. Both devices need
   to be on the same reachable local network. Exit the Switch server with **+** afterwards.

Existing ftpsrv configuration can affect both the original and modified builds. This
release does not silently overwrite it, change NAND partitions or install a sysmodule.
FTP in this preview is anonymous and unencrypted; the server should be open only for
the transfer on your trusted local network.

`switch/source.zip` contains the upstream source, modified files, build instructions
and required attribution. `switch/save-write.patch` isolates the save-file write type
check correction. The NRO has a custom application label and was built without USBHSFS
and game-card features for this Wi-Fi use case. Its SHA-256 is recorded by the release
builder alongside the other distributed files.

DBI's FTP save reads failed for the original test installation with an out-of-range
read. This companion is the supported backend for now. DBI support and an upstream
ftpsrv fix are future work; no compatibility with arbitrary FTP save servers is claimed.
