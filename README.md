# tiller-book

Status: 0.1.0-alpha. Review identity from a CI run, CI workflows read from main, and lesson filing are not enforced yet. They are planned for 0.1.

An agent's word is not evidence. tiller-book makes every change follow a signed plan, pass independent review and checkers, and leave a record anyone can verify.

Plan, review, learn. Every step leaves proof.

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

Review. An independent reviewer, never the agent that built the change, plus checkers. A checker is a script with no model in it. It decides one yes-or-no fact from what is in the repository, prints the failing line on a no, and reports "could not run" with the reason when it cannot run. A check that did not run counts as a failure. In this release the checkers are enforced and the reviewer's identity is not.

Learning. Every miss becomes a lesson, filed as a GitHub issue. A signed plan then makes one change to an artefact the harness can change, such as a skill, a checker, a prompt, a retrieval setting or a guardrail. The change is measured with and without on the same held-out cases and kept only if it scores no worse. None of this is built in this release: plans record `min_held_out_cases`, and nothing runs a measurement yet.

## Proof

Every unit leaves a receipt, `receipts/<id>.json`, which must validate against `schemas/receipt.schema.json`. A receipt records who ran the unit, the commits it started from and produced, the model calls it made with their input and output tokens and cost, the checks it ran with their exit codes, what was refused or blocked, and where the evidence is. A claim that was not measured goes in `not_measured` with the command that would measure it. A model call with a null cost needs such an entry.

The receipt is the last commit of a unit and changes nothing else. Its `commits.head` names that commit's parent, and its `commits.start` names the merge base with `origin/main`.

## What is enforced now and what is not yet

| Item | Status | What it does | Command | Code |
|---|---|---|---|---|
| Signed plans | Enforced now | Fails unless the plan is on the ref, valid against `schemas/plan.schema.json`, and last written by a commit signed with a key in `.github/allowed_signers` on `origin/main` | `tlb plan verify <id>` | `tiller_book/plan/verify.py` |
| Path scope from main | Enforced now | Fails if the unit branch changes a path outside `allowed_paths` of its plan on `origin/main`; a build that edits its own plan fails too | run by `tlb check run` | `tiller_book/checks/floor/path_scope.py` |
| Receipt check | Enforced now | Fails unless the last commit changes only `receipts/<id>.json`, the receipt validates, and it names that commit's parent and the merge base | run by `tlb check run` | `tiller_book/checks/floor/receipt.py` |
| Fail-closed runner | Enforced now | Runs the registered checks (tests, gitleaks leak scan, path scope, receipt); a failure, timeout, missing tool or command that cannot start counts as a failure, and it exits 0 only if every required check passed | `tlb check run` | `tiller_book/checks/__init__.py`, `tiller_book/checks/registry.py` |
| Release gate | Enforced now | Deny-list on the tree and history, author and committer identities, gitleaks, the `VISION.md` lock, and `tlb check run` on `origin/main`; a missing tool or deny-list file is a failure | `tlb release gate --denylist PATH` | `tiller_book/release/` |
| Review identity from a CI run | Not yet, planned for 0.1 | Today nothing checks who reviewed a change; a review listed in a receipt is text, and text is not identity | | |
| CI workflows read from main | Not yet, planned for 0.1 | Today the repository has no CI workflow, so no check is a required status check on main; each check counts only when someone runs it | | |
| Lesson filing | Not yet, planned for 0.1 | Today misses are not filed as lessons and no measurement runs | | |

[VISION.md](VISION.md) sets the floor for 0.1: each gate a required status check on main, with no bypass, run from main. This release does not reach that floor yet. The known limits below say where it falls short.

## Known limits

- CODEOWNERS only requests a review from the owner and enforces nothing.
- The ruleset on main keeps the owner's bypass actors, so an admin push skips the pull-request gates, though `tlb plan verify` still checks plan signatures.
- The receipt check proves the receipt's shape and its binding to the head commit, not that the listed checks ran.
- A diff fed to a model reviewer can steer its verdict, so review is never the only gate.
- Token counts and costs in a receipt are reported by the caller, because `tlb receipt write` cannot see a model session.
- With the default checkout, a GitHub `pull_request` event checks out a merge ref, so CI must check out the pull request's head commit for the receipt check.
- A run that stalls or fails has no watchdog and no escalation, and shows up only as a missing receipt.
- The schemas load from the repository checkout, so only an editable install finds them.

## Quick start

You need Python 3.11 or later, git, `ssh-keygen` and `gitleaks` on `PATH`, and a full clone (not shallow) with `origin` pointing at the repository. A missing tool makes its check fail; nothing is skipped.

From the root of a clone:

```sh
pip install -e ".[test]"
tlb plan verify U1
tlb check run
```

The `[test]` extra installs pytest, which the `tests` check runs. `tlb plan verify U1` prints `PASS` when `plans/U1.toml` on `origin/main` is valid and signed. `tlb check run` prints one line per check and a verdict, and exits 0 only if every required check passed.

To finish a unit on a branch named `unit/<id>`, write its receipt, commit it alone, and run the checks again:

```sh
tlb receipt write <id> --agent <agent> --model <model> --model-call <model>,<input tokens>,<output tokens>,<cost in USD or ->
git add receipts/<id>.json
git commit -m "receipt: <id>"
tlb check run
```

## Commands

- `tlb plan verify <id> [--ref REF] [--signers-ref REF] [--repo PATH]`: exits 0 only if `plans/<id>.toml` on the ref (default `origin/main`) is valid and owner-signed. The signers file is read from `--signers-ref` (default `origin/main`).
- `tlb check run [--json] [--repo PATH]`: runs every registered check and exits 0 only if every required check passed. `--json` prints the results as receipt `checks[]` items.
- `tlb receipt write <unit>`: writes `receipts/<unit>.json` with `commits.start` set to the merge base with `origin/main` and `commits.head` set to `HEAD`. It runs every registered check except `receipt` and records the results, and it refuses to write a receipt that fails the schema or to describe uncommitted changes. Options:
  - `--model-call MODEL,INPUT_TOKENS,OUTPUT_TOKENS,COST_USD`, repeatable; a cost of `-` means not measured and adds a `not_measured` entry;
  - `--check-file FILE`, a JSON list of extra `checks[]` items, such as review rounds;
  - `--evidence LOCATION=WHAT`, repeatable;
  - `--not-measured CLAIM=COMMAND`, repeatable;
  - `--agent` and `--model`, the runner.
- `tlb release gate --denylist PATH`: runs the release steps in order, prints one PASS or FAIL line each, and exits 0 only if all pass. The deny-list file stays outside the repository. A deny-list hit is reported by count, never by the matched text.

## Why not X

These projects work on nearby problems. Each row describes the project in the terms of its own README, checked on 1 Nov 2026.

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

## Licence

MIT. See [LICENSE](LICENSE).
