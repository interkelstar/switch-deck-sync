# Publishing this repository

The local repository is ready for review. A remote repository and public release are
separate steps. Choose a GitHub owner and repository visibility before publishing.
Recommended repository name: `switch-deck-sync`.

Before a public release:

- Run the Linux tests and release builder.
- Complete the fresh Steam Machine acceptance test in `STEAM-MACHINE-TEST.md`.
- Review the clean allowlisted archives, licensing and companion source attribution.
- Keep the installed library, runtime settings, backups, dumps and SSH material outside
  this repository. The source fixtures use fabricated data.

The CI workflow runs tests on pushes and pull requests. For a release, push a version
tag such as `v0.3.0-preview`; the release workflow builds both archives and publishes a
GitHub **prerelease** with checksums. It does not build a stable release automatically.
GitHub's built-in source ZIP is not the installer artifact; users should download the
named ZIP or tar.gz from Releases and open Install.desktop after extraction.

No remote URL is hardcoded in the installer. The initial installation works offline
from an extracted release. An online bootstrap and self-update facility are intentionally
not part of this preview; updating means running a newer downloaded installer.
