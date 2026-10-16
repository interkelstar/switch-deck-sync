# Contributing

Run the tests on Linux using the command in README.md. Add regression coverage for
changes to profile isolation, transfer recovery, card detection or installer rollback.
Do not use real keys, firmware, games or personal saves in fixtures.

Issue reports should include OS/emulator versions, the setup stage and the displayed
error. Do not attach installed card folders or unreviewed configuration/backup archives.
Changes affecting the installer need a fresh-user hardware test before a stable release.

The `switch/` companion is derived from ftpsrv. Preserve its separate attribution and
source/build instructions. Propose generally applicable fixes upstream where possible.
