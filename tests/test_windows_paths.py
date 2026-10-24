#!/usr/bin/env python3
"""Credential-free Windows path regressions, not native Plex acceptance.

The real scanner runs against ntpath and a synthetic, in-memory filesystem.
The filesystem models Python 2's unprefixed MAX_PATH failure; no drive, SDK,
configuration, credential, or network is accessed. SDK stacking stays a stub.
"""

import ntpath
import types
from urllib.parse import unquote

import test_scanner as harness


PREFIX = "\\\\?\\"
UNC_PREFIX = PREFIX + "UNC\\"


def plain(path):
    if path.startswith(UNC_PREFIX):
        return "\\\\" + path[len(UNC_PREFIX):]
    if path.startswith(PREFIX):
        return path[len(PREFIX):]
    return path


def extended(path):
    return UNC_PREFIX + path[2:] if path.startswith("\\\\") else PREFIX + path


class WindowsFS:
    def __init__(self, root, relative_files):
        self.root = root
        self.files = {ntpath.join(root, path) for path in relative_files}
        self.dirs = {root}
        self.io = []
        for path in self.files:
            parent = ntpath.dirname(path)
            while ntpath.normcase(parent.rstrip("\\")) != ntpath.normcase(root.rstrip("\\")):
                self.dirs.add(parent)
                parent = ntpath.dirname(parent)
        self.entries = {}
        for path in self.dirs | self.files:
            if path != root:
                self.entries.setdefault(ntpath.normcase(ntpath.dirname(path)).rstrip("\\"), []).append(ntpath.basename(path))
        self.directory_keys = {ntpath.normcase(p).rstrip("\\") for p in self.dirs}
        self.path = types.SimpleNamespace(**{name: getattr(ntpath, name) for name in (
            "abspath", "basename", "dirname", "join", "normcase", "normpath", "relpath", "split",
        )})
        self.path.isdir = self.isdir
        self.os = types.SimpleNamespace(name="nt", sep="\\", path=self.path, listdir=self.listdir)

    def listdir(self, path):
        # Demonstrated Python 2/Windows failure, before directory traversal.
        if not path.startswith(PREFIX) and len(path.encode("utf-8")) >= 260:
            raise TypeError("encoded string too long (260, maximum length 259)")
        self.io.append(path)
        key = ntpath.normcase(plain(path)).rstrip("\\")
        if key not in self.directory_keys:
            raise OSError("synthetic directory does not exist")
        return sorted(self.entries.get(key, []))

    def isdir(self, path):
        self.io.append(path)
        return ntpath.normcase(plain(path)).rstrip("\\") in self.directory_keys


def helper_cases():
    scanner, _, _ = harness.load_scanner()
    scanner.os = types.SimpleNamespace(name="nt", path=ntpath)
    cases = (
        ("Z:\\fixture\\Show", "Z:\\fixture\\Show", PREFIX + "Z:\\fixture\\Show"),
        (PREFIX + "Z:\\fixture\\Show", "Z:\\fixture\\Show", PREFIX + "Z:\\fixture\\Show"),
        ("\\\\server\\share\\Show", "\\\\server\\share\\Show", UNC_PREFIX + "server\\share\\Show"),
        (UNC_PREFIX + "server\\share\\Show", "\\\\server\\share\\Show", UNC_PREFIX + "server\\share\\Show"),
        ("Z:\\fixture\\長い名前", "Z:\\fixture\\長い名前", PREFIX + "Z:\\fixture\\長い名前"),
    )
    for supplied, expected, io_path in cases:
        for value in (supplied, supplied.encode("utf-8")):
            harness.check(scanner.ordinary_path(value) == expected, "extended/UTF-8 path arithmetic differs")
            harness.check(scanner.filesystem_path(value) == io_path, "wide filesystem path differs")
            harness.check(scanner.canonical_path(value) == ntpath.normcase(expected), "canonical path differs")
    for root in ("Z:\\fixture", "\\\\server\\share"):
        for base in (root, extended(root)):
            for child in (root + "\\Show", extended(root + "\\Show")):
                harness.check(scanner.relative_path(child, base) == "Show", "mixed-prefix relative path differs")
    scanner.os = types.SimpleNamespace(name="posix")
    for path in ("/fixture/Show", b"/fixture/Show", "//fixture/Show"):
        harness.check(scanner.ordinary_path(path) is path, "non-Windows path arithmetic changed input")
        harness.check(scanner.filesystem_path(path) is path, "non-Windows filesystem path changed input")


