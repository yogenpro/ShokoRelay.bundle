#!/usr/bin/env python3
"""Offline tests of publishing, failures, exact-revision gating and job boundaries."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sync', ROOT / 'scripts/upstream-sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)
B, H, U, OTHER = ('b' * 40, 'c' * 40, 'a' * 40, 'd' * 40)


def pull():
    return {
        'number': 7, 'node_id': 'PR_test', 'state': 'open', 'draft': False,
        'body': '<!-- relay-upstream: %s -->' % U, 'labels': [],
        'auto_merge': None, 'mergeable': True,
        'head': {'sha': H, 'ref': sync.PREFIX + U, 'repo': {'full_name': sync.REPO}},
        'base': {'sha': B, 'ref': sync.BASE, 'repo': {'full_name': sync.REPO}},
    }


class FakeGitHub:
    def __init__(self):
        self.pr = pull()
        self.calls = []
        self.pending = [self.pr]
        self.comments = []
        self.files = [{'filename': 'Contents/Code/__init__.py'}]
        self.closed = []
        self.comparisons = {}
        self.existing_branch = False
        self.merge_conflict = False
        self.graphql_error = False

    def request(self, path, method='GET', data=None):
        self.calls.append((path, method, copy.deepcopy(data)))
        if method == 'POST':
            if path == '/graphql':
                return {'errors': [{'message': 'test error'}]} if self.graphql_error else {'data': {}}
            if path.endswith('/merges') and self.merge_conflict:
                raise sync.APIError(409, 'Merge conflict')
            if path.endswith('/pulls'):
                return self.pr
            return {}
        if '/compare/' in path:
            return {'status': self.comparisons.get(path.split('/compare/')[1], 'ahead')}
        if path.endswith('/git/ref/heads/master'):
            return {'object': {'sha': U if sync.UPSTREAM in path else B}}
        if '/git/ref/heads/upstream-sync/' in path:
            if not self.existing_branch:
                raise sync.APIError(404, 'Not Found')
            return {'object': {'sha': H}}
        if path.endswith('/pulls/7'):
            return copy.deepcopy(self.pr)
        raise AssertionError('Unexpected API request: ' + path)

    def pages(self, path):
        self.calls.append((path, 'PAGES', None))
        if '/pulls?state=open' in path:
            return copy.deepcopy(self.pending)
        if '/pulls?state=closed' in path:
            return self.closed
        if path.endswith('/comments'):
            return self.comments
        if path.endswith('/files'):
            return self.files
        raise AssertionError('Unexpected paginated request: ' + path)

    def statuses(self):
        return [body['state'] for path, method, body in self.calls if '/statuses/' in path]

    def enables(self):
        return [body for path, method, body in self.calls
                if path == '/graphql' and 'enablePullRequestAutoMerge' in body['query']]


class PrepareTests(unittest.TestCase):
    def test_existing_pr_is_preserved_without_ref_or_merge_mutations(self):
        api = FakeGitHub()
        result = sync.prepare(api)
        self.assertEqual(result, {'pr': '7', 'head': H, 'base': B, 'ready': 'true', 'reason': ''})
        writes = [p for p, m, _ in api.calls if m == 'POST']
        self.assertEqual(writes, [sync.endpoint('/statuses/' + H)])

    def test_multiple_pending_prs_fail_closed(self):
        api = FakeGitHub()
        api.pending.append(pull())
        with self.assertRaisesRegex(RuntimeError, 'Multiple'):
            sync.prepare(api)
        self.assertFalse(api.statuses())

    def test_no_upstream_changes_has_no_writes(self):
        api = FakeGitHub()
        api.pending = []
        api.comparisons[U + '...' + B] = 'identical'
        self.assertEqual(sync.prepare(api), {})
        self.assertFalse(any(m == 'POST' for _, m, _ in api.calls))

    def test_new_update_creates_branch_merge_and_fork_only_pr(self):
        api = FakeGitHub()
        api.pending = []
        api.comparisons[U + '...' + B] = 'diverged'
        self.assertEqual(sync.prepare(api)['ready'], 'true')
        posts = {p: d for p, m, d in api.calls if m == 'POST'}
        self.assertEqual(posts[sync.endpoint('/git/refs')]['sha'], U)
        self.assertEqual(posts[sync.endpoint('/merges')]['head'], B)
        self.assertEqual(posts[sync.endpoint('/pulls')]['base'], 'master')
        self.assertFalse(any(sync.UPSTREAM in p for p in posts))
        self.assertNotIn('force', str(posts))

    def test_conflict_still_publishes_valid_pr_without_success(self):
        api = FakeGitHub()
        api.pending = []
        api.comparisons[U + '...' + B] = 'diverged'
        api.comparisons[B + '...' + H] = 'diverged'
        api.merge_conflict = True
        api.pr['mergeable'] = False
        result = sync.prepare(api)
        self.assertEqual(result['ready'], 'false')
        self.assertIn('conflict', result['reason'])
        self.assertIn(sync.endpoint('/pulls'), [p for p, m, _ in api.calls if m == 'POST'])
        self.assertEqual(api.statuses(), ['pending'])

    def test_existing_branch_after_interruption_is_not_recreated(self):
        api = FakeGitHub()
        api.pending = []
        api.existing_branch = True
        api.comparisons[U + '...' + B] = 'diverged'
        sync.prepare(api)
        self.assertNotIn(sync.endpoint('/git/refs'), [p for p, m, _ in api.calls if m == 'POST'])

    def test_closed_revision_not_reopened_by_schedule(self):
        api = FakeGitHub()
        api.pending = []
        api.closed = [{'number': 2}]
        api.comparisons[U + '...' + B] = 'diverged'
        self.assertEqual(sync.prepare(api), {})
        self.assertFalse(any(m == 'POST' for _, m, _ in api.calls))

    def test_upstream_rewrite_stops(self):
        api = FakeGitHub()
        api.pending = []
        api.comparisons[sync.ANCHOR + '...' + U] = 'diverged'
        with self.assertRaisesRegex(RuntimeError, 'known baseline'):
            sync.prepare(api)
        self.assertFalse(any(m == 'POST' for _, m, _ in api.calls))

    def test_changed_base_requires_integration(self):
        api = FakeGitHub()
        api.comparisons[B + '...' + H] = 'diverged'
        self.assertEqual(sync.prepare(api, 7)['ready'], 'false')

    def test_missing_original_upstream_is_rejected(self):
        api = FakeGitHub()
        api.comparisons[U + '...' + H] = 'diverged'
        self.assertIn('original upstream', sync.prepare(api, 7)['reason'])


class FinishTests(unittest.TestCase):
    def test_pass_enables_native_merge_before_publishing_success(self):
        api = FakeGitHub()
        sync.finish(api, 7, H, B, 'success')
        self.assertEqual(len(api.enables()), 1)
        self.assertIn('mergeMethod:MERGE', api.enables()[0]['query'])
        self.assertEqual(api.statuses(), ['success'])
        enable = next(i for i, (p, _, _) in enumerate(api.calls) if p == '/graphql')
        success = next(i for i, (p, _, _) in enumerate(api.calls) if '/statuses/' in p)
        self.assertLess(enable, success)

    def test_non_success_results_never_merge(self):
        for result in ('failure', 'cancelled', 'skipped', '', 'unknown'):
            with self.subTest(result=result):
                api = FakeGitHub()
                sync.finish(api, 7, H, B, result)
                self.assertEqual(api.statuses(), ['failure'])
                self.assertFalse(api.enables())

    def test_head_or_base_drift_never_inherits_success(self):
        for which in ('head', 'base'):
            with self.subTest(which=which):
                api = FakeGitHub()
                api.pr[which]['sha'] = OTHER
                with self.assertRaisesRegex(RuntimeError, 'untested'):
                    sync.finish(api, 7, H, B, 'success')
                self.assertEqual(api.statuses(), ['error'])
                self.assertFalse(api.enables())

    def test_pause_or_draft_keeps_required_status_pending(self):
        for kind in ('draft', 'label'):
            api = FakeGitHub()
            if kind == 'draft':
                api.pr['draft'] = True
            else:
                api.pr['labels'] = [{'name': 'sync-pause'}]
            sync.finish(api, 7, H, B, 'success')
            self.assertEqual(api.statuses(), ['pending'])
            self.assertFalse(api.enables())

    def test_control_changes_pass_tests_but_need_manual_merge(self):
        for path in ('.github/workflows/a.yml', 'scripts/a.py', 'tests/test_scanner.py', 'AGENTS.md'):
            with self.subTest(path=path):
                api = FakeGitHub()
                api.files = [{'filename': path}]
                sync.finish(api, 7, H, B, 'success')
                self.assertEqual(api.statuses(), ['success'])
                self.assertFalse(api.enables())

    def test_renaming_control_file_does_not_bypass_policy(self):
        api = FakeGitHub()
        api.files = [{'filename': 'ordinary.txt', 'previous_filename': 'scripts/upstream-sync.py'}]
        sync.finish(api, 7, H, B, 'success')
        self.assertFalse(api.enables())

    def test_ordinary_pr_gets_status_without_auto_merge(self):
        api = FakeGitHub()
        api.pr['head']['ref'] = 'feature/example'
        sync.finish(api, 7, H, B, 'success')
        self.assertEqual(api.statuses(), ['success'])
        self.assertFalse(api.enables())

    def test_graphql_failure_never_publishes_success(self):
        api = FakeGitHub()
        api.graphql_error = True
        with self.assertRaisesRegex(RuntimeError, 'Could not enable'):
            sync.finish(api, 7, H, B, 'success')
        self.assertFalse(api.statuses())

    def test_missing_upstream_or_base_never_merges(self):
        for older in (B, U):
            api = FakeGitHub()
            api.comparisons[older + '...' + H] = 'diverged'
            with self.assertRaises(RuntimeError):
                sync.finish(api, 7, H, B, 'success')
            self.assertFalse(api.enables())

    def test_exception_comments_are_deduplicated(self):
        api = FakeGitHub()
        reason = 'Regression checks did not pass'
        api.comments = [{'body': '<!-- relay-sync-exception: %s:%s -->' % (H, reason)}]
        sync.finish(api, 7, H, B, 'failure')
        self.assertFalse(any(p.endswith('/comments') and m == 'POST' for p, m, _ in api.calls))


class Boundaries(unittest.TestCase):
    def test_only_exact_owned_branch_and_marker_allow_auto_merge(self):
        for mutate in (
            lambda p: p['head'].update(repo={'full_name': 'someone/other'}),
            lambda p: p['head'].update(repo=None),
            lambda p: p.update(body=''),
            lambda p: p.update(body=p['body'] + p['body']),
            lambda p: p['head'].update(ref='upstream-sync/' + OTHER),
        ):
            pr = pull()
            mutate(pr)
            self.assertFalse(sync.is_upstream(pr))

    def test_workflow_separates_candidate_execution_from_write_jobs(self):
        content = (ROOT / '.github/workflows/upstream-sync.yml').read_text()
        prepare, rest = content.split('  regression:', 1)
        regression, finalize = rest.split('  finalize:', 1)
        self.assertIn('pull_request_target:', content)
        self.assertIn('ref: master', prepare)
        self.assertNotIn('path: candidate', prepare + finalize)
        self.assertNotIn('GH_TOKEN', regression)
        self.assertNotIn('write', regression)
        self.assertNotIn('secrets.', content)
        self.assertEqual(content.count('persist-credentials: false'), 4)
        self.assertIn('needs.regression.result', finalize)
        self.assertIn('always()', finalize)
        self.assertIn('cancel-in-progress: false', content)

    def test_only_full_shas_are_accepted(self):
        for value in ('master', 'abc', 'a' * 40 + '\n', '$(echo x)', None):
            with self.assertRaises(ValueError):
                sync.sha(value)

    def test_developer_ci_has_no_write_permissions_or_persisted_credentials(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        self.assertNotIn('write', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('GH_TOKEN', workflow)
        self.assertIn('persist-credentials: false', workflow)

    def test_pagination_limit_fails_instead_of_returning_partial(self):
        class TooMany(sync.GitHub):
            def request(self, *args):
                return [{}] * 100
        with self.assertRaisesRegex(RuntimeError, 'partial'):
            TooMany().pages('/example')


if __name__ == '__main__':
    unittest.main()
