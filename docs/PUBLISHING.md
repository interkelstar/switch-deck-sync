# Publishing this repository

Prepare a preview release in the existing repository before changing its visibility.
Making the repository public is a separate, explicit maintainer action. Do not assume
that preparing or testing a release authorizes that visibility change.

Before a public release:

- Run the Linux tests and release builder.
- Review recorded hardware acceptance and remaining coverage in `STEAM-MACHINE-TEST.md`.
- Check the English/Russian SDL interface smoke test and its rendered frames.
- Review the clean allowlisted archives, licensing and companion source attribution.
- Keep the installed library, runtime settings, backups, dumps and SSH material outside
  this repository. The source fixtures use fabricated data.

The CI workflow runs tests on pushes and pull requests. For a release, push a version
tag matching VERSION, such as `v0.5.1-preview`. The workflow tests both interface
languages, builds ZIP/tar.gz installers and publishes a GitHub **prerelease** with
checksums. Assets also include the standalone ftpsrv Save Sync NRO, full source ZIP,
configuration example and MIT notices. It does not build a stable release automatically.
GitHub's built-in source ZIP is not the installer artifact; users should download the
named ZIP or tar.gz from Releases and open Install.desktop after extraction.

No remote URL is hardcoded in the installer. The initial installation works offline
from an extracted release. An online bootstrap and self-update facility are intentionally
not part of this preview; updating means running a newer downloaded installer.