def root_case(root, queue_prefix, root_prefix, trailing):
    long_parent = "Nested\\" + "long-folder-" * 22 + "\\長い名前"
    relatives = ("Release\\one.mkv", "Release\\two.mkv", long_parent + "\\three.mkv")
    fs = WindowsFS(root, relatives)
    scanner, log, stack_calls = harness.load_scanner(identity=True)
    scanner.os = fs.os
    scanner.sys = types.SimpleNamespace(version_info=(2, 7))

    def sdk_filter(path, files, media, dirs, sdk_root):
        # Native Filter.py calls f.decode('utf-8') when Unicode is supported.
        # Giving it Unicode instead aborts before collection finishes.
        harness.check(all(isinstance(f, bytes) for f in files), "legacy SDK received Unicode instead of UTF-8 bytes")
        harness.check(all(f.decode("utf-8").startswith(PREFIX) for f in files), "SDK filesystem reads lacked extended paths")
        files[:] = [f for f in files if ntpath.splitext(f)[1].lower() == b".mkv"]

    scanner.VideoFiles.Scan = sdk_filter
    requests = []
    suffixes = {ntpath.join(ntpath.basename(ntpath.dirname(path)), ntpath.basename(path)): sid
                for sid, path in enumerate(relatives, 1)}

    def http(url):
        requests.append(url)
        endpoint = url.split("?", 1)[0]
        if endpoint.startswith("api/v3/File/PathEndsWith/"):
            sid = suffixes[unquote(endpoint.split("PathEndsWith/", 1)[1])]
            return [{"SeriesIDs": [{"SeriesID": {"ID": sid}, "EpisodeIDs": [{"ID": sid * 100 + 1}]}]}]
        if endpoint.startswith("api/v3/Series/"):
            return {"Name": "Identical title", "TMDB": {"Shows": [], "Movies": []}}
        if endpoint.startswith("api/v3/Episode/"):
            return {"IsHidden": False, "IDs": {"ID": int(endpoint.rsplit("/", 1)[1]), "TMDB": {"Episode": []}},
                    "AniDB": {"Type": "Episode", "EpisodeNumber": 1}, "TMDB": {"Episodes": []}}
        raise AssertionError("unexpected synthetic endpoint")

    scanner.HttpReq = http
    queue = [ntpath.join(root, name) for name in ("Release", "Nested")]
    if queue_prefix:
        queue = [extended(path) for path in queue]
    if trailing:
        queue = [path + "\\" for path in queue]
    root_argument = extended(root) if root_prefix else root
    if trailing:
        root_argument += "\\"
    media = []
    # Verify the failure model really refuses the old filesystem operation.
    long_directory = ntpath.join(root, ntpath.dirname(relatives[-1]))
    try:
        fs.listdir(long_directory)
    except TypeError:
        harness.check(True, "legacy long-path failure reproduced")
    else:
        harness.check(False, "legacy long-path model did not fail")
    scanner.Scan("", [], media, queue, root=root_argument)
    harness.check(queue == [], "consumed native queue retained ordinary/extended callbacks")
    harness.check(len(media) == 3, "long path root collection stopped before all records")
    actual = {(m.show.decode("utf-8"), m.season, m.episode, tuple(p.decode("utf-8") for p in m.parts)) for m in media}
    expected = {("Identical title [ShokoRelay SeriesID:%s]" % sid, 1, 1, (ntpath.join(root, path),))
                for sid, path in enumerate(relatives, 1)}
    harness.check(actual == expected, "identity, coordinates, or original source paths changed")
    harness.check(not log.errors, "Windows path scan swallowed an error")
    harness.check(all(isinstance(p, str) and p.startswith(PREFIX) for p in fs.io), "filesystem access was not wide/prefixed")
    harness.check(len(stack_calls) == 5, "identity-scoped stacking did not finish both file-containing folders (2 then 3 identities)")
    harness.check(any("%E9%95%B7" in url for url in requests), "Unicode immediate parent was not UTF-8 quoted")


def targeted_case():
    root = "Z:\\fixture"
    path = root + "\\Release\\episode.mkv"
    fs = WindowsFS(root, ("Release\\episode.mkv", "Release\\Child\\extra.txt"))
    scanner, log, _ = harness.load_scanner(identity=True)
    scanner.os = fs.os

    def sdk_filter(path, files, media, dirs, sdk_root):
        files[:] = [f for f in files if ntpath.splitext(f)[1].lower() == ".mkv"]
        # Exercise restoration of SDK-created media parts too.
        item = harness.Episode(b"SDK-created", 1, 99)
        item.parts = files[:]
        media.append(item)

    scanner.VideoFiles.Scan = sdk_filter

    def http(url):
        if "PathEndsWith/" in url:
            return [{"SeriesIDs": [{"SeriesID": {"ID": 1}, "EpisodeIDs": [{"ID": 101}]}]}]
        if "api/v3/Series/" in url:
            return {"Name": "Targeted", "TMDB": {"Shows": [], "Movies": []}}
        if "api/v3/Episode/" in url:
            return {"IsHidden": False, "IDs": {"ID": 101, "TMDB": {"Episode": []}},
                    "AniDB": {"Type": "Episode", "EpisodeNumber": 1}, "TMDB": {"Episodes": []}}
        raise AssertionError("unexpected synthetic endpoint")

    scanner.HttpReq = http
    queued = [extended(root + "\\Release\\Child")]
    supplied_file = extended(path)
    media = []
    scanner.Scan("Release", [supplied_file], media, queued, root=root)
    harness.check(len(media) == 2 and not log.errors, "mixed-prefix callback logging aborted targeted scan")
    harness.check(all(m.parts == [supplied_file] for m in media), "targeted or SDK-created source path was rewritten")
    harness.check(queued == [extended(root + "\\Release\\Child")], "targeted child callback was removed")
    harness.check(not fs.io, "targeted callback unexpectedly traversed filesystem")


def main():
    helper_cases()
    scenarios = [(root, queued, prefixed_root, trailing)
                 for root in ("Z:\\fixture", "\\\\server\\share")
                 for queued in (False, True) for prefixed_root in (False, True)
                 for trailing in (False, True)]
    for scenario in scenarios:
        root_case(*scenario)
    targeted_case()
    print("ok %s checks passed across %s Windows root scenarios plus path/targeted cases" %
          (harness.CHECKS, len(scenarios)))


if __name__ == "__main__":
    main()
