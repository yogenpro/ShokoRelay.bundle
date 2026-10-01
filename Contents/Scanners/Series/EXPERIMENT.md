# Flat-folder grouping experiment

This fork starts with the legacy ShokoRelay v1.2.36 scanner/agent, compatible
with Shoko Server 5.3.1+. It does not require a Shoko upgrade or the modern
Shoko metadata-provider plugin.

## First change

The upstream scanner's library-root callback already walks descendants,
collects their per-file episode records, and removes their top-level directory
from Plex's subsequent folder-callback queue. This is its existing workaround
for Plex grouping different series together by folder.

Upstream only performs that collection when a folder is nested or has child
directories. A flat, top-level folder is left for a separate native folder
callback. This experiment extends the same collection to every folder with
files, including that flat case. It changes only the root-scan orchestration;
no directories are added, renamed or deleted, and original media paths are
passed to Plex unchanged.

The change does **not** alter:

- Shoko file lookup through immediate-parent name + filename (`PathEndsWith`).
- Selection of the first SeriesID for a video linked to multiple series.
- AniDB/TMDB episode ordering, hidden episodes, or multi-episode offsets.
- Metadata-agent title search, GUID namespace or automation scripts.
- Logging/skipping behavior when the Shoko API fails or a file is ambiguous.

Multiple separate files belonging to different series in one folder are the
initial target. One video associated with several series is a separate policy
question, not solved by this patch.

## Credential-free regression checks

From a source checkout, run:

```sh
python3 tests/test_scanner.py
```

Python 3.7+ and its standard library are sufficient for the tests. The shipped
scanner retains its legacy Python 2/Plex SDK syntax. The tests execute the real
scanner with fake Plex SDK modules, Shoko 5-style API responses, configuration
and logging. Real authentication/network access is explicitly blocked. No
local `.cfg` file is read, and no Plex installation is needed.

Fixtures cover flat and nested layouts, empty and real child directories,
multiple shows, single shows, filtering, ambiguous/ignored files, API errors,
hidden/special episodes, combined episodes, primary-series selection, partial
scanner calls and pre-existing media records. Every successful scenario also
checks that its temporary regular files and directories were not modified.
The relevant root-collection cases fail against unmodified upstream.

These checks prove scanner emissions and queue handling only. The fixture
files contain synthetic bytes, not playable video. SDK filtering/stacking and
Plex's native grouping engine are **not** reproduced by the mocks.

## Native Plex acceptance still required

No successful Plex grouping result or deployment is claimed yet. Before any
production adoption, use a fresh, separately authorized synthetic test library
and actual small playable fixtures with a fixture-only Shoko API adapter.
Do not import synthetic content into a production Shoko catalogue.

Verify at least:

1. Two series in one flat folder become two distinct Plex shows after a full
   library scan, with correct episodes and unchanged source locations.
2. A repeated full scan creates no duplicate shows, episodes or media parts.
3. Targeted folder scans and filesystem-triggered rescans retain that split.
   These callbacks may bypass the root workaround; the portable partial-call
   test does not establish native incremental behavior.
4. Metadata refresh/rematching preserves the intended show identities.
5. Nested layouts and single-series folders still behave correctly.
6. API outages are failed/unknown acceptance results, never evidence of an
   empty healthy library. Protect existing metadata from automatic trash
   emptying while testing failure behavior.
7. Duplicate titles, repeated `SPs` + filename suffixes, and multi-series
   videos remain explicit follow-up cases rather than silent guesses.

Retain backups and test evidence. Do not write, move, rename, repair or delete
original media, change download paths, or deploy/clean up live libraries as
part of running these tests. A scanner-only success must survive both full and
incremental scans before it can be considered a clean fix.
