#!/usr/bin/env python3
"""Pure routing checks: no listener, credentials, media or external requests."""

from fixture_api import KEY, route


CASES = [
    ("synthetic authentication", "POST", "/api/auth",
     {"user": "fixture", "pass": "", "device": "Shoko Relay for Plex"}, None, 200),
    ("real-looking identity refused", "POST", "/api/auth",
     {"user": "someone", "pass": "password", "device": "Shoko Relay for Plex"}, None, 403),
    ("wrong key refused", "GET", "/api/v3/Series/1000001", None, "other", 401),
    ("missing key refused", "GET", "/api/v3/Series/1000001", None, None, 401),
    ("first series", "GET", "/api/v3/Series/1000001?includeDataFrom=AniDB,TMDB", None, KEY, 200),
    ("second series", "GET", "/api/v3/Series/1000002", None, KEY, 200),
    ("unknown series", "GET", "/api/v3/Series/42", None, KEY, 404),
    ("invalid identity", "GET", "/api/v3/Series/not-an-id", None, KEY, 404),
    ("first episode", "GET", "/api/v3/Episode/1000011", None, KEY, 200),
    ("second episode", "GET", "/api/v3/Episode/1000021", None, KEY, 200),
    ("unknown episode", "GET", "/api/v3/Episode/42", None, KEY, 404),
    ("Windows suffix", "GET", "/api/v3/File/PathEndsWith/Shared%20Release%5Cseries-a-01.mkv?include=XRefs", None, KEY, 200),
    ("portable suffix", "GET", "/api/v3/File/PathEndsWith/Shared%20Release/series-b-01.mkv", None, KEY, 200),
    ("wrong parent", "GET", "/api/v3/File/PathEndsWith/Other/series-a-01.mkv", None, KEY, 200),
    ("wrong file", "GET", "/api/v3/File/PathEndsWith/Shared%20Release/unknown.mkv", None, KEY, 200),
    ("absolute path refused", "GET", "/api/v3/File/PathEndsWith/D:%5CShared%20Release%5Cseries-a-01.mkv", None, KEY, 200),
    ("extra prefix refused", "GET", "/api/v3/File/PathEndsWith/Outer/Shared%20Release/series-a-01.mkv", None, KEY, 200),
    ("traversal refused", "GET", "/api/v3/File/PathEndsWith/../Shared%20Release/series-a-01.mkv", None, KEY, 200),
    ("deletion refused", "DELETE", "/api/v3/Series/1000001", None, KEY, 405),
    ("unsupported write refused", "POST", "/api/v3/Series/1000001", {}, KEY, 405),
    ("unknown endpoint", "GET", "/api/v3/Unknown", None, KEY, 404),
]


def main():
    checks = 0
    for name, method, path, body, key, expected in CASES:
        status, payload = route(method, path, body, key)
        assert status == expected, name
        checks += 1
        if name in {"wrong parent", "wrong file", "absolute path refused",
                    "extra prefix refused", "traversal refused"}:
            assert payload == [], name
            checks += 1
        if name == "Windows suffix":
            assert payload[0]["SeriesIDs"][0]["SeriesID"]["ID"] == 1000001, name
            checks += 1
        if name == "portable suffix":
            assert payload[0]["SeriesIDs"][0]["SeriesID"]["ID"] == 1000002, name
            checks += 1
    print("ok " + str(checks) + " checks passed across " + str(len(CASES)) + " fixture API scenarios")


if __name__ == "__main__":
    main()
