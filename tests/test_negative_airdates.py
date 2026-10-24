#!/usr/bin/env python3
"""Pure airdate gate in the real agent; does not emulate native metadata import."""
import test_agent_identity as harness


def main():
    module, _ = harness.load_agent()
    seasons = (-4, -3, -2, -1, 0, 1)
    preferences = ('Disabled', 'Exclude Other', 'Enabled')
    cases = [(s, p, strict) for s in seasons for p in preferences for strict in (False, True)]
    for season, preference, strict in cases:
        expected = season < 0 and (strict or (preference != 'Disabled' and not (season == -4 and preference == 'Exclude Other')))
        harness.check(module.suppress_negative_airdate(season, preference, strict) == expected,
                      'airdate gate widened/narrowed unexpectedly')
    harness.check(module.suppress_negative_airdate(-4, 'Exclude Other', True),
                  'strict other-season duplicate-date hint retained')
    harness.check(not module.suppress_negative_airdate(-4, 'Exclude Other', False),
                  'legacy other-season date policy changed')
    harness.check(not module.suppress_negative_airdate(1, 'Disabled', True),
                  'positive season dates changed')
    print('ok %s checks passed across %s negative-airdate cases' % (harness.CHECKS, len(cases)))


if __name__ == '__main__':
    main()
