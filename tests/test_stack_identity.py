#!/usr/bin/env python3
"""Portable identity boundaries around the SDK hook, not a native stacking proof."""
import types
import test_scanner as harness


def episode(show, season, number, path, offset=0):
    item = harness.Episode(show, season, number)
    item.parts = [path]
    item.display_offset = offset
    return item


def case(identity, left, right, merged):
    scanner, log, _ = harness.load_scanner(identity=identity)
    calls = []

    def filename_only_stacker(path, files, items, dirs):
        # Deliberately ignores identity, like the generic filename heuristic.
        # All inputs are synthetic reel1/reel2 names. This stub tests only
        # which objects Relay permits the SDK to compare, not its algorithm.
        calls.append(tuple(items))
        if len(items) > 1:
            items[0].parts.extend(items[1].parts)
            del items[1]

    scanner.Stack = types.SimpleNamespace(Scan=filename_only_stacker)
    media = [left, right]
    scanner.stack_media('Release', ['reel1.mkv', 'reel2.mkv'], media, [])
    harness.check(len(media) == (1 if merged else 2), 'wrong stack boundary')
    harness.check(sorted(p for item in media for p in item.parts) == ['reel1.mkv', 'reel2.mkv'], 'source parts lost')
    harness.check(len(calls) == (1 if merged else 2), 'SDK groups differ')
    if not merged:
        harness.check(media[0] is left and media[1] is right, 'identity objects replaced')
    harness.check(not log.errors, 'unexpected scanner error')


def main():
    a = b'Synthetic [ShokoRelay SeriesID:1]'
    b = b'Synthetic [ShokoRelay SeriesID:2]'
    scenarios = [
        (True, a, 0, 3, 0, a, 0, 4, 0, False),
        (True, a, -1, 1, 0, b, -1, 1, 0, False),
        (True, a, -1, 1, 0, a, 1, 1, 0, False),
        (True, a, 1, 1, 0, a, 1, 1, 50, False),
        (True, a, 1, 1, 0, a, 1, 1, 0, True),
        (True, a, -1, 1, 0, a, -1, 1, 0, True),
        (False, a, 0, 3, 0, a, 0, 4, 0, True),
        (None, a, -1, 1, 0, b, -1, 1, 0, True),
    ]
    for enabled, s1, season1, n1, offset1, s2, season2, n2, offset2, merged in scenarios:
        case(enabled, episode(s1, season1, n1, 'reel1.mkv', offset1),
             episode(s2, season2, n2, 'reel2.mkv', offset2), merged)
    scanner, _, calls = harness.load_scanner(identity=True)
    scanner.stack_media('', [], [], [])
    harness.check(not calls, 'empty identity list invoked SDK')
    print('ok %s checks passed across %s identity stack scenarios plus empty case' % (harness.CHECKS, len(scenarios)))


if __name__ == '__main__':
    main()
