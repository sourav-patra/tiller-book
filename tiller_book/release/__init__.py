"""tlb release gate: what must hold on origin/main before the repository is made public.

The gate prints only fixed reasons, counts, exit codes and commit hashes: never tool output, exception
text, file paths, lock-file fields or addresses, so its own output cannot leak what it guards against.
Every step that cannot run is a FAIL, never a skip.
"""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from functools import partial
from pathlib import Path

from tiller_book.checks import aggregate, registry, run_check
from tiller_book.plan.verify import _git, signed_on_ref

REF = "origin/main"
LOCK = "locks/VISION.md.sha256"
NO_REPLACE = "GIT_NO_REPLACE_OBJECTS"


class StepFailed(Exception):
    """A step that could not run; its message is a fixed reason, safe to print."""


def _bytes(args, **kwargs):
    """Run a command and return (exit code, stdout bytes); stderr is dropped because it can echo a pattern."""
    try:
        r = subprocess.run(args, capture_output=True, **kwargs)
    except OSError as e:
        raise StepFailed(f"{args[0]} could not start") from e
    return r.returncode, r.stdout


def _git_bytes(repo, *args):
    code, out = _bytes(["git", "-C", str(repo), *args])
    if code != 0:
        raise StepFailed(f"git {args[0]} exited {code}")
    return out


def _rev(repo, ref):
    code, out, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    return out.strip() if code == 0 else None


def head_is_main(repo):
    head, main = _rev(repo, "HEAD"), _rev(repo, REF)
    if head is None or main is None:
        return False, f"HEAD or {REF} does not resolve to a commit"
    if head != main:
        return False, f"HEAD {head[:12]} is not {REF} {main[:12]}; the gate checks what will be published"
    return True, f"HEAD is {REF} {main[:12]}"


def _patterns(path):
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise StepFailed("deny-list file not readable") from e
    # CR is dropped so a CRLF file works with both greps; a blank line would match every line.
    patterns = [p.rstrip(b"\r") for p in data.split(b"\n") if p.strip()]
    if not patterns:
        raise StepFailed("deny-list file has no patterns")
    return patterns


TAGGER = re.compile(rb"^tagger [^\n]*<([^>\n]*)>", re.M)
TAG_SIGNATURE = re.compile(rb"\n-----BEGIN (PGP|SSH) SIGNATURE-----\n.*-----END \1 SIGNATURE-----\n?", re.S)


def _without_gpgsig(commit):
    """Drop the gpgsig header and its continuation lines; random base64 hits short patterns by chance."""
    header, sep, message = commit.partition(b"\n\n")
    kept, in_sig = [], False
    for line in header.split(b"\n"):
        in_sig = line.startswith((b"gpgsig ", b"gpgsig-sha256 ")) or (in_sig and line.startswith(b" "))
        if not in_sig:
            kept.append(line)
    return b"\n".join(kept) + sep + message


def _without_tag_signature(tag):
    start = tag.rfind(b"\n-----BEGIN ")
    if start >= 0 and TAG_SIGNATURE.fullmatch(tag, start):
        return tag[:start + 1]
    return tag


def _reachable(repo):
    """Return [(id, type, raw content)] for every object reachable from a ref, without the reflog."""
    ids = _git_bytes(repo, "rev-list", "--objects", "--all", "--no-object-names").split()
    code, out = _bytes(["git", "-C", str(repo), "cat-file", "--batch"], input=b"".join(i + b"\n" for i in ids))
    if code != 0:
        raise StepFailed(f"git cat-file exited {code}")
    # shortcut: holds every reachable object in memory; stream it if the repository grows past a few hundred MB.
    objects, pos = [], 0
    for oid in ids:
        nl = out.index(b"\n", pos)
        fields = out[pos:nl].split()
        if len(fields) != 3 or fields[0] != oid:
            raise StepFailed("git cat-file could not read a reachable object")
        size = int(fields[2])
        objects.append((oid, fields[1], out[nl + 1:nl + 1 + size]))
        pos = nl + 2 + size
    return objects


def _tree_names(oid, body):
    """Entry names of a raw tree: repeated `<mode> <name>NUL<binary id>`."""
    names, pos, idlen = [], 0, len(oid) // 2
    while pos < len(body):
        nul = body.index(b"\0", pos)
        names.append(body[body.index(b" ", pos) + 1:nul])
        pos = nul + 1 + idlen
    return names


def _reachable_text(repo):
    """Return (object count, the text to grep).

    Commits lose their gpgsig header and tags a trailing signature block; blobs are kept in full;
    trees are binary, so the entry names of every tree stand in for them; ref names are added.
    """
    objects = _reachable(repo)
    parts = _git_bytes(repo, "for-each-ref", "--format=%(refname)").splitlines()
    for oid, kind, body in objects:
        # Signatures are skipped to avoid chance hits in base64; limit: a crafted fake signature can hide text.
        if kind == b"commit":
            parts.append(_without_gpgsig(body))
        elif kind == b"tag":
            parts.append(_without_tag_signature(body))
        elif kind == b"blob":
            parts.append(body)
        elif kind == b"tree":
            parts.extend(_tree_names(oid, body))
    return len(objects), b"\n".join(parts) + b"\n"


