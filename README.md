# tiller-book

[![Status: 0.1.0-alpha](https://img.shields.io/badge/status-0.1.0--alpha-orange)](#what-is-enforced-now-and-what-is-not-yet)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![Python 3.11 or later](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Checks run locally, no CI yet](https://img.shields.io/badge/checks-run%20locally%2C%20no%20CI%20yet-lightgrey)](#known-limits)

Status: 0.1.0-alpha. Review identity from a CI run, CI workflows read from main, and lesson filing are not enforced yet. They are planned for 0.1.

An agent's word is not evidence. You give tiller-book a plan a person signed and a branch an agent built. It gives you PASS or FAIL for each check and a receipt for the change, so you can decide whether to merge. It runs locally through the `tlb` command. Independent review is part of the contribution process, but this release does not verify reviewer identity or require checks before merging.

## How a change moves

![Four lanes: owner, agent, independent reviewer and the tlb command. The agent writes a plan, the owner signs and merges it, and tlb plan verify checks it. The agent builds on a unit branch, a reviewer who is not the builder reviews it, and the agent commits a receipt alone. tlb check run then runs four checks. A failure returns to the build, and a pass goes to the owner, who merges.](docs/change-flow.svg)

The agent never decides that its own work passed: scripts decide steps 3 and 7, and a person decides steps 2 and 8. Step 5 is a process in this release, because nothing checks who the reviewer was, and no CI gate forces anyone to run steps 3 and 7.

## Quick start

You need Python 3.11 or later, git, `ssh-keygen` and `gitleaks` on `PATH`, and a full clone (not shallow) with `origin` pointing at the repository. The release gate also needs `grep` on `PATH`. A missing tool makes its check fail; nothing is skipped.

From the root of a clone of this repository:

```sh
pip install -e ".[test]"
tlb plan verify U1
tlb check run
```

The `[test]` extra installs pytest, which the `tests` check runs. `tlb plan verify U1` prints `PASS` when `plans/U1.toml` on `origin/main` is valid and signed. `tlb check run` prints one line per check and a verdict, and exits 0 only if every required check passed.

A passing run on main prints the lines below. The test suite takes about 5 minutes (measured on one Windows machine).

```text
PASS tests: exit 0
PASS leak-scan: exit 0
PASS path-scope: exit 0
PASS receipt: exit 0
PASS: all 4 required checks passed
```

## Use it in your own repository

Install `tlb` into your project's environment. To pin a release, replace `main` with its tag.

```sh
pip install "tiller-book[test] @ git+https://github.com/sourav-patra/tiller-book.git@main"
```

1. Add three things to main:
   - `.github/allowed_signers`, with one line for each signer: `<commit email> <key type> <public key>`;
   - at least one pytest test, because the `tests` check runs `python -m pytest -q`;
   - a `.gitignore` with `__pycache__/` and `.pytest_cache/`, because the receipt writer refuses untracked files.
2. Write the plan as `plans/demo-1.toml`. A unit's plan must allow its own receipt.

   ```toml
   id = "demo-1"
   title = "Add a greeting"
   allowed_paths = ["src/", "receipts/demo-1.json"]
   min_held_out_cases = 20
   ```

3. Sign the plan commit and put it on main. A squash or rebase merge rewrites the commit and loses the signature, so use a merge commit if it goes through a pull request.

   ```sh
   git add plans/demo-1.toml
   git -c gpg.format=ssh -c user.signingkey=<path to your signing key> commit -S -m "plan: demo-1"
   git push origin main
   tlb plan verify demo-1
   ```

   ```text
   PASS: plans/demo-1.toml at origin/main is valid and signed by a key in .github/allowed_signers at origin/main
   ```

4. Build on a branch named after the plan, commit the change, write the receipt, commit it alone, and run the checks.

   ```sh
   git switch -c unit/demo-1
   # make the change inside allowed_paths and commit it
   tlb receipt write demo-1 --agent <agent> --model <model> --model-call <model>,<input tokens>,<output tokens>,<cost in USD or ->
   git add receipts/demo-1.json
   git commit -m "receipt: demo-1"
   tlb check run
   ```

   The last command prints the same five PASS lines as the quick start. If the diff from the merge base to `HEAD` holds a path outside `allowed_paths`, the path-scope check fails with the path named:

   ```text
   FAIL path-scope: exit 1: FAIL: outside allowed_paths of plans/demo-1.toml at origin/main: outside.txt
   ```

## Who it is for

Everyone who works with agents and code, whatever their role: developers, DevOps, QA, product and design. tiller-book needs three things from the work: a plan to sign, a fact a script can check, and a commit to point a receipt at. Code meets all three, and so does any work kept as files under version control.

| Role | Work in the repository | A checker could decide |
|---|---|---|
| Developer | Code and tests | Tests pass; changed paths stay inside the plan |
| DevOps | Infrastructure as code, pipelines | The infrastructure plan destroys nothing; no secret sits in config; the policy check exits 0 |
| QA | Test plans and suites | Every acceptance criterion in the plan maps to a test; the run's exit codes are in the receipt |
| Product | Inception and requirement documents | Required sections exist; every requirement has an acceptance criterion; no open TODO |
| Design | Design tokens and component specs | Tokens parse; colour pairs meet the contrast ratio; every specified component has its tokens |

Work that lives only in a tool outside the repository, such as a design canvas or a slide deck, gets checked only as far as that tool exports files.

Version 0.1 is built and proven on code first. The checkers in this release are for code. The other roles follow as their checkers are written, and each new checker is a good first contribution: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Principle

A script decides whatever a script can decide. A model is called only for what no script can.

Model thinking costs money, and its price and availability can change quickly. tiller-book spends it only where nothing cheaper does the job. Its checkers are the fast first line. The measure of success is model tokens per accepted change.

## Three concepts

Plan. A signed plan for one bounded change. A plan is `plans/<id>.toml` with an `id`, a `title`, `allowed_paths` and `min_held_out_cases`. It counts only when a commit signed with a key in `.github/allowed_signers` brought its exact text onto main. A unit writes only inside the paths its plan names.

Review. An independent reviewer, never the agent that built the change, plus checkers. A checker is a script with no model in it. It decides one yes-or-no fact from what is in the repository, reports a reason on failure, and reports "could not run" with the reason when it cannot run. A check that did not run counts as a failure. In this release the checkers are enforced and the reviewer's identity is not.

Learning. Every miss becomes a lesson, filed as a GitHub issue. A signed plan then makes one change to an artefact the harness can change, such as a skill, a checker, a prompt, a retrieval setting or a guardrail. The change is measured with and without on the same held-out cases and kept only if it scores no worse. None of this is built in this release: plans record `min_held_out_cases`, and nothing runs a measurement yet.

## Proof

Every unit leaves a receipt, `receipts/<id>.json`, which must validate against `tiller_book/schemas/receipt.schema.json`. A receipt records who ran the unit, the commits it started from and produced, the model calls it made with their input and output tokens and cost, the checks it ran with their exit codes, what was refused or blocked, and where the evidence is. A claim that was not measured goes in `not_measured` with the command that would measure it. A model call with a null cost needs such an entry.

The receipt is the last commit of a unit and changes nothing else. Its `commits.head` names that commit's parent, and its `commits.start` names the merge base with `origin/main`.

## Why an agent cannot widen its own limit

![The tlb checks read the plan and the signers file from origin/main, and read the changed paths and the receipt from the unit branch. A copy of the plan edited on the branch is not the one the checks use, so it cannot widen the limit. The boundary holds only while the agent cannot merge to main.](docs/trust-boundary.svg)

The checks read the limit from `origin/main` and the work from the branch, so a plan edited on the branch cannot widen the limit for that check. The edit counts as one more changed path: in a build it fails unless the signed plan allows that path. A change made only of plan files passes these checks, and such a plan counts only once a signed commit brings it onto main. All of this depends on who can merge, which tiller-book does not control.

## What is enforced now and what is not yet

| Item | Status | What it does | Command | Code |
|---|---|---|---|---|
| Signed plans | Enforced now | Fails unless the plan is on the ref, valid against `tiller_book/schemas/plan.schema.json`, and last written by a commit signed with a key in `.github/allowed_signers` on `origin/main` | `tlb plan verify <id>` | `tiller_book/plan/verify.py` |
| Path scope from main | Enforced now | For build changes, verifies the signed plan on `origin/main` and fails on any path outside its `allowed_paths`; a build's edit to its own plan counts as one more changed path and cannot widen the limit. No changes, and plan-class changes (only `plans/<id>.toml` files), pass without this validation | run by `tlb check run` | `tiller_book/checks/floor/path_scope.py` |
| Receipt check | Enforced now | For build changes, requires a valid signed plan and a receipt-only last commit whose receipt validates and names its parent and the merge base. No changes, and plan-class changes, pass without receipt validation | run by `tlb check run` | `tiller_book/checks/floor/receipt.py` |
| Fail-closed runner | Enforced now | Runs the registered checks (tests, gitleaks leak scan, path scope, receipt); a failure, timeout, missing tool or command that cannot start counts as a failure, and it exits 0 only if every required check passed | `tlb check run` | `tiller_book/checks/__init__.py`, `tiller_book/checks/registry.py` |
| Release gate | Enforced now | Deny-list on the HEAD tree and every reachable object, noreply author, committer and tagger addresses, gitleaks, the `VISION.md` lock, and the registered checks, with `HEAD` equal to `origin/main`; a missing tool or deny-list file is a failure | `tlb release gate --denylist PATH` | `tiller_book/release/` |
| Review identity from a CI run | Not yet, planned for 0.1 | Today nothing checks who reviewed a change; a review listed in a receipt is text, and text is not identity | | |
| CI workflows read from main | Not yet, planned for 0.1 | Today the repository has no CI workflow, so no check is a required status check on main; each check counts only when someone runs it | | |
| Lesson filing | Not yet, planned for 0.1 | Today misses are not filed as lessons and no measurement runs | | |

[VISION.md](VISION.md) sets the floor for 0.1: each gate a required status check on main, with no bypass, run from main. This release does not reach that floor yet. The known limits below say where it falls short.

## Known limits

- CODEOWNERS only requests a review from the owner and enforces nothing.
- tiller-book does not control who can merge. An agent that can merge to main can change `.github/allowed_signers` and sign its own plans, so keep the merge right with a person.
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

## Commands

- `tlb plan verify <id> [--ref REF] [--signers-ref REF] [--repo PATH]`: exits 0 only if `plans/<id>.toml` on the ref (default `origin/main`) is valid and owner-signed. The signers file is read from `--signers-ref` (default `origin/main`).
- `tlb check run [--json] [--repo PATH]`: runs every registered check and exits 0 only if every required check passed. `--json` prints the results as receipt `checks[]` items.
- `tlb receipt write <unit>`: writes `receipts/<unit>.json` with `commits.start` set to the merge base with `origin/main` and `commits.head` set to `HEAD`. It runs every registered check except `receipt`, which cannot pass before the receipt commit exists, and records the results, including failures. It validates the receipt before writing, writes it in one step, and refuses uncommitted changes other than an untracked receipt for this unit. Options:
  - `--model-call MODEL,INPUT_TOKENS,OUTPUT_TOKENS,COST_USD`, repeatable; a cost of `-` means not measured and adds a `not_measured` entry;
  - `--check-file FILE`, a JSON list of extra `checks[]` items, such as review rounds;
  - `--evidence LOCATION=WHAT`, repeatable;
  - `--not-measured CLAIM=COMMAND`, repeatable;
  - `--agent` and `--model`, the runner;
  - `--skip-check NAME`, repeatable, `tests` or `receipt`; `receipt` is always skipped, and each skipped check is listed in `not_measured`;
  - `--repo PATH`, the repository, default the current directory.
- `tlb release gate --denylist PATH [--repo PATH]`: requires `HEAD` to equal `origin/main` in a full clone without grafts; it does not switch to it. It then checks the deny-list against the HEAD tree and every object reachable from every ref, author, committer and tagger addresses, gitleaks on the history and on every reachable blob, commit and tag, the `VISION.md` lock, and the registered checks. It prints one PASS or FAIL line per step and a final verdict, and exits 0 only if all steps pass. The deny-list file stays outside the repository. Output is counts, short hashes and fixed reasons only, never matched text, addresses or tool output.

## Why not X

These projects work on nearby problems. Each row describes the project in the terms of its own README, checked on 1 or 2 Nov 2026.

| Project | What it is |
|---|---|
| [joymin5655/Agent](https://github.com/joymin5655/Agent) | A governance harness that puts Claude Code, Codex CLI and Antigravity CLI under one policy, with security hooks, a fail-closed verifier for "done" claims and review by other vendors' models; published as one developer's own setup |
| [acgs-ai/acgs-lite](https://github.com/acgs-ai/acgs-lite) | A governance layer between agent reasoning and side effects: a proposed side effect runs only with a valid decision receipt; in beta |
| [Microsoft Agent Governance Toolkit](https://github.com/microsoft/agent-governance-toolkit) | Policy enforcement, agent identity, execution sandboxing and reliability engineering for autonomous agents; in public preview |
| [OpenHarness](https://github.com/HKUDS/OpenHarness) | An agent harness with multi-level permission modes, path rules, command deny rules, hooks and plugins |
| [ECC](https://github.com/affaan-m/ECC) | A large library of skills, hooks, memory and security tooling for Claude Code, Codex, OpenCode, Cursor and other agents |
| [OpenShell](https://github.com/NVIDIA/OpenShell) | A runtime that runs each agent in a sandbox with kernel-level limits on files, system calls and network, where the agent never sees real credentials |
| [SkillOpt](https://github.com/microsoft/SkillOpt) | An optimiser for natural-language agent skills that keeps an edit only if it improves a held-out validation score |
| [Harness2](https://github.com/google-research/harness2) | A research framework that refines an agent's harness (prompts, tools, memory, skills) task by task, with model weights fixed |
| [OpenLIT](https://github.com/openlit/openlit) | An agent engineering platform on OpenTelemetry with tracing, evaluations, guardrails, and cost and GPU monitoring |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | A framework for large language model evaluations from the UK AI Security Institute, with over 200 pre-built evaluations |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | A plugin-based agent harness with a web UI, in developer preview |
| [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model) | A plugin where a long-context agent drafts a design specification with a person and fresh zero-context subagents review it, ending at an approved specification |

## Licence

MIT. See [LICENSE](LICENSE).
