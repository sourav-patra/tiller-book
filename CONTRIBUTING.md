# Contributing to tiller-book

tiller-book is built with its own rules. Every change is a unit, and every unit runs the same way.

## How a unit runs

1. Plan. Write `plans/<id>.toml`: an `id`, a `title`, the `allowed_paths` the unit may change and `min_held_out_cases`. The file must validate against `tiller_book/schemas/plan.schema.json`. An entry in `allowed_paths` that ends in `/` is a directory prefix; any other entry is one exact file. Open it as a plan-class pull request, in which every changed path is a `plans/<id>.toml` file directly under `plans/`.
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

## Writing docs

The README is the front door: a stranger decides in a minute whether to try the project.

- Order: the project name and a one-line promise, status badges from GitHub, and a figure of the project working, all before the first section. Then the headings "Why", "Features", "Quick start" and "Docs". Under "Why", state the reader's problem with one line of evidence. Number the quick-start steps; run each one and end it on a check the reader can run. Put reference detail behind links.
- Keep paragraphs to at most 60 words, most under 25. Put detail in lists, tables or linked pages.
- Each sentence states one thing a reader can check. Name who does what, and state errors as cause and fix. No filler words, no "etc.", no dashes joining clauses, no "not X but Y", no sales adjectives.
- Explain a technical term the first time it appears, or link to where it is explained. Keep each fact in one place and link to it elsewhere.
- Every number is measured, or marked "not measured" with the command that would measure it. Name the source of each claim, and keep observed, reported and planned behaviour apart.
- Use at least two distinct rendered figures that answer different questions, in one style. Badges, logos and repeated images do not count. Give each figure labels, alt text and a caption stating its conclusion and limits; colour never carries meaning alone. Use animation when motion explains the task. Keep each diagram as one plain-text SVG in the repository, edited directly, with system fonts and no external resources; update any derived image when its SVG changes. Never paste diagram source or ASCII boxes into the README.
- Check what each figure shows against the source revision, and look at it at reading size. Record both checks; keep unperformed checks pending.
- Keep the status, the key evidence and the main limits next to the claims they qualify. Never include secrets, tokens, personal data or paths outside the project.

Before opening a pull request, run `python scripts/readme_lint.py README.md`; CI runs it on every pull request. Passing the lint does not mean the README follows every rule above. A reviewer checks every rule above and that links open without signing in. Then someone unfamiliar with the project, without help, says its audience, problem and status within a minute, and after reading, its input, output, the decision it supports, the first action, the evidence and the main limits, and explains the figures. Record their answers and what they misread, fix it and ask again. Keep the GitHub sidebar current: description, a working website or docs link, 5 to 10 relevant topics, a social preview image, and a release for each published version. If the lint rejects correct text, open an issue about the lint; do not rewrite correct text to pass it.

## Starter issues

These three are open for anyone. Each one starts with a plan, like any unit.

### 1. Skill-necessity study

How relevant are agent skills, and how much effort should go into improving them? Pick one skill and measure a set of tasks with it and without it.

- Name the comparison before the first run.
- Run each arm at least five times.
- Seal the held-out cases by recording their hash before any change is written.
- Use at least the plan's `min_held_out_cases`, a required field that this repository's plans set to 20. A result from fewer cases is marked provisional.
- Report the scores and the model tokens per accepted change for both arms, with a receipt for each run.

The study may show that the skill is not needed at all. That is a valid result.

### 2. A checker for another role

Write one checker for DevOps or for product work. Examples from [VISION.md](VISION.md):

- DevOps: no secret sits in config; an infrastructure plan destroys nothing.
- Product: every requirement document has its required sections; every requirement has an acceptance criterion; no open TODO remains.

A checker is a script with no model in it. It prints one PASS or FAIL line, exits 0 or 1, and reports "could not run" with the reason when it cannot run. Register it in `tiller_book/checks/registry.py` so `tlb check run` runs it. Include tests for a pass, a failure and a case where it cannot run.

### 3. Receipt viewer

Write a command that reads `receipts/<id>.json` and prints a short summary a person can read in a minute: the unit, the runner, the commits, each check with its status, each model call with its tokens and cost, and every `not_measured` claim with its command. It validates the receipt against `tiller_book/schemas/receipt.schema.json` first, exits 1 on an invalid receipt, and calls no model.
