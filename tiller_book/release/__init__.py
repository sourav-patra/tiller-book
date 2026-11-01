"""tlb release gate: what must hold on origin/main before the repository is made public.

The deny-list step prints counts only, never a matched line or a pattern, so the gate's own output
cannot leak a term. Every step that cannot run is a FAIL, never a skip.
"""

import hashlib
import shutil
import subprocess
import tempfile
from functools import partial
from pathlib import Path

from tiller_book.checks import Check, aggregate, registry, run_check
from tiller_book.plan.verify import CouldNotRun, _git, signed_on_ref

REF = "origin/main"
LOCK = "locks/VISION.md.sha256"
LEAK_SCAN = Check("leak-scan", ("gitleaks", "git", "."), tools=("gitleaks",), timeout=300)


def _rev(repo, ref):
    code, out, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if code != 0:
        raise CouldNotRun(f"{ref} does not resolve to a commit")
    return out.strip()


def _bytes(args, **kwargs):
    """Run a command and return (exit code, stdout bytes); stderr is dropped because it can echo a pattern."""
    try:
        r = subprocess.run(args, capture_output=True, **kwargs)
    except OSError as e:
        raise CouldNotRun(f"{args[0]} could not start: {e}") from e
    return r.returncode, r.stdout


def head_is_main(repo):
    head, main = _rev(repo, "HEAD"), _rev(repo, REF)
    if head != main:
        return False, f"HEAD {head[:12]} is not {REF} {main[:12]}; the gate checks what will be published"
    return True, f"HEAD is {REF} {main[:12]}"


def _patterns(path):
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise CouldNotRun(f"deny-list {path} is not readable: {e.strerror or e}") from e
    # CR is dropped so a CRLF file works with both greps; a blank line would match every line.
    patterns = [p.rstrip(b"\r") for p in data.split(b"\n") if p.strip()]
    if not patterns:
        raise CouldNotRun(f"deny-list {path} has no patterns")
    return patterns


def denylist(repo, path):
    patterns = _patterns(path)
    if shutil.which("grep") is None:
        raise CouldNotRun("grep not on PATH")
    with tempfile.TemporaryDirectory() as d:
        pf = Path(d) / "patterns"
        pf.write_bytes(b"\n".join(patterns) + b"\n")
        code, out = _bytes(["git", "-C", str(repo), "grep", "-I", "-i", "-c", "-f", pf.as_posix()])
        if code not in (0, 1):
            raise CouldNotRun(f"git grep exited {code}")
        per_file = [int(line.rsplit(b":", 1)[1]) for line in out.splitlines()]
        code, log = _bytes(["git", "-C", str(repo), "log", "-p", "--all"])
        if code != 0:
            raise CouldNotRun(f"git log -p --all exited {code}")
        code, out = _bytes(["grep", "-i", "-c", "-f", pf.as_posix()], input=log)
        if code not in (0, 1):
            raise CouldNotRun(f"grep exited {code}")
    history = int(out.strip())
    reason = (f"{sum(per_file)} matching lines in {len(per_file)} tracked files, "
              f"{history} matching lines in git log -p --all")
    return not per_file and history == 0, reason


def identities(repo):
    code, out, _ = _git(repo, "log", "--all", "--format=%ae%n%ce")
    if code != 0:
        raise CouldNotRun(f"git log --all exited {code}")
    seen = set(out.splitlines())
    bad = [a for a in seen if a != "noreply@github.com" and not a.endswith("@users.noreply.github.com")]
    if bad:
        return False, f"{len(bad)} of {len(seen)} author and committer addresses are not GitHub noreply addresses"
    return True, f"all {len(seen)} author and committer addresses are GitHub noreply addresses"


def leak_scan(repo):
    r = run_check(LEAK_SCAN, repo)
    return r["status"] == "PASS", f"gitleaks git .: {r['reason']}"


def vision_lock(repo):
    problems = signed_on_ref(repo, "VISION.md", REF, REF) + signed_on_ref(repo, LOCK, REF, REF)
    if problems:
        return False, "; ".join(problems)
    code, lock = _bytes(["git", "-C", str(repo), "cat-file", "blob", f"{REF}:{LOCK}"])
    code2, vision = _bytes(["git", "-C", str(repo), "cat-file", "blob", f"{REF}:VISION.md"])
    if code or code2:
        raise CouldNotRun(f"git could not read VISION.md or {LOCK} at {REF}")
    recorded = lock.split()[0].decode("ascii", "replace") if lock.split() else ""
    actual = hashlib.sha256(vision).hexdigest()
    if recorded != actual:
        return False, f"{LOCK} records {recorded[:12] or 'nothing'}, VISION.md at {REF} hashes to {actual[:12]}"
    return True, f"VISION.md and {LOCK} are owner-signed on {REF} and the hash matches ({actual[:12]})"


def checks(repo):
    results = [run_check(c, repo) for c in registry.CHECKS]
    code, verdict = aggregate(registry.CHECKS, results)
    return code == 0, verdict.split(": ", 1)[-1]


def gate(repo, denylist_path):
    """Return [(step name, passed, reason)] for every step, in order; an exception is a FAIL."""
    steps = [("head", head_is_main), ("deny-list", partial(denylist, path=denylist_path)),
             ("identities", identities), ("leak-scan", leak_scan), ("vision-lock", vision_lock),
             ("checks", checks)]
    results = []
    for name, step in steps:
        try:
            ok, reason = step(repo)
        except Exception as e:  # noqa: BLE001 -- the gate reports, it never shows a traceback
            ok, reason = False, f"could not run: {e if isinstance(e, CouldNotRun) else f'{type(e).__name__}: {e}'}"
        results.append((name, ok, reason))
    return results
