# Status and limits

Status: 0.1.0-alpha.

## What is enforced now and what is not yet

| Item | Status | What it does | Command | Code |
|---|---|---|---|---|
| Signed plans | Enforced now | Fails unless the plan is on the ref, valid against `tiller_book/schemas/plan.schema.json`, and last written by a commit signed with a key in `.github/allowed_signers` on `origin/main` | `tlb plan verify <id>` | `tiller_book/plan/verify.py` |
| Path scope from main | Enforced now | For build changes, verifies the signed plan on `origin/main` and fails on any path outside its `allowed_paths`; a build's edit to its own plan counts as one more changed path and cannot widen the limit. No changes, and plan-class changes (only `plans/<id>.toml` files), pass without this validation | run by `tlb check run` | `tiller_book/checks/floor/path_scope.py` |
| Receipt check | Enforced now | For build changes, requires a valid signed plan and a receipt-only last commit whose receipt validates and names its parent and the merge base. No changes, and plan-class changes, pass without receipt validation | run by `tlb check run` | `tiller_book/checks/floor/receipt.py` |
| Fail-closed runner | Enforced now | Runs the registered checks (tests, gitleaks leak scan, path scope, receipt); a failure, timeout, missing tool or command that cannot start counts as a failure, and it exits 0 only if every required check passed | `tlb check run` | `tiller_book/checks/__init__.py`, `tiller_book/checks/registry.py` |
| Release gate | Enforced now | Deny-list on the HEAD tree and every reachable object, noreply author, committer and tagger addresses, gitleaks, the `VISION.md` lock, and the registered checks, with `HEAD` equal to `origin/main`; a missing tool or deny-list file is a failure | `tlb release gate --denylist PATH` | `tiller_book/release/` |
| Review identity from a CI run | Not yet, planned for 0.1 | Today nothing checks who reviewed a change; a review listed in a receipt is text, and text is not identity | | |
| CI workflows read from main | Not yet, planned for 0.1 | Today the only workflow is docs-lint, which runs the README lint. No check is a required status check on main yet, so each `tlb` check counts only when someone runs it | | |
| Lesson filing | Not yet, planned for 0.1 | Today misses are not filed as lessons and no measurement runs | | |

[VISION.md](https://github.com/sourav-patra/tiller-book/blob/main/VISION.md) sets the floor for 0.1: each gate a required status check on main, with no bypass, run from main. This release does not reach that floor yet. The known limits below say where it falls short.

## Known limits

- CODEOWNERS only requests a review from the owner and enforces nothing.
- tiller-book does not control who can merge. An agent that can merge to main can change `.github/allowed_signers` and sign its own plans, so keep the merge right with a person.
- The checks read plans and signing keys from the local `origin/main` reference and do not authenticate it against GitHub. An agent that controls the machine can change that reference or the checker code, so run the checks where it cannot.
- A PASS does not mean the change is correct. A person still reads it and decides.
- The ruleset on main keeps the owner's bypass actors, so an admin push skips the pull-request gates, though `tlb plan verify` still checks plan signatures.
- Path scope compares the merge base with `HEAD`, so a path changed and then reverted on the branch does not appear.
- The receipt check proves the receipt's shape and its binding to the head commit, not that the listed checks ran.
- A diff fed to a model reviewer can steer its verdict, so review is never the only gate.
- Token counts and costs in a receipt are reported by the caller, because `tlb receipt write` cannot see a model session.
- With the default checkout, a GitHub `pull_request` event checks out a merge ref, so CI must check out the pull request's head commit for the receipt check.
- `tlb receipt write` always writes an empty `refusals` list and has no option to add one, so a written receipt records no refusals unless someone edits it by hand.
- A plan may list `model_calls`, and nothing enforces that list yet.
- There is no watchdog or escalation for a stalled or failed run; the receipt writer records failing checks in the receipt.
- The release gate skips signature blocks in commit headers and tag trailers, because their random text matches short deny-list terms by chance. A commit crafted to hide text inside a fake signature header would pass the deny-list step.

Skipped or not checked: only the docs-lint workflow has run on GitHub Actions; the `tlb` checks have not. Model tokens per accepted change have not been measured. tiller-book has been run on this repository and on throwaway test repositories only.
