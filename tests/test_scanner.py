#!/usr/bin/env python3
"""Offline tests of the real legacy scanner, not Plex's native grouping engine.

Plex SDK modules, configuration, logging and HTTP are replaced with fixtures.
Only ordinary directories/files inside a TemporaryDirectory are created.
The fixture bytes are not playable videos; these are not Plex integration tests.
"""

import os
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote


SCANNER = Path(__file__).resolve().parents[1] / "Contents/Scanners/Series/Shoko Relay Scanner.py"
CHECKS = 0


def check(condition, message):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(message)


class ForbiddenIO(BaseException):
    """Cannot be swallowed by the scanner's catch-and-continue error handler."""


def forbidden_io(*args, **kwargs):
    raise ForbiddenIO("real credentials/network access is forbidden in offline tests")


class Logger:
    def __init__(self):
        self.errors = []
        self.handlers = []

    def addHandler(self, handler):
        self.handlers.append(handler)

    def error(self, message):
        self.errors.append(message)

    def info(self, *args):
        pass

    debug = info
    setLevel = info


class Handler:
    def __init__(self, path, *args, **kwargs):
        self.path = path

    def setFormatter(self, *args):
        pass

    setLevel = setFormatter


class Config:
    def __init__(self):
        self.paths = []
        self.identity = None

    def read(self, path):
        self.paths.append(path)
        return []  # Do not open a real .cfg file, even if one exists locally.

    get = staticmethod(forbidden_io)

    def has_option(self, section, key):
        if (section, key) != ("Prefs", "SeriesIDIdentity"):
            raise AssertionError("unexpected optional configuration lookup")
        return self.identity is not None

    def getboolean(self, section, key):
        if (section, key) == ("Prefs", "SingleSeasonOrdering"):
            return True
        if (section, key) == ("Prefs", "SeriesIDIdentity") and self.identity is not None:
            return self.identity
        raise AssertionError("unexpected configuration lookup")


class Episode:
    def __init__(self, show, season, episode):
        self.show = show
        self.season = season
        self.episode = episode
        self.parts = []
        self.display_offset = 0


def load_scanner(source=SCANNER, identity=None):
    """Load unchanged scanner syntax with a Python 3 shim for its Python 2 SDK."""
    log, stack_calls = Logger(), []
    modules = {name: types.ModuleType(name) for name in (
        "urllib", "urllib2", "ConfigParser", "Media", "Stack", "VideoFiles",
        "logging", "logging.handlers",
    )}
    modules["urllib"].quote = quote
    modules["urllib2"].Request = forbidden_io
    modules["urllib2"].urlopen = forbidden_io
    modules["ConfigParser"].RawConfigParser = Config
    modules["Media"].Episode = Episode
    modules["Stack"].Scan = lambda path, files, media, dirs: stack_calls.append(path)

    def video_scan(path, files, media, dirs, root):
        # Model only SDK video-extension filtering, not probing or grouping.
        files[:] = [f for f in files if Path(f).suffix.lower() in (".mkv", ".mp4")]

    modules["VideoFiles"].Scan = video_scan
    modules["logging"].getLogger = lambda name: log
    modules["logging"].DEBUG = 10
    modules["logging"].Formatter = lambda fmt: fmt
    modules["logging"].handlers = modules["logging.handlers"]
    modules["logging.handlers"].RotatingFileHandler = Handler

    absent = object()
    previous = {name: sys.modules.get(name, absent) for name in modules}
    scanner = types.ModuleType("scanner_under_test")
    scanner.__file__ = str(source)
    scanner.Platform = types.SimpleNamespace(OS="Linux")
    try:
        sys.modules.update(modules)
        # exec/compile avoids generating __pycache__ in the shipped bundle.
        exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), scanner.__dict__)
    finally:
        for name, module in previous.items():
            if module is absent:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    scanner.cfg.identity = identity
    check(scanner.cfg.paths == [str(source.with_suffix(".cfg"))], "configuration basename differs")
    check(Path(log.handlers[0].path).name == source.stem + ".log", "log basename differs")
    return scanner, log, stack_calls


def run_alias():
    with TemporaryDirectory(prefix="relay-alias-test-") as temp:
        alias = Path(temp) / "Relay Isolated Experiment.py"
        alias.write_text(SCANNER.read_text(encoding="utf-8"), encoding="utf-8")
        load_scanner(alias)
        check(not alias.with_suffix(".cfg").exists(), "real alias configuration was created")


