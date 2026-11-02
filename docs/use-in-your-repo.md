# Use tiller-book in your own repository

You need Python 3.11 or later, git, `ssh-keygen` and `gitleaks` on `PATH`, and a full clone (not shallow) with `origin` pointing at the repository. The release gate also needs `grep` on `PATH`. A missing tool makes its check fail; nothing is skipped.

Install `tlb` into your project's environment. To pin a release, replace `main` with its tag. In the commands below, replace each `<...>` with your own value.

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

   The last command prints the same five PASS lines as the [quick start](https://github.com/sourav-patra/tiller-book/blob/main/README.md#quick-start). If the diff from the merge base to `HEAD` holds a path outside `allowed_paths`, the path-scope check fails with the path named:

   ```text
   FAIL path-scope: exit 1: FAIL: outside allowed_paths of plans/demo-1.toml at origin/main: outside.txt
   ```
