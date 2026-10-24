# Experimental SeriesID identity transport

This is a separate opt-in follow-up to the flat-folder scanner patch. It is
not a release, an upgrade instruction, or a claim of native Plex acceptance.

## Why titles are insufficient

Shoko's preferred `Name` can be shared by several distinct SeriesIDs. The
legacy scanner emits that name as Plex's grouping key; the agent then searches
by name. Root collection alone cannot distinguish these identities, and equal
search scores cannot establish which series the agent should update.

In identity mode the scanner emits:

```text
Shared title [ShokoRelay SeriesID:123]
Shared title [ShokoRelay SeriesID:456]
```

The suffix is internal transport, not the final display title. The agent
supplies titles, artwork and metadata according to its preferences, with the
strict-mode negative-season airdate exception described below. Separate
SeriesIDs can have separate GUIDs even when their display titles are equal;
correct native file associations must still be verified.

## Explicit opt-in, fail-closed matching

- Scanner: `SeriesIDIdentity=True` in its own basename-matched `.cfg`.
  An absent option or `False` retains legacy emissions.
- Agent: `RequireSeriesIDToken=True` refuses untagged titles. Its default is
  `False`, preserving untagged legacy searches when this experiment is unused.
- A canonical token always resolves directly through
  `api/v3/Series/<ID>?includeDataFrom=AniDB,TMDB`, never through title Search.
  The returned ID and nonempty text title are verified before a result is added.
- IDs must be positive, canonical decimal values within a signed 32-bit range.
  Empty, signed, zero-padded, malformed, repeated, newline-containing and
  out-of-range tokens are refused without a title fallback, even with strict
  mode disabled. Actual series titles containing the reserved marker are
  refused by the identity scanner rather than ambiguously escaped.
- An ID API failure is still a failure. It must not become a guessed title
  match or a clean empty-library result.
- Manual rematching with an untagged display title is not supported in strict
  mode. This experiment does not change the server's SeriesID assignments.

Deploying the modified agent over an existing plugin would affect every
library using that plugin. Native validation must instead use an independently
identified bundle, its own preference file, a new scanner alias/configuration,
and a fresh library. Preserve production code, credentials, ordering and
libraries. Bundle/GUID namespace changes are operational isolation, not a
migration or merge of existing library identities.

## Windows path and SDK contracts

Windows traversal uses Unicode extended paths for filesystem I/O, ordinary
paths for relative arithmetic and queue comparisons, and UTF-8 byte paths for
the legacy SDK's filtering contract. Extended filesystem names are temporary
SDK inputs: surviving files and SDK-created parts are restored to supplied
source paths before emission. This is not a source rename or a VFS layout.
Drive/UNC roots, mixed prefixes, long Unicode paths and trailing separators are
covered by portable tests, not by a complete reproduction of Windows/Plex.

## Opt-in stacking and metadata exceptions

With `SeriesIDIdentity=True`, the generic SDK stacker can compare items only
within the same `(show, season, episode, display_offset)` group. Filename
similarity or `part1`/`part2` is not permission to combine distinct Shoko
coordinates. Same-coordinate multipart behavior is retained. Disabled or
absent identity mode still calls the SDK stacker directly.

With `RequireSeriesIDToken=True`, metadata Update omits negative-season
`originally_available_at` hints. Plex's legacy importer can rematch distinct
negative-season episode numbers by a shared date and consolidate their files.
Strict mode preserves the signed coordinates instead of that ambiguous date
hint, including the Other season. Positive-season dates are unchanged. With
strict mode disabled, the existing `disableNegativeSeasonAirdates` policy,
including its Other-season exception, is unchanged.

Immediate-parent/filename suffix lookup, skipping ambiguous files, selection
of the first SeriesID for multi-series videos, AniDB/TMDB coordinates, hidden
episodes and offsets remain unchanged. Distinct episode IDs at the same
coordinates may still become media versions within one series. No catalogue
rename, source rename, VFS, watch-sync or source-writing operation is included.

These changes are not an index-repair API. Existing native media versions can
retain incorrect associations after a corrected scan. Do not promise that a
rescan or metadata refresh will split an already damaged index. Keep such an
index and its evidence until a separately authorized migration is agreed;
never remove sources, empty trash or edit the live database to hide a failure.

## Offline checks and remaining acceptance

```sh
python3 tests/test_scanner.py
python3 tests/test_agent_identity.py
python3 tests/test_windows_paths.py
python3 tests/test_stack_identity.py
python3 tests/test_negative_airdates.py
python3 tests/test_fixture_api.py
```

The real scanner and agent Search execute with fake SDK/API/configuration.
The agent loader uses one lexical shim for Python 2's `ur` string prefix and a
`basestring` shim; authentication and actual network access are forbidden.
These are Python 3.7+ standard-library tests, not Plex SDK reproduction.

Fixtures cover duplicate names, Unicode, partial callbacks, primary-series
selection, offsets, signed seasons, boundary IDs, malformed tokens, bad API
responses, outages, explicit strict mode and unchanged legacy defaults/search.
Additional stubs check Windows path contracts, identity-scoped stacking
boundaries and the real agent's airdate gate. They do not reproduce the SDK
stacking algorithm, the complete Update lifecycle, native date-based remapping,
existing-index repair or playback.

Native acceptance remains required: two same-title series must form distinct
shows with correct agent GUIDs/files, and repeat/targeted scans plus forced
metadata refresh must retain their identities and metadata. Do not accept
mock grouping, a successful HTTP request, or `refreshing=0` alone as proof.
Automatic filesystem events, playback/default-version selection and broad
catalogue correctness are separate checks. Preserve evidence; cleanup and
production adoption need independent authorization.
