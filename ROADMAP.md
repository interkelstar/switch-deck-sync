# Roadmap

The current preview supports Ryujinx account saves and ftpsrv Save Sync. These
are plans, not compatibility claims or release dates.

## DBI as another Switch backend

- Reproduce the FTP save-read failure with a small, non-personal test case.
  Check directory names, profile discovery, file lengths and partial reads.
- Confirm supported reads, writes and save commit semantics. Keep backups,
  recovery journals and read-back verification for every backend.
- Confirm source availability and the contribution route. Prepare a focused
  patch/PR where possible, otherwise a reproducible report for the maintainer.
  The public [DBI repository](https://github.com/rashevskyv/dbi) exposes docs and
  the desktop backend; availability of the relevant Switch implementation must
  be confirmed before promising a code PR.
- Keep ftpsrv Save Sync supported until DBI round trips and recovery pass.
  No upstream report or PR has been submitted by this project yet.

## Other emulators

- Separate emulator-specific save discovery, profile IDs and safe import/export
  from content comparison and transfer.
- Evaluate one emulator at a time. Confirm its save layout and game-save format
  compatibility; similar folder names are not evidence of compatibility.
- Add synthetic fixtures for each adapter, idle detection and profile isolation.
  Verify import, export, conflicts, recovery and backup restoration before
  offering it in the installer.
- Keep ordinary local save sync available without a portable-card requirement.

## Upstream ftpsrv

Prepare the save-write correction as a focused contribution with a minimal
reproduction and upstream build configuration. Preserve its MIT attribution and
source. A contribution is planned, not yet submitted.

## Русский

Следующие направления — DBI как альтернативный сервер и адаптеры для других
эмуляторов. Для DBI сначала нужны воспроизведение ошибки, проверка чтения/записи
и доступности исходников; затем — узкий PR или воспроизводимый отчёт автору.
До проверки обмена и восстановления поддержанным сервером остаётся ftpsrv Save
Sync. Для нового эмулятора отдельно проверяются формат сейвов, профили и безопасный
импорт. Сроки не обещаются; обращения авторам и PR пока не отправлены.
