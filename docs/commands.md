# Commands

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
- `tlb release gate --denylist PATH [--repo PATH]`: needs `grep` on `PATH`, and requires `HEAD` to equal `origin/main` in a full clone without grafts; it does not switch to it. It then checks the deny-list against the HEAD tree and every object reachable from every ref, author, committer and tagger addresses, gitleaks on the history and on every reachable blob, commit and tag, the `VISION.md` lock, and the registered checks. It prints one PASS or FAIL line per step and a final verdict, and exits 0 only if all steps pass. The deny-list file stays outside the repository. Output is counts, short hashes and fixed reasons only, never matched text, addresses or tool output.
