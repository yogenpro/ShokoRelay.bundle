#!/usr/bin/env python3
"""Execute legacy agent Search with fake SDK/API; never credentials or network.

These checks do not reproduce Plex's native grouping, GUID assignment or refresh.
"""
import json
import sys
import types
from pathlib import Path
from urllib.parse import quote_plus

from test_scanner import ForbiddenIO, forbidden_io

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Contents/Code/__init__.py'
CHECKS = 0


def check(condition, message):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(message)


class Prefs(dict):
    def __getitem__(self, key):
        if key in ('Username', 'Password', 'Hostname', 'Port'):
            raise ForbiddenIO('real authentication/connection settings forbidden')
        return super().__getitem__(key)


class Result:
    def __init__(self, ident, title, year, score, language):
        self.id, self.title, self.year = ident, title, year
        self.score, self.language = score, language


class Results(list):
    def Append(self, value):
        self.append(value)


def load_agent(required=True):
    logs = []
    sdk = {
        'Agent': types.SimpleNamespace(TV_Shows=type('TV_Shows', (), {})),
        'Locale': types.SimpleNamespace(Language=types.SimpleNamespace(English='en')),
        'Prefs': Prefs(RequireSeriesIDToken=required), 'Log': logs.append,
        'MetadataSearchResult': Result, 'basestring': str,
        'HTTP': types.SimpleNamespace(Request=forbidden_io),
        'JSON': types.SimpleNamespace(ObjectFromString=forbidden_io),
    }
    legacy_urllib = types.ModuleType('urllib')
    legacy_urllib.quote_plus = quote_plus
    absent = object()
    previous = sys.modules.get('urllib', absent)
    module = types.ModuleType('agent_under_test')
    module.__dict__.update(sdk)
    try:
        sys.modules['urllib'] = legacy_urllib
        source = SOURCE.read_text(encoding='utf-8')
        # Python 3 lacks Python 2's ur string prefix. This single lexical shim
        # lets the complete shipped module compile; Search/Update stay real.
        check(source.count("re.sub(ur'^(") == 1, 'legacy syntax shim no longer matches exactly')
        source = source.replace("re.sub(ur'^(", "re.sub(r'^(")
        exec(compile(source, str(SOURCE), 'exec'), module.__dict__)
    finally:
        if previous is absent:
            sys.modules.pop('urllib', None)
        else:
            sys.modules['urllib'] = previous
    return module, logs


def direct_case(ident, title='Shared title', language='zh', manual=False):
    module, logs = load_agent()
    requests = []

    def http(path):
        requests.append(path)
        check(path == 'api/v3/Series/%s?includeDataFrom=AniDB,TMDB' % ident,
              'ID search used an unexpected endpoint/title lookup')
        return {'IDs': {'ID': ident}, 'Name': 'Current preferred title',
                'AniDB': {'AirDate': '2001-02-03'}}

    module.HttpReq = http
    results = Results()
    module.ShokoRelayAgent().search(results, types.SimpleNamespace(show=title + ' [ShokoRelay SeriesID:%s]' % ident), language, manual)
    check(len(results) == 1, 'canonical identity did not give exactly one result')
    check(results[0].id == str(ident), 'identity changed to a different series')
    check(results[0].title == 'Current preferred title', 'display title was guessed from the token')
    check(results[0].year == '2001' and results[0].score == 100 and results[0].language == language,
          'search-result metadata differs')
    check(len(requests) == 1 and not logs, 'direct ID search retried or fell back')


MALFORMED = [
    'Title [ShokoRelay SeriesID:0]', 'Title [ShokoRelay SeriesID:-1]',
    'Title [ShokoRelay SeriesID:+1]', 'Title [ShokoRelay SeriesID:01]',
    'Title [ShokoRelay SeriesID:2147483648]', 'Title [ShokoRelay SeriesID:99999999999]',
    'Title [ShokoRelay SeriesID:1.0]', 'Title [ShokoRelay SeriesID:True]',
    'Title [ShokoRelay SeriesID:١]', 'Title [ShokoRelay SeriesID:]',
    'Title [ShokoRelay SeriesID:1', 'Title [ShokoRelay SeriesID:1] tail',
    '[ShokoRelay SeriesID:1]', 'Title [ShokoRelay SeriesID: 1]',
    'Title [ShokoRelay SeriesID:1 ]', 'Title [ShokoRelay SeriesID :1]',
    'Title [ShokoRelay SeriesID:1]\n', 'Title\rSubtitle [ShokoRelay SeriesID:1]',
    'Title\nSubtitle [ShokoRelay SeriesID:1]',
    'Title [ShokoRelay SeriesID:2] [ShokoRelay SeriesID:1]',
    'Title\t[ShokoRelay SeriesID:1]',
]


