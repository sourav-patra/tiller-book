"""Path scope: every path the pull request changes lies inside allowed_paths of its plan on origin/main.

The plan is read only from origin/main, so a pull request that edits its own plan cannot widen the limit;
the edit is itself out of scope, because no plan lists plans/.
"""

import sys
import tomllib

from tiller_book.checks.floor import BASE, gate, git, run
from tiller_book.plan.verify import verify_plan


def allowed(path, entries):
    return any(path.startswith(e) if e.endswith("/") else path == e for e in entries)


def check(repo):
    _, changed, unit, verdict = gate(repo)
    if verdict:
        return verdict
    problems = verify_plan(repo, unit, BASE, BASE)
    if problems:
        return False, "; ".join(problems)
    plan = f"plans/{unit}.toml"
    entries = tomllib.loads(git(repo, "show", f"{BASE}:{plan}"))["allowed_paths"]
    outside = [p for p in changed if not allowed(p, entries)]
    if outside:
        return False, f"outside allowed_paths of {plan} at {BASE}: {', '.join(outside)}"
    return True, f"all {len(changed)} changed paths inside allowed_paths of {plan} at {BASE}"


if __name__ == "__main__":
    sys.exit(run(check))
