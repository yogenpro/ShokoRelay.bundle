#!/usr/bin/env python3
"""Trusted GitHub control plane. Never import or execute candidate code here."""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

REPO = 'yogenpro/ShokoRelay.bundle'
UPSTREAM = 'natyusha/ShokoRelay.bundle'
BASE = 'master'
ANCHOR = 'c06ec963f5f3402d48f1690ca35663b5539efa87'
CONTEXT = 'relay/upstream-validation'
PREFIX = 'upstream-sync/'
SHA = re.compile(r'[0-9a-f]{40}\Z')
MARKER = re.compile(r'<!-- relay-upstream: ([0-9a-f]{40}) -->')
CONTROL = ('.github/', 'scripts/', 'tests/')


class APIError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__('GitHub HTTP %s: %s' % (code, message))


class GitHub:
    def request(self, path, method='GET', data=None):
        assert path.startswith('/') and not path.startswith('//')
        body = None if data is None else json.dumps(data).encode()
        request = urllib.request.Request('https://api.github.com' + path, data=body,
                                        method=method, headers={
            'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'Content-Type': 'application/json',
            'User-Agent': 'ShokoRelay-upstream-sync',
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                message = json.loads(raw).get('message', 'request failed')
            except (ValueError, AttributeError):
                message = 'request failed'
            raise APIError(error.code, message) from None

    def pages(self, path):
        result = []
        separator = '&' if '?' in path else '?'
        for page in range(1, 21):
            batch = self.request(path + separator + 'per_page=100&page=%s' % page)
            if not isinstance(batch, list):
                raise RuntimeError('Unexpected paginated GitHub response')
            result.extend(batch)
            if len(batch) < 100:
                return result
        raise RuntimeError('GitHub pagination exceeded limit; refusing partial results')


def endpoint(suffix):
    return '/repos/' + REPO + suffix


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError('Expected full commit SHA')
    return value


def ancestor(api, older, newer, repo=REPO):
    comparison = api.request('/repos/%s/compare/%s...%s' % (repo, sha(older), sha(newer)))
    return comparison['status'] in ('ahead', 'identical')


def is_upstream(pr):
    branch = pr['head']['ref']
    matches = MARKER.findall(pr.get('body') or '')
    return (pr['head']['repo'] is not None and
            pr['head']['repo']['full_name'] == REPO and len(matches) == 1 and
            branch == PREFIX + matches[0])


def eligible(pr):
    return (pr['state'] == 'open' and pr['base']['ref'] == BASE and
            pr['base']['repo']['full_name'] == REPO)


def paused(pr):
    return pr.get('draft', False) or any(label['name'] == 'sync-pause' for label in pr['labels'])


def controlled(path):
    return path == 'AGENTS.md' or path.startswith(CONTROL)


def status(api, head, state, description):
    run_url = os.environ.get('GITHUB_SERVER_URL', 'https://github.com') + '/' + REPO
    if os.environ.get('GITHUB_RUN_ID'):
        run_url += '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    api.request(endpoint('/statuses/' + sha(head)), 'POST', {
        'state': state, 'context': CONTEXT, 'description': description[:140],
        'target_url': run_url,
    })


def comment(api, pr, reason):
    marker = '<!-- relay-sync-exception: %s:%s -->' % (pr['head']['sha'], reason)
    existing = api.pages(endpoint('/issues/%s/comments' % pr['number']))
    if any(marker in item.get('body', '') for item in existing):
        return
    body = ('%s\nUpstream update needs attention: **%s**.\n\n'
            'The maintained branch has not been updated. See the linked Actions run '
            'for details and [UPSTREAM.md](https://github.com/yogenpro/ShokoRelay.bundle/blob/master/UPSTREAM.md) for the Codex '
            'repair prompt. Push a repair to this same PR branch; validation and '
            'automatic merging will resume. The scheduler preserves your repair '
            'commits and does not replace this branch with a newer upstream tip.\n\n'
            'To pause this update deliberately, make the PR a draft or add '
            '`sync-pause`.') % (marker, reason)
    api.request(endpoint('/issues/%s/comments' % pr['number']), 'POST', {'body': body})


def auto_merge(api, pr, enabled):
    operation = ('enable' if enabled else 'disable') + 'PullRequestAutoMerge'
    method = ',mergeMethod:MERGE' if enabled else ''
    response = api.request('/graphql', 'POST', {
        'query': 'mutation($id:ID!){%s(input:{pullRequestId:$id%s}){clientMutationId}}' % (operation, method),
        'variables': {'id': pr['node_id']},
    })
    if (not isinstance(response, dict) or response.get('errors') or
            not isinstance(response.get('data'), dict) or
            not isinstance(response['data'].get(operation), dict)):
        raise RuntimeError('Could not %s auto-merge; missing successful GitHub response' %
                           ('enable' if enabled else 'disable'))


def disable_auto(api, pr):
    if pr.get('auto_merge'):
        auto_merge(api, pr, False)