def denylist(repo, path):
    """Grep the HEAD tree and every object reachable from a ref."""
    patterns = _patterns(path)
    if shutil.which("grep") is None:
        raise StepFailed("grep not on PATH")
    with tempfile.TemporaryDirectory() as d:
        pf = Path(d) / "patterns"
        pf.write_bytes(b"\n".join(patterns) + b"\n")
        code, out = _bytes(["git", "-C", str(repo), "grep", "-a", "-i", "-c", "-f", pf.as_posix(), "HEAD"])
        if code not in (0, 1):
            raise StepFailed(f"git grep exited {code}")
        per_file = [int(line.rsplit(b":", 1)[1]) for line in out.splitlines()]
        n, text = _reachable_text(repo)
        code, out = _bytes(["grep", "-a", "-i", "-c", "-f", pf.as_posix()], input=text)
        if code not in (0, 1):
            raise StepFailed(f"grep exited {code}")
    history = int(out.strip())
    reason = (f"{sum(per_file)} matching lines in {len(per_file)} files at HEAD, "
              f"{history} matching lines across {n} reachable objects")
    return not per_file and history == 0, reason


def identities(repo):
    code, out, _ = _git(repo, "log", "--all", "--format=%ae%n%ce")
    if code != 0:
        raise StepFailed(f"git log exited {code}")
    headers = (body.partition(b"\n\n")[0] for _, kind, body in _reachable(repo) if kind == b"tag")
    taggers = {m.group(1).decode("utf-8", "replace") for h in headers for m in TAGGER.finditer(h)}
    seen = set(out.splitlines()) | taggers
    bad = [a for a in seen if a != "noreply@github.com" and not a.endswith("@users.noreply.github.com")]
    what = "author, committer and tagger addresses"
    if bad:
        return False, f"{len(bad)} of {len(seen)} {what} are not GitHub noreply addresses"
    return True, f"all {len(seen)} {what} are GitHub noreply addresses"


def leak_scan(repo):
    """gitleaks git . reads commits only, so every reachable tag object and every non-commit object a ref
    points at (directly or through one tag) is scanned as a file too."""
    if shutil.which("gitleaks") is None:
        raise StepFailed("gitleaks not on PATH")
    loose = {oid: body for oid, kind, body in _reachable(repo) if kind == b"tag"}
    refs = _git_bytes(repo, "for-each-ref", "--format=%(objectname) %(objecttype) %(*objectname) %(*objecttype)")
    for fields in (line.split() for line in refs.splitlines()):
        for oid, kind in zip(fields[0::2], fields[1::2]):
            if kind not in (b"commit", b"tag"):
                loose[oid] = _raw(repo, oid)
    code_git, _ = _bytes(["gitleaks", "git", "."], cwd=repo, timeout=300)
    with tempfile.TemporaryDirectory() as d:
        for oid, body in loose.items():
            (Path(d) / oid.decode("ascii")).write_bytes(body)
        code_dir, _ = _bytes(["gitleaks", "dir", d], timeout=300)
    reason = f"gitleaks git exit {code_git}, gitleaks dir exit {code_dir} ({len(loose)} tag or non-commit objects)"
    return code_git == 0 and code_dir == 0, reason


def _raw(repo, oid):
    kind = _git_bytes(repo, "cat-file", "-t", oid.decode("ascii")).strip().decode("ascii")
    return _git_bytes(repo, "cat-file", kind, oid.decode("ascii"))


def vision_lock(repo):
    if shutil.which("ssh-keygen") is None:
        raise StepFailed("ssh-keygen not on PATH")
    for path in ("VISION.md", LOCK):
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{REF}:{path}")[0] != 0:
            return False, f"{path} missing on {REF}"
    for path in ("VISION.md", LOCK):
        if signed_on_ref(repo, path, REF, REF):
            return False, f"{path} on {REF} is not as written by a commit signed with a key in allowed_signers"
    fields = _git_bytes(repo, "cat-file", "blob", f"{REF}:{LOCK}").split()
    actual = hashlib.sha256(_git_bytes(repo, "cat-file", "blob", f"{REF}:VISION.md")).hexdigest()
    if not fields or fields[0] != actual.encode("ascii"):
        return False, "lock hash does not match VISION.md"
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
    results, saved = [], os.environ.get(NO_REPLACE)
    os.environ[NO_REPLACE] = "1"  # every child (git, grep pipelines, gitleaks, checks) reads stored objects
    try:
        for name, step in steps:
            try:
                ok, reason = step(repo)
            except StepFailed as e:
                ok, reason = False, f"could not run: {e}"
            except Exception as e:  # noqa: BLE001 -- the gate reports, it never shows a traceback or exception text
                ok, reason = False, f"could not run: {type(e).__name__} in {name}"
            results.append((name, ok, reason))
    finally:
        if saved is None:
            os.environ.pop(NO_REPLACE, None)
        else:
            os.environ[NO_REPLACE] = saved
    return results
