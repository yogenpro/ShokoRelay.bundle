#!/usr/bin/env python3
"""Loopback-only synthetic Shoko API for manual native scanner experiments.

No catalogue, media inventory, real credentials or external service is used.
This adapter covers scanner requests only, not the legacy metadata agent.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlsplit


KEY = "fixture-key-not-a-real-secret"
FILES = {"series-a-01.mkv": (1000001, 1000011),
         "series-b-01.mkv": (1000002, 1000021)}
SERIES = {1000001: "Relay Fixture Series A", 1000002: "Relay Fixture Series B"}
EPISODES = {1000011, 1000021}


def route(method, target, body=None, key=None):
    path = urlsplit(target).path
    if method == "POST" and path == "/api/auth":
        if body != {"user": "fixture", "pass": "", "device": "Shoko Relay for Plex"}:
            return 403, {"error": "only the synthetic fixture identity is allowed"}
        return 200, {"apikey": KEY}
    if method != "GET":
        return 405, {"error": "unsupported fixture method"}
    if key != KEY:
        return 401, {"error": "fixture authentication required"}
    prefix = "/api/v3/File/PathEndsWith/"
    if path.startswith(prefix):
        suffix = unquote(path[len(prefix):]).replace("\\", "/")
        pieces = suffix.split("/")
        if len(pieces) != 2 or pieces[0] != "Shared Release" or pieces[1] not in FILES:
            return 200, []  # Never guess a file or read a filesystem path.
        sid, eid = FILES[pieces[1]]
        return 200, [{"SeriesIDs": [{"SeriesID": {"ID": sid},
                                     "EpisodeIDs": [{"ID": eid}]}]}]
    for prefix, records, kind in (("/api/v3/Series/", SERIES, "series"),
                                 ("/api/v3/Episode/", EPISODES, "episode")):
        if not path.startswith(prefix):
            continue
        try:
            ident = int(path[len(prefix):])
        except ValueError:
            return 404, {"error": "unknown fixture identity"}
        if ident not in records:
            return 404, {"error": "unknown fixture identity"}
        if kind == "series":
            return 200, {"Name": SERIES[ident], "TMDB": {"Shows": [], "Movies": []}}
        return 200, {"IsHidden": False, "IDs": {"ID": ident, "TMDB": {"Episode": []}},
                     "AniDB": {"Type": "Episode", "EpisodeNumber": 1},
                     "TMDB": {"Episodes": []}}
    return 404, {"error": "unsupported fixture endpoint"}


class Handler(BaseHTTPRequestHandler):
    def respond(self, method, body=None):
        status, payload = route(method, self.path, body, self.headers.get("apikey"))
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.respond("GET")

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("invalid fixture body length")
            body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            self.send_error(400, "invalid fixture request")
            return
        self.respond("POST", body)

    def log_message(self, fmt, *args):
        # No request bodies or authentication headers are logged.
        print(json.dumps({"method": self.command, "path": self.path}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if args.port != 0 and not 1024 <= args.port <= 65535:
        parser.error("use an ephemeral port or an unprivileged explicit port")
    with HTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(json.dumps({"fixture_only": True, "address": "127.0.0.1",
                          "port": server.server_port}), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