@dataclass
class Case:
    name: str
    files: dict
    expected: tuple
    dirs: tuple = ()
    remaining: tuple = ()
    errors: tuple = ()
    ambiguous: bool = False
    unavailable: bool = False
    hidden: tuple = ()
    partial: bool = False
    existing: bool = False
    episode_types: dict = field(default_factory=dict)
    identity: object = None
    series_names: dict = field(default_factory=dict)
    trailing_root: bool = False
    trailing_queue: bool = False


def result(show, episode, path, season=1, offset=0):
    return (show, season, episode, (path,), offset)


def snapshot(root):
    entries = []
    for path in sorted(root.rglob("*")):
        stat = path.stat()
        entries.append((path.relative_to(root).as_posix(), path.is_dir(),
                        stat.st_mode, stat.st_mtime_ns,
                        None if path.is_dir() else path.read_bytes()))
    return entries


def run_case(case):
    scanner, log, stack_calls = load_scanner(identity=case.identity)
    with TemporaryDirectory(prefix="relay-scanner-test-") as temp:
        root = Path(temp) / "library"
        root.mkdir()
        for directory in case.dirs:
            (root / directory).mkdir(parents=True, exist_ok=True)
        records = {}
        for relative, relations in case.files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic scanner fixture, not playable media")
            suffix = os.path.join(path.parent.name, path.name)
            record = {"SeriesIDs": [
                {"SeriesID": {"ID": sid}, "EpisodeIDs": [{"ID": eid} for eid in eids]}
                for sid, eids in relations
            ]}
            records.setdefault(suffix, []).append(record)
        before = snapshot(root)
        requests = []

        def http(url):
            requests.append(url)
            if case.unavailable:
                raise RuntimeError("fixture API unavailable")
            endpoint = url.split("?", 1)[0]
            prefix = "api/v3/File/PathEndsWith/"
            if endpoint.startswith(prefix):
                found = records[unquote(endpoint[len(prefix):])]
                return found * 2 if case.ambiguous else found
            if endpoint.startswith("api/v3/Series/"):
                sid = int(endpoint.rsplit("/", 1)[1])
                title = case.series_names[sid] if sid in case.series_names else "Series " + chr(64 + sid)
                return {"Name": title,
                        "TMDB": {"Shows": [], "Movies": []}}
            if endpoint.startswith("api/v3/Episode/"):
                eid = int(endpoint.rsplit("/", 1)[1])
                return {"IsHidden": eid in case.hidden,
                        "IDs": {"ID": eid, "TMDB": {"Episode": []}},
                        "AniDB": {"Type": case.episode_types.get(eid, "Episode"),
                                  "EpisodeNumber": eid % 100},
                        "TMDB": {"Episodes": []}}
            raise AssertionError("unexpected fixture API endpoint: " + url)

        scanner.HttpReq = http
        subdirs = sorted(str(path) + (os.sep if case.trailing_queue else '') for path in root.iterdir() if path.is_dir())
        root_argument = str(root) + (os.sep if case.trailing_root else '')
        media = []
        sentinel = Episode(b"Existing", 1, 1) if case.existing else None
        if sentinel:
            media.append(sentinel)
        if case.partial:
            folder = root / "Release"
            scanner.Scan("Release", sorted(str(p) for p in folder.iterdir()),
                         media, [], root=root_argument)
        else:
            scanner.Scan("", [], media, subdirs, root=root_argument)
        if sentinel:
            check(media[0] is sentinel, "pre-existing media record was replaced")
            media = media[1:]
        actual = sorted((m.show.decode("utf-8"), m.season, m.episode,
                         tuple(Path(p).relative_to(root).as_posix() for p in m.parts),
                         m.display_offset) for m in media)
        check(actual == sorted(case.expected), "episode mappings differ: " + repr(actual))
        if not case.partial:
            remaining = tuple(Path(p).relative_to(root).as_posix() for p in subdirs)
            check(remaining == case.remaining, "native subdirectory queue differs: " + repr(remaining))
        check(snapshot(root) == before, "fixture files/directories were mutated")
        check(len(log.errors) == len(case.errors), "unexpected errors: " + repr(log.errors))
        check(all(message.startswith(prefix) for message, prefix in zip(log.errors, case.errors)),
              "error classification differs: " + repr(log.errors))
        check(all("?include=XRefs" in url for url in requests if "/File/" in url),
              "file lookups omitted cross-references")
        if case.expected:
            check(bool(stack_calls), "SDK stacking hook was not called")
        if case.name == "one file linked to two series keeps primary-series policy":
            check(not any("/Series/2?" in url for url in requests),
                  "secondary crossover series was unexpectedly queried")


