# Maintaining this fork

`master` is the maintained patched legacy ShokoRelay bundle. The updater checks
`natyusha/ShokoRelay.bundle`'s `master` daily at 10:37 UTC and can also be run
from **Actions → Upstream synchronization → Run workflow**.

Use this workflow to update the patched branch. A forced fork synchronization
can replace fork-specific commits; the updater preserves them through ordinary
merge commits and never force-pushes.

The updater opens one PR in this fork, using `upstream-sync/<full upstream
SHA>`. It merges the maintained branch into that candidate when possible,
preserving upstream history. It never force-pushes or replaces an open PR
with a newer upstream revision. Further upstream commits wait until that PR
is merged or closed. A deliberately closed revision is not proposed again;
reopen the PR to retry it.

The scheduled workflow runs validation itself, so bot-created PRs do not
depend on a second workflow being approved. PR updates also trigger trusted
validation, including repairs pushed by an agent. GitHub's native auto-merge
uses merge commits after the required `relay/upstream-validation` status
passes. Strict branch protection requires the candidate to include current
`master`; a changed head/base never inherits an earlier successful result.

Validation runs the six regression suites from the trusted maintained branch
against the candidate's `Contents`, plus Python 2.7 grammar checks. Candidate
test edits cannot weaken those checks. These are offline mocked checks,
not native Plex acceptance. Live installation remains a separate operation.

## Exceptions and Codex repairs

Conflicts and failing/cancelled checks leave the PR open, with a failing
required status and a deduplicated explanation linking to the Actions logs.
No code is deployed. The scheduler keeps the candidate branch intact so an
agent's repairs are preserved.

Connect this repository to Codex and enable its GitHub integration in
[Codex settings](https://chatgpt.com/codex/settings). Repository access alone
does not prove that cloud task execution is configured for your account.
Then post this as a **new comment yourself** on the blocked PR:

```text
@codex Resolve the merge conflicts or failing CI on this upstream-sync PR.
Merge current master into this PR branch, preserving the upstream commit
and this fork's SeriesID matching, Windows paths, stacking and airdate fixes.
Run the six regression suites and Python 2.7 syntax checks. Push repairs to
this same branch. Do not weaken tests or change automation to obtain green
checks. Do not deploy, scan libraries or access live services or credentials.
```

Codex can start a cloud task from a PR comment and push fixes when its
integration has permission. See the
[official Codex GitHub documentation](https://learn.chatgpt.com/docs/third-party/github). This updater does not
invoke a paid agent automatically or require an OpenAI API key in Actions.

After the repair is pushed, checks rerun and passing eligible updates merge
automatically. If master moved, the agent must merge current master first.
To pause deliberately, convert the PR to a draft or add a `sync-pause` label;
mark ready/remove that label and rerun the workflow to resume.

Changes to `.github/`, `scripts/`, `tests/` or `AGENTS.md` are tested but need manual
review/merge, because they can change the updater's own authority or checks.
A rewritten upstream history, API failure or missing/invalid result fails
the workflow rather than claiming the fork is current. Scheduled workflows
in public repositories can be disabled by GitHub after 60 days without
repository activity; check Actions if upstream has been quiet that long.

## Repository setup

- Enable Actions to create pull requests; keep default workflow tokens read-only.
- Enable repository auto-merge and merge commits.
- Protect master: require `relay/upstream-validation` from GitHub Actions,
  require the branch to be current, prohibit force pushes/deletion. No human
  approval is required for routine passing upstream imports.
- Keep the workflow on the default branch. Only trusted master scripts run
  with write credentials; candidate code runs in a separate read-only job
  without persisted checkout credentials or service secrets.
- Use the Actions logs/PR status to monitor exceptions. A green no-update
  run is not a security audit or evidence that upstream has fixed every issue.
