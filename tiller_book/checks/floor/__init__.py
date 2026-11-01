"""Floor checkers: each reads the pull request as origin/main..HEAD, prints one PASS or FAIL line and exits 0 or 1.

Both share the gates below: no changes and plan-class pull requests pass as not applicable, any other pull
request must sit on a unit/<id> branch.
"""

import os
import re
import sys
from pathlib import Path

from tiller_book.plan.verify import PLAN_ID, CouldNotRun, _git

BASE = "origin/main"
PLAN_FILE = re.compile(r"plans/[A-Za-z0-9][A-Za-z0-9._-]*\.toml")
BRANCH = re.compile(r"^unit/(.+)$")


def git(repo, *args):
    code, out, err = _git(repo, *args)
    if code != 0:
        raise CouldNotRun(f"git {args[0]} failed: {err or f'exit {code}'}")
    return out


def names(repo, *args):
    """Paths from git diff --name-only, read with -z so git never quotes them."""
    return [p for p in git(repo, "diff", "--name-only", "--no-renames", "--ignore-submodules=none", "--no-relative", "-z", *args).split("\0") if p]


def gate(repo):
    """Return (base, changed, unit id, verdict); a verdict (ok, message) means the checker is done."""
    base = git(repo, "merge-base", BASE, "HEAD").strip()
    changed = names(repo, base, "HEAD")
    if not changed:
        return base, changed, None, (True, f"no changes against {BASE}")
    if all(PLAN_FILE.fullmatch(p) for p in changed):
        return base, changed, None, (True, "not applicable: plan-class pull request, every path under plans/")
    branch = os.environ.get("GITHUB_HEAD_REF") or git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    m = BRANCH.match(branch)
    if not m or not PLAN_ID.match(m.group(1)):
        return base, changed, None, (False, f"branch {branch!r} is not unit/<id>, and the pull request is not plan-class")
    return base, changed, m.group(1), None


def run(check, repo="."):
    """Print one line and return the exit code; any exception is FAIL with its reason, never a traceback."""
    if hasattr(sys.stdout, "reconfigure"):  # paths may hold characters the console code page cannot encode
        sys.stdout.reconfigure(errors="backslashreplace")
    try:
        ok, message = check(Path(repo))
    except Exception as e:  # noqa: BLE001 - fail closed on anything
        ok, message = False, f"could not run: {e}"
    message = " ".join(str(message).splitlines())  # one line: git errors span several
    print(f"{'PASS' if ok else 'FAIL'}: {message}")
    return 0 if ok else 1