CASES = [
    Case("flat folder contains files from two series",
         {"Release/a.mkv": [(1, [101])], "Release/b.mkv": [(2, [201])]},
         (result("Series A", 1, "Release/a.mkv"), result("Series B", 1, "Release/b.mkv"))),
    Case("flat folder with a single series",
         {"Release/a.mkv": [(1, [101])], "Release/b.mkv": [(1, [102])]},
         (result("Series A", 1, "Release/a.mkv"), result("Series A", 2, "Release/b.mkv"))),
    Case("existing nested workaround stays active",
         {"Outer/Release/a.mkv": [(1, [101])], "Outer/Release/b.mkv": [(2, [201])]},
         (result("Series A", 1, "Outer/Release/a.mkv"), result("Series B", 1, "Outer/Release/b.mkv"))),
    Case("existing empty-child workaround stays active",
         {"Release/a.mkv": [(1, [101])], "Release/b.mkv": [(2, [201])]},
         (result("Series A", 1, "Release/a.mkv"), result("Series B", 1, "Release/b.mkv")),
         dirs=("Release/Empty",)),
    Case("files and real subfolders are both scanned once",
         {"Release/a.mkv": [(1, [101])], "Release/SPs/b.mkv": [(2, [201])]},
         (result("Series A", 1, "Release/a.mkv"), result("Series B", 1, "Release/SPs/b.mkv"))),
    Case("two flat folders are both collected",
         {"First/a.mkv": [(1, [101])], "Second/b.mkv": [(2, [201])]},
         (result("Series A", 1, "First/a.mkv"), result("Series B", 1, "Second/b.mkv"))),
    Case("non-video files are filtered without modification",
         {"Release/a.mkv": [(1, [101])], "Release/notes.txt": []},
         (result("Series A", 1, "Release/a.mkv"),)),
    Case("empty folder stays in the native queue", {}, (),
         dirs=("Empty",), remaining=("Empty",)),
    Case("ambiguous suffix lookup is still skipped",
         {"Release/a.mkv": [(1, [101])]}, (), ambiguous=True,
         errors=("Multiple Files:",)),
    Case("file without series links is still skipped",
         {"Release/a.mkv": []}, (), errors=("Missing ID:",)),
    Case("hidden episode is still skipped",
         {"Release/a.mkv": [(1, [101])]}, (), hidden=(101,)),
    Case("API outage is logged, not hidden by the test harness",
         {"Release/a.mkv": [(1, [101])]}, (), unavailable=True,
         errors=("Error in Scan:",)),
    Case("combined episode file retains both mappings and offsets",
         {"Release/combined.mkv": [(1, [101, 102])]},
         (result("Series A", 1, "Release/combined.mkv", offset=0),
          result("Series A", 2, "Release/combined.mkv", offset=50))),
    Case("one file linked to two series keeps primary-series policy",
         {"Release/crossover.mkv": [(1, [101]), (2, [201])]},
         (result("Series A", 1, "Release/crossover.mkv"),)),
    Case("special episodes retain season-zero mapping",
         {"Release/special.mkv": [(2, [201])]},
         (result("Series B", 1, "Release/special.mkv", season=0),),
         episode_types={201: "Special"}),
    Case("partial scanner call retains per-file mapping",
         {"Release/a.mkv": [(1, [101])], "Release/b.mkv": [(2, [201])]},
         (result("Series A", 1, "Release/a.mkv"), result("Series B", 1, "Release/b.mkv")),
         partial=True),
    Case("existing root media records are preserved",
         {"Release/a.mkv": [(1, [101])]},
         (result("Series A", 1, "Release/a.mkv"),), existing=True),
    Case("identity mode separates identical titles in one flat folder",
         {"Release/a.mkv": [(1, [101])], "Release/b.mkv": [(2, [201])]},
         (result("Shared title [ShokoRelay SeriesID:1]", 1, "Release/a.mkv"),
          result("Shared title [ShokoRelay SeriesID:2]", 1, "Release/b.mkv")),
         identity=True, series_names={1: "Shared title", 2: "Shared title"}),
    Case("explicitly disabled identity retains untagged legacy output",
         {"Release/a.mkv": [(1, [101])]},
         (result("Series A", 1, "Release/a.mkv"),), identity=False),
    Case("identity survives partial callbacks for duplicate titles",
         {"Release/a.mkv": [(1, [101])], "Release/b.mkv": [(2, [201])]},
         (result("Shared title [ShokoRelay SeriesID:1]", 1, "Release/a.mkv"),
          result("Shared title [ShokoRelay SeriesID:2]", 1, "Release/b.mkv")),
         identity=True, series_names={1: "Shared title", 2: "Shared title"}, partial=True),
    Case("identity preserves Unicode names and combined episode offsets",
         {"Release/a.mkv": [(1, [101, 102])]},
         (result("星空・カフェ [ShokoRelay SeriesID:1]", 1, "Release/a.mkv", offset=0),
          result("星空・カフェ [ShokoRelay SeriesID:1]", 2, "Release/a.mkv", offset=50)),
         identity=True, series_names={1: "星空・カフェ"}),
    Case("identity preserves signed credit-season coordinates",
         {"Release/a.mkv": [(1, [101])]},
         (result("Series A [ShokoRelay SeriesID:1]", 1, "Release/a.mkv", season=-1),),
         identity=True, episode_types={101: "Credits"}),
    Case("identity accepts the maximum signed database ID",
         {"Release/a.mkv": [(2147483647, [101])]},
         (result("Boundary [ShokoRelay SeriesID:2147483647]", 1, "Release/a.mkv"),),
         identity=True, series_names={2147483647: "Boundary"}),
    Case("identity rejects zero IDs instead of emitting untagged files",
         {"Release/a.mkv": [(0, [101])]}, (), identity=True, errors=("Error in Scan:",)),
    Case("identity rejects oversized IDs",
         {"Release/a.mkv": [(2147483648, [101])]}, (), identity=True,
         series_names={2147483648: "Boundary"}, errors=("Error in Scan:",)),
    Case("identity rejects reserved markers in actual titles",
         {"Release/a.mkv": [(1, [101])]}, (), identity=True,
         series_names={1: "Title [ShokoRelay SeriesID:2]"}, errors=("Error in Scan:",)),
    Case("identity rejects newlines in actual titles",
         {"Release/a.mkv": [(1, [101])]}, (), identity=True,
         series_names={1: "Title\nSubtitle"}, errors=("Error in Scan:",)),
    Case("identity rejects empty titles",
         {"Release/a.mkv": [(1, [101])]}, (), identity=True,
         series_names={1: ""}, errors=("Error in Scan:",)),
    Case("identity mode retains primary-series crossover selection",
         {"Release/crossover.mkv": [(1, [101]), (2, [201])]},
         (result("Series A [ShokoRelay SeriesID:1]", 1, "Release/crossover.mkv"),), identity=True),
    Case("trailing root separator still removes flat native callback",
         {"Release/a.mkv": [(1, [101])]}, (result("Series A", 1, "Release/a.mkv"),), trailing_root=True),
    Case("trailing root separator still removes nested top-level callback",
         {"Outer/Release/a.mkv": [(1, [101])]}, (result("Series A", 1, "Outer/Release/a.mkv"),), trailing_root=True),
    Case("trailing queued directory separator still removes callback",
         {"Release/a.mkv": [(1, [101])]}, (result("Series A", 1, "Release/a.mkv"),), trailing_queue=True),
    Case("identity and noncanonical roots keep duplicate titles separated",
         {"Outer/First/a.mkv": [(1, [101])], "Outer/Second/b.mkv": [(2, [201])]},
         (result("Shared [ShokoRelay SeriesID:1]", 1, "Outer/First/a.mkv"),
          result("Shared [ShokoRelay SeriesID:2]", 1, "Outer/Second/b.mkv")),
         identity=True, series_names={1: "Shared", 2: "Shared"}, trailing_root=True, trailing_queue=True),
]


def main():
    failures = []
    scenarios = [(case.name, lambda case=case: run_case(case)) for case in CASES]
    scenarios.append(("renamed scanner keeps configuration and logs isolated", run_alias))
    for name, run in scenarios:
        try:
            run()
        except Exception as exc:
            failures.append((name, str(exc)))
    if failures:
        for name, message in failures:
            print("FAIL " + name + ": " + message)
        print(str(len(failures)) + " of " + str(len(scenarios)) + " scenarios failed")
        return 1
    print("ok " + str(CHECKS) + " checks passed across " + str(len(scenarios)) + " scanner scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
