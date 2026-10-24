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

Configuration and log filenames now follow the scanner's own basename. The
original `Shoko Relay Scanner.py` still uses its original `.cfg` and `.log`
names, while separately named experimental scanners cannot accidentally read
production credentials or share its log. This supports side-by-side testing.

The grouping change does **not** alter:

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
python3 tests/test_fixture_api.py
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

## Native Plex results — synthetic scanner-only test

A controlled native Plex comparison used two distinct, playable synthetic
videos in one flat folder, a loopback-only Shoko 5-style fixture API, separate
scanner names/configurations, and the **Personal Media Shows** agent. No live
catalogue or source media was used.

| Scenario | Result |
| --- | --- |
| Baseline with upstream grouping guard | One show/episode containing both files as media versions: failure reproduced. |
| Candidate full scan | Two distinct shows/episodes, each pointing only to its intended file. |
| Repeated full scan | Same show/episode identities; no duplicates. |
| Targeted scan of unchanged folder | Split and identities preserved. |
| Start with series A, append series B, targeted scan | A retained its identity; B became a distinct new show/episode. Native logs confirmed a non-root callback. |
| Metadata refresh using Personal Media Shows | Split and identities preserved. |

This is evidence for the **scanner grouping fix**, not a production deployment
or end-to-end ShokoRelay metadata-agent acceptance. Automatic filesystem-event
rescans were not exercised. Duplicate-title matching, ambiguous suffixes,
multiple-series videos, the real Shoko metadata agent, and native nested-layout
controls remain follow-up work.

The generic manual adapter is `tests/fixture_api.py`. It binds only loopback,
uses a synthetic identity and fixed fixture mappings, and never reads a media
inventory or contacts Shoko. It covers scanner endpoints only, **not** the
metadata agent. Do not point production clients at it.

## Opt-in SeriesID identity follow-up

A separate [SeriesID identity experiment](IDENTITY.md) now addresses identical
scanner titles. It adds an explicit ID token only when `SeriesIDIdentity=True`,
and resolves that token directly in the metadata agent. Legacy defaults stay
unchanged; this is not a deployment or native acceptance claim.

Run `python3 tests/test_agent_identity.py`, `tests/test_windows_paths.py`,
`tests/test_stack_identity.py` and `tests/test_negative_airdates.py` in addition
to the two scanner/API suites. Real credentials/network remain blocked.
Suffix lookup, primary-series selection and episode ordering remain unchanged.
Identity mode now confines SDK stacking to one signed coordinate/offset, and
strict agent mode suppresses negative-season date hints that can trigger native
consolidation. See `IDENTITY.md` for those exceptions, Windows path contracts,
legacy-default behavior and existing-index limitations. This is not permission
to deploy, rebuild or clean up a live library.

## Remaining native acceptance

Before production adoption, continue with fresh, separately authorized synthetic
test libraries and actual small playable fixtures. Do not import synthetic
content into a production Shoko catalogue.

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
