# Working on this fork

Experimental legacy ShokoRelay scanner/agent fork for Shoko Server 5.
Upstream is `natyusha/ShokoRelay.bundle`; this fork is `yogenpro/ShokoRelay.bundle`.
Read `Contents/Scanners/Series/EXPERIMENT.md` before changing scan behavior.

- Work on a feature branch, not `master`. Explicitly target this checkout for
  every write or Git mutation; other repositories may be active concurrently.
- This is a public code-only repository. Never add real host inventory, media
  paths, torrent information, credentials, copied runtime configuration,
  application databases, or private operational evidence. Examples and fixture
  API responses must be synthetic. Keep host-specific operations elsewhere.
- Do not deploy to Plex/Shoko, upgrade services, scan live libraries, or modify
  source media without separate explicit authorization. The default is local,
  credential-free development only.
- The runtime scanner uses legacy Python 2 and Plex SDK modules. Preserve that
  compatibility; Python 3 is used only by the standalone offline test harness.
- Run `python3 tests/test_scanner.py` and `git diff --check` after changes.
  Tests use the standard library, fake SDK/API/config/logging and ordinary
  temporary files. They must not read real credentials or contact services.
- Portable scanner tests do not establish Plex's native grouping, metadata
  matching or incremental-rescan behavior. State that limit in reports.
- Keep the initial change narrow. FileID-based resolution, SeriesID-based
  matching and multi-series-video policy are separate follow-up decisions.
- Preserve upstream notices. Do not invent a licence or publish releases as
  production-ready without resolving licensing and native acceptance first.
- Any PR must explicitly target this fork unless the owner requests an upstream
  contribution. Inherited upstream release workflows are not a test/deployment
  plan; do not publish tags/releases or enable write-capable automation casually.
