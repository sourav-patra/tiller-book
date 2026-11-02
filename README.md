# tiller-book

Check an agent's work against a plan a person signed, and keep a receipt for every change.

[![Latest release](https://img.shields.io/github/v/release/sourav-patra/tiller-book?include_prereleases)](https://github.com/sourav-patra/tiller-book/releases)
[![Licence](https://img.shields.io/github/license/sourav-patra/tiller-book)](LICENSE)
[![Python 3.11 or later](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Checks run locally](https://img.shields.io/badge/checks-run%20locally-lightgrey)](docs/status-and-limits.md)

![Real tlb output. A commit changes config.txt, which the signed plan does not allow: path scope fails, names the file, and the run exits 1. After the fix and a committed receipt, all four checks pass and the run exits 0.](docs/demo.svg)

Real `tlb` output from a test repository: a commit outside the plan fails with the path named, and the fixed branch passes.

Status: 0.1.0-alpha. Checks run when someone runs them. No CI gate (an automatic check on GitHub) blocks a merge yet.

## Why

For anyone who lets coding agents change a repository and decides whether to merge the result.

An agent's word is not evidence. Saying "done" does not tell you what it changed or whether that was agreed.

You give tiller-book a plan a person signed and a branch an agent built. You get PASS or FAIL for each check and a receipt for the change. You then decide whether to merge.

Evidence: this repository contains 7 [signed plans](plans/) and 7 [receipts](receipts/), one receipt for the last pull request of each unit.

## Features

- Signed plans: a plan counts only if a commit signed with a listed key put it on main.
- Path scope: a change fails if its final diff includes a path its plan does not allow. A change made only of plan files is exempt.
- No silent skips: a check that fails, times out or cannot run counts as a failure.
- Receipts: one file per unit (one planned change) records its commits, its checks and the model tokens the caller reports.
- Release gate: a command to run by hand before going public. It scans the history for deny-listed text, personal email addresses and secrets.
- Not yet: reviewer identity, CI gates and lesson filing are planned for the full 0.1 release.

## Quick start

These steps run `tlb` on tiller-book itself. You need Python 3.11 or later, git, `ssh-keygen` and `gitleaks` on `PATH`.

1. Clone the repository and install it in a virtual environment. On Windows PowerShell, use `python` and `.venv\Scripts\Activate.ps1`. The `[test]` extra installs pytest, which the `tests` check runs. `tlb --help` then lists the commands.

   ```sh
   git clone https://github.com/sourav-patra/tiller-book.git
   cd tiller-book
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -e ".[test]"
   tlb --help
   ```

2. Verify a signed plan. `U1` is the first plan in this repository.

   ```sh
   tlb plan verify U1
   ```

   ```text
   PASS: plans/U1.toml at origin/main is valid and signed by a key in .github/allowed_signers at origin/main
   ```

3. Run the checks. The test suite takes about 5 minutes (measured on one Windows machine).

   ```sh
   tlb check run
   ```

   ```text
   PASS tests: exit 0
   PASS leak-scan: exit 0
   PASS path-scope: exit 0
   PASS receipt: exit 0
   PASS: all 4 required checks passed
   ```

To try it on your own work, follow [Use it in your own repository](docs/use-in-your-repo.md).

## How it works

![Four lanes: owner, agent, independent reviewer and the tlb command. The agent writes a plan, the owner signs and merges it, and tlb verifies it. The agent builds, a reviewer who is not the builder reviews, the agent commits a receipt, and tlb runs four checks. A failure returns to the build; a pass goes to the owner to merge.](docs/change-flow.svg)

How one change moves. Scripts decide steps 3 and 7, and a person decides steps 2 and 8. Step 5 is a process in this release: nothing checks who the reviewer was.

![The tlb checks read the plan and signers file from origin/main, and the changed paths and receipt from the unit branch. A plan edited on the branch cannot widen the limit. This holds only while the agent cannot merge to main or change the machine the checks run on.](docs/trust-boundary.svg)

Why an agent cannot widen its own limit. The checks read the limit from `origin/main` and the work from the branch. This holds only while the agent cannot merge to main or change the machine the checks run on.

## Status and limits

- A PASS does not mean the change is correct. A person still reads it and decides.
- Checks count only when someone runs them, because no CI gate exists yet.
- This release does not check who reviewed a change.
- tiller-book does not control who can merge. An agent that can merge to main can add its own signing key, so keep the merge right with a person.
- The checks trust the local `origin/main` reference and their own code. An agent that controls the machine can change both, so run them where it cannot.
- The receipt check proves the receipt's shape and its binding to the head commit. It does not prove the listed checks ran.

[Every known limit](docs/status-and-limits.md) is listed with what is enforced today.

## Docs

- [How it works](docs/how-it-works.md): who it is for, the three concepts, and what a receipt records.
- [Use it in your own repository](docs/use-in-your-repo.md): the steps, with their output.
- [Commands](docs/commands.md): every `tlb` command and option.
- [Status and limits](docs/status-and-limits.md): what is enforced now and what is not yet.
- [Comparison](docs/comparison.md): nearby projects, described in their own terms.
- [Contributing](CONTRIBUTING.md) and [vision](VISION.md).

## Licence

MIT. See [LICENSE](LICENSE).
