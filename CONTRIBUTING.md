# Contributing to tiller-book

tiller-book is built with its own rules. Every change is a unit, and every unit runs the same way.

## How a unit runs

1. Plan. Write `plans/<id>.toml`: an `id`, a `title`, the `allowed_paths` the unit may change and `min_held_out_cases`. The file must validate against `schemas/plan.schema.json`. An entry in `allowed_paths` that ends in `/` is a directory prefix; any other entry is one exact file. Open it as a plan-class pull request, in which every changed path is a `.toml` file under `plans/`.
2. Owner signature. The owner signs the plan commit with an SSH key listed in `.github/allowed_signers` and merges the pull request with "Create a merge commit". A squash or rebase merge rewrites the commit, so the plan loses its signature. `tlb plan verify <id>` passes once the signed plan is on main.
3. Build. Work on a branch named `unit/<id>`, made from `origin/main`, and change only paths inside the plan's `allowed_paths`. The path-scope check reads the plan from `origin/main`, so editing the plan in the build branch does not widen it.
4. Independent review. A reviewer that did not build the change, a person or a different agent, reads the change and the source. Record each review round as a `checks[]` item in the receipt.
5. Receipt-only last commit. Run `tlb receipt write <id>`, then commit `receipts/<id>.json` alone as the last commit of the branch. A code commit after it makes the receipt check fail, and the unit then needs a new receipt-only last commit. `tlb check run` on the branch must pass.
6. Merge commit. The owner merges the build pull request with "Create a merge commit", so the plan, the build commits and the receipt all stay in the history.

## Commit identity

Commits use a GitHub noreply identity, `<id>+<login>@users.noreply.github.com`, as both author and committer. Set it in the repository before your first commit:

```sh
git config user.email "<id>+<login>@users.noreply.github.com"
```

GitHub shows the address under Settings, Emails, when "Keep my email addresses private" is on.

## Starter issues

These three are open for anyone. Each one starts with a plan, like any unit.

### 1. Skill-necessity study

How relevant are agent skills, and how much effort should go into improving them? Pick one skill and measure a set of tasks with it and without it.

- Name the comparison before the first run.
- Run each arm at least five times.
- Seal the held-out cases by recording their hash before any change is written.
- Use at least the plan's `min_held_out_cases`, 20 by default. A result from fewer cases is marked provisional.
- Report the scores and the model tokens per accepted change for both arms, with a receipt for each run.

The study may show that the skill is not needed at all. That is a valid result.

### 2. A checker for another role

Write one checker for DevOps or for product work. Examples from [VISION.md](VISION.md):

- DevOps: no secret sits in config; an infrastructure plan destroys nothing.
- Product: every requirement document has its required sections; every requirement has an acceptance criterion; no open TODO remains.

A checker is a script with no model in it. It prints one PASS or FAIL line, exits 0 or 1, and reports "could not run" with the reason when it cannot run. Register it in `tiller_book/checks/registry.py` so `tlb check run` runs it. Include tests for a pass, a failure and a case where it cannot run.

### 3. Receipt viewer

Write a command that reads `receipts/<id>.json` and prints a short summary a person can read in a minute: the unit, the runner, the commits, each check with its status, each model call with its tokens and cost, and every `not_measured` claim with its command. It validates the receipt against `schemas/receipt.schema.json` first, exits 1 on an invalid receipt, and calls no model.
