# How tiller-book works

The figures are on the [README](https://github.com/sourav-patra/tiller-book/blob/main/README.md#how-it-works). This page is the detail behind them.

## Who it is for

Everyone who works with agents and code, whatever their role: developers, DevOps, QA, product and design.

tiller-book needs three things from the work: a plan to sign, a fact a script can check, and a commit to point a receipt at. Code meets all three, and so does any work kept as files under version control.

| Role | Work in the repository | A checker could decide |
|---|---|---|
| Developer | Code and tests | Tests pass; changed paths stay inside the plan |
| DevOps | Infrastructure as code, pipelines | The infrastructure plan destroys nothing; no secret sits in config; the policy check exits 0 |
| QA | Test plans and suites | Every acceptance criterion in the plan maps to a test; the run's exit codes are in the receipt |
| Product | Inception and requirement documents | Required sections exist; every requirement has an acceptance criterion; no open TODO |
| Design | Design tokens and component specs | Tokens parse; colour pairs meet the contrast ratio; every specified component has its tokens |

Work that lives only in a tool outside the repository, such as a design canvas or a slide deck, gets checked only as far as that tool exports files.

Version 0.1 is built and proven on code first. The checkers in this release are for code. The other roles follow as their checkers are written, and each new checker is a good first contribution: see [CONTRIBUTING.md](https://github.com/sourav-patra/tiller-book/blob/main/CONTRIBUTING.md).

## Principle

A script decides whatever a script can decide. A model is called only for what no script can.

Model thinking costs money, and its price and availability can change quickly. tiller-book spends it only where nothing cheaper does the job. Its checkers are the fast first line. The measure of success is model tokens per accepted change.

## Three concepts

### Plan

A signed plan for one bounded change. A plan is `plans/<id>.toml` with an `id`, a `title`, `allowed_paths` and `min_held_out_cases`.

It counts only when a commit signed with a key in `.github/allowed_signers` brought its exact text onto main. A unit writes only inside the paths its plan names.

### Review

An independent reviewer, never the agent that built the change, plus checkers.

A checker is a script with no model in it. It decides one yes-or-no fact from what is in the repository, reports a reason on failure, and reports "could not run" with the reason when it cannot run.

A check that did not run counts as a failure. In this release the checkers are enforced and the reviewer's identity is not.

### Learning

Every miss becomes a lesson, filed as a GitHub issue.

A signed plan then makes one change to an artefact the harness can change, such as a skill, a checker, a prompt, a retrieval setting or a guardrail.

The change is measured with and without on the same held-out cases and kept only if it scores no worse.

None of this is built in this release: plans record `min_held_out_cases`, and nothing runs a measurement yet.

## Proof

Every unit leaves a receipt, `receipts/<id>.json`, which must validate against `tiller_book/schemas/receipt.schema.json`.

A receipt records who ran the unit, the commits it started from and produced, the model calls it made with their input and output tokens and cost, the checks it ran with their exit codes, what was refused or blocked, and where the evidence is.

A claim that was not measured goes in `not_measured` with the command that would measure it. A model call with a null cost needs such an entry.

The receipt is the last commit of a unit and changes nothing else. Its `commits.head` names that commit's parent, and its `commits.start` names the merge base with `origin/main`.

## Why an agent cannot widen its own limit

The checks read the limit from `origin/main` and the work from the branch, so a plan edited on the branch cannot widen the limit for that check.

The edit counts as one more changed path: in a build it fails unless the signed plan allows that path. A change made only of plan files passes these checks, and such a plan counts only once a signed commit brings it onto main.

All of this depends on who can merge, which tiller-book does not control.