def prepare(api, event_pr=None):
    if event_pr is not None:
        pr = api.request(endpoint('/pulls/%s' % int(event_pr)))
    else:
        candidates = api.pages(endpoint('/pulls?state=open&base=' + BASE))
        pending = [item for item in candidates if is_upstream(item)]
        if len(pending) > 1:
            raise RuntimeError('Multiple upstream PRs are open; refusing to choose one')
        if pending:
            pr = api.request(endpoint('/pulls/%s' % pending[0]['number']))
        else:
            upstream = sha(api.request('/repos/' + UPSTREAM + '/git/ref/heads/master')['object']['sha'])
            base = sha(api.request(endpoint('/git/ref/heads/' + BASE))['object']['sha'])
            if not ancestor(api, ANCHOR, upstream, UPSTREAM):
                raise RuntimeError('Upstream history no longer contains the known baseline')
            if ancestor(api, upstream, base):
                print('No new upstream commits')
                return {}
            branch = PREFIX + upstream
            previous = api.pages(endpoint('/pulls?state=closed&base=' + BASE + '&head=' +
                                          urllib.parse.quote('yogenpro:' + branch, safe='')))
            if previous:
                print('This upstream revision already has a closed PR; reopen it to retry')
                return {}
            try:
                api.request(endpoint('/git/ref/heads/' + branch))
            except APIError as error:
                if error.code != 404:
                    raise
                api.request(endpoint('/git/refs'), 'POST', {
                    'ref': 'refs/heads/' + branch, 'sha': upstream,
                })
            # GitHub creates an ordinary merge commit, without running candidate code.
            # A conflict leaves the pristine upstream branch available for a blocked PR.
            try:
                api.request(endpoint('/merges'), 'POST', {
                    'base': branch, 'head': base,
                    'commit_message': 'Merge maintained fork into upstream update',
                })
            except APIError as error:
                if error.code != 409:
                    raise
            body = ('<!-- relay-upstream: %s -->\n'
                    'Import upstream commit `%s` from `%s` into this fork.\n\n'
                    'Regression checks run without write credentials. Passing updates '
                    'merge automatically using a merge commit. Conflicts or failing '
                    'checks leave this PR open for repair. Workflow/control changes '
                    'require manual review.\n\n'
                    'For Codex repair instructions, see [UPSTREAM.md]'
                    '(https://github.com/%s/blob/master/UPSTREAM.md). '
                    'No deployment is performed.') % (upstream, upstream, UPSTREAM, REPO)
            pr = api.request(endpoint('/pulls'), 'POST', {
                'head': branch, 'base': BASE,
                'title': 'Merge upstream ShokoRelay updates (%s)' % upstream[:12], 'body': body,
            })
            pr = api.request(endpoint('/pulls/%s' % pr['number']))
    if not eligible(pr):
        return {}
    head, base = sha(pr['head']['sha']), sha(pr['base']['sha'])
    disable_auto(api, pr)
    status(api, head, 'pending', 'Checking this exact PR revision against master')
    reason = ''
    if paused(pr):
        reason = 'Update is paused or draft'
    elif pr.get('mergeable') is False:
        reason = 'Merge conflict; merge current master into this PR branch'
    elif not ancestor(api, base, head):
        reason = 'PR branch must include current master before validation'
    elif is_upstream(pr) and not ancestor(api, MARKER.findall(pr['body'])[0], head):
        reason = 'PR no longer contains its original upstream commit'
    return {'pr': str(pr['number']), 'head': head, 'base': base,
            'ready': str(not reason).lower(), 'reason': reason}


def finish(api, number, head, base, result, reason=''):
    pr = api.request(endpoint('/pulls/%s' % int(number)))
    if not eligible(pr):
        return
    if pr['head']['sha'] != sha(head) or pr['base']['sha'] != sha(base):
        status(api, head, 'error', 'PR head or base changed; rerun validation')
        raise RuntimeError('Refusing to merge an untested head/base revision')
    if paused(pr):
        disable_auto(api, pr)
        status(api, head, 'pending', 'Paused; remove sync-pause or mark ready, then rerun')
        return
    if result != 'success':
        disable_auto(api, pr)
        reason = reason or 'Regression checks did not pass'
        status(api, head, 'failure', reason)
        comment(api, pr, reason)
        return
    if not ancestor(api, base, head):
        raise RuntimeError('Tested PR does not include current master')
    automatic = is_upstream(pr)
    if automatic:
        upstream = MARKER.findall(pr['body'])[0]
        if not ancestor(api, upstream, head):
            raise RuntimeError('Original upstream commit is missing')
        files = api.pages(endpoint('/pulls/%s/files' % pr['number']))
        automatic = not any(controlled(item['filename']) or
                            controlled(item.get('previous_filename', '')) for item in files)
    if automatic:
        auto_merge(api, pr, True)
    else:
        disable_auto(api, pr)
    # Native strict branch protection keeps the base-current check effective
    # even if master changes after our last read. Publish success only last.
    status(api, head, 'success', 'Trusted regression checks passed against current master')
    if is_upstream(pr) and not automatic:
        comment(api, pr, 'Automation or instructions changed; manual review required')
    print('Validation passed; ' + ('native auto-merge enabled' if automatic else 'manual merge available'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'finish'))
    args = parser.parse_args()
    if os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise RuntimeError('This automation is restricted to ' + REPO)
    api = GitHub()
    if args.mode == 'prepare':
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        number = event.get('pull_request', {}).get('number')
        outputs = prepare(api, number)
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            for key, value in outputs.items():
                if '\n' in value or '\r' in value:
                    raise RuntimeError('Invalid workflow output')
                stream.write('%s=%s\n' % (key, value))
    else:
        finish(api, os.environ['PR_NUMBER'], os.environ['TESTED_HEAD'], os.environ['TESTED_BASE'],
               os.environ['CHECK_RESULT'], os.environ.get('PREPARE_REASON', ''))


if __name__ == '__main__':
    main()