def rejected_case(name, required):
    module, logs = load_agent(required)
    module.HttpReq = forbidden_io
    results = Results()
    module.ShokoRelayAgent().Search(results, types.SimpleNamespace(show=name), 'en', False)
    check(not results, 'malformed/untagged input became a match')
    check(bool(logs), 'rejection was silent')


RESPONSES = [None, [], {}, {'IDs': {'ID': 2}, 'Name': 'Wrong series'},
             {'IDs': {'ID': True}, 'Name': 'Boolean ID'},
             {'IDs': {'ID': 1}, 'Name': ''}, {'IDs': {'ID': 1}},
             {'IDs': {'ID': 1}, 'Name': ['Not text']},
             {'Name': 'No ID'}, {'IDs': {'ID': '01'}, 'Name': 'Noncanonical ID'}]


def response_case(response):
    module, logs = load_agent()
    requests = []
    def http(path):
        requests.append(path)
        return response
    module.HttpReq = http
    results = Results()
    module.ShokoRelayAgent().Search(results, types.SimpleNamespace(show='Title [ShokoRelay SeriesID:1]'), 'zh', False)
    check(not results, 'mismatched/incomplete response was accepted')
    check(requests == ['api/v3/Series/1?includeDataFrom=AniDB,TMDB'], 'bad response triggered title fallback')
    check(bool(logs), 'bad response rejection was silent')


def outage_case():
    module, _ = load_agent(False)
    requests = []
    def http(path):
        requests.append(path)
        raise RuntimeError('synthetic API unavailable')
    module.HttpReq = http
    results = Results()
    try:
        module.ShokoRelayAgent().Search(results, types.SimpleNamespace(show='Title [ShokoRelay SeriesID:1]'), 'en', False)
    except RuntimeError:
        pass
    else:
        raise AssertionError('ID API outage was treated as successful search')
    check(not results, 'API outage yielded a guessed match')
    check(requests == ['api/v3/Series/1?includeDataFrom=AniDB,TMDB'], 'API outage triggered title lookup')


def legacy_case():
    module, logs = load_agent(False)
    requests = []
    def http(path):
        requests.append(path)
        if '/Search?' in path:
            return [{'IDs': {'ID': 1}, 'Name': 'Legacy title', 'Distance': 0},
                    {'IDs': {'ID': 2}, 'Name': 'Alternative', 'Distance': .1}]
        if path in ('api/v3/Series/1/AniDB', 'api/v3/Series/2/AniDB'):
            return {'AirDate': '1999-03-04'}
        raise AssertionError('unexpected legacy fixture API lookup')
    module.HttpReq = http
    results = Results()
    module.ShokoRelayAgent().Search(results, types.SimpleNamespace(show='Legacy title'), 'en', True)
    check([x.id for x in results] == ['1', '2'], 'legacy candidate selection changed')
    check([x.score for x in results] == [100, 88], 'legacy ranking changed')
    check(all(x.year == '1999' for x in results), 'legacy year handling changed')
    check('query=Legacy+title&fuzzy=false&limit=10' in requests[0], 'legacy title query changed')
    check(not logs, 'legacy search was incorrectly rejected')


def defaults_case():
    prefs = json.loads((ROOT / 'Contents/DefaultPrefs.json').read_text(encoding='utf-8'))
    matches = [x for x in prefs if x['id'] == 'RequireSeriesIDToken']
    check(len(matches) == 1 and matches[0]['type'] == 'bool' and matches[0]['default'] is False,
          'legacy default was silently made strict')
    scanner_cfg = (ROOT / 'Contents/Scanners/Series/Shoko Relay Scanner.cfg').read_text(encoding='utf-8')
    check('SeriesIDIdentity=False' in scanner_cfg, 'default scanner identity mode was enabled')


def main():
    cases = [(f'direct ID {ident}', lambda ident=ident: direct_case(ident)) for ident in (1, 2, 2147483647)]
    cases += [('Unicode/stale display name', lambda: direct_case(17, '星空・カフェ', 'ja')),
              ('manual explicit ID', lambda: direct_case(18, manual=True))]
    cases += [(f'malformed input {i} strict={required}', lambda name=name, required=required: rejected_case(name, required))
              for i, name in enumerate(MALFORMED) for required in (False, True)]
    cases += [(f'untagged/nontext {i}', lambda name=name: rejected_case(name, True))
              for i, name in enumerate(('Plain title', '', None, 0))]
    cases += [(f'incomplete/mismatched response {i}', lambda response=response: response_case(response))
              for i, response in enumerate(RESPONSES)]
    cases += [('ID API outage', outage_case), ('legacy title search', legacy_case), ('opt-in defaults', defaults_case)]
    failures = []
    for name, run in cases:
        try:
            run()
        except BaseException as error:
            failures.append(name + ': ' + type(error).__name__ + ': ' + str(error))
    if failures:
        for failure in failures:
            print('FAIL', failure)
        return 1
    print('ok %s checks passed across %s agent identity scenarios' % (CHECKS, len(cases)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
