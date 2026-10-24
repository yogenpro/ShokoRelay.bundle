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

## Maintaining upstream imports

The owner authorized daily upstream-update PRs in this fork and automatic
merge after required trusted regression checks pass. `master` is the maintained
patched branch. Read `UPSTREAM.md` before repairing a blocked update.

- Preserve the original upstream commit and fork fixes; merge current master
  into the existing PR branch. Never replace the branch or force-push repairs.
- Run `python3 -B -S scripts/check-relay.py . --python2 python2.7` and
  `python3 -B -S tests/test_upstream_sync.py`. Without Python 2.7 locally, use
  the runner's default pinned Docker grammar check.
- Do not weaken tests, alter required checks or change automation to make an
  upstream import pass. Changes to tests, scripts, workflows or these
  instructions require manual review and cannot merge automatically.
- An AI repair is source-only. Do not contact live services, read credentials,
  deploy, scan a library or modify media. The updater invokes no AI itself;
  an owner starts Codex from a PR comment when an exception needs repair.
