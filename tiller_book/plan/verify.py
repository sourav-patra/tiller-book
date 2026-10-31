"""A plan counts only if a commit signed by a key in allowed_signers brought its exact text onto the ref.

GitHub signs merge, squash and rebase results with its own key, so the merge commit never carries the
owner's signature. The check therefore looks at the newest non-merge commit that changed the file, and
requires that the file's text on the ref is still exactly what that commit wrote.
"""

import json
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from jsonschema import Draft202012Validator

# shortcut: schemas load from the repository checkout, so only an editable install finds them; package them when U8 writes the install steps.
SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"
SIGNERS = ".github/allowed_signers"
PLAN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class CouldNotRun(Exception):
    """A step that could not run; it counts as a failure, never as a pass."""


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout, r.stderr.strip()


def _show(repo, ref, path):
    code, out, _ = _git(repo, "show", f"{ref}:{path}")
    return out if code == 0 else None


def _blob(repo, rev, path):
    code, out, _ = _git(repo, "rev-parse", f"{rev}:{path}")
    return out.strip() if code == 0 else None


def signed_on_ref(repo, path, ref="origin/main", signers_ref="origin/main"):
    """Return the problems with `path` at `ref`; an empty list means it carries a valid signature."""
    if shutil.which("ssh-keygen") is None:
        raise CouldNotRun("ssh-keygen not on PATH; git needs it to check SSH signatures")
    code, out, err = _git(repo, "rev-parse", "--is-shallow-repository")
    if code != 0:
        raise CouldNotRun(f"not a git repository: {err}")
    if out.strip() == "true":
        raise CouldNotRun("shallow clone; fetch full history (fetch-depth: 0)")
    signers = _show(repo, signers_ref, SIGNERS)
    if signers is None:
        raise CouldNotRun(f"{SIGNERS} not found at {signers_ref}")
    if _blob(repo, ref, path) is None:
        return [f"{path} not found at {ref} (branch-only or missing)"]

    code, out, err = _git(repo, "log", "--no-merges", "-1", "--format=%H", ref, "--", path)
    commit = out.strip()
    if code != 0 or not commit:
        return [f"no non-merge commit on {ref} changed {path} {err}".rstrip()]

    problems = []
    if _blob(repo, commit, path) != _blob(repo, ref, path):
        problems.append(f"{path} at {ref} differs from what commit {commit[:12]} wrote; a merge rewrote it")

    with tempfile.TemporaryDirectory() as d:
        signers_file = Path(d) / "allowed_signers"
        signers_file.write_text(signers, encoding="utf-8", newline="\n")
        code, out, err = _git(repo, "-c", f"gpg.ssh.allowedSignersFile={signers_file.as_posix()}",
                              "log", "-1", "--format=%G?", commit)
    status = out.strip()
    if code != 0:
        raise CouldNotRun(f"git could not read the signature of {commit[:12]}: {err}")
    if status != "G":
        problems.append(f"commit {commit[:12]}, which last changed {path}, is not signed by a key in "
                        f"{SIGNERS} at {signers_ref} (signature status {status or 'none'})")
    return problems


def verify_plan(repo, plan_id, ref="origin/main", signers_ref="origin/main"):
    """Return the problems with plans/<plan_id>.toml at `ref`; an empty list means the plan holds."""
    if not PLAN_ID.match(plan_id):
        return [f"invalid plan id {plan_id!r}"]
    path = f"plans/{plan_id}.toml"
    text = _show(repo, ref, path)
    if text is None:
        return [f"{path} not found at {ref} (branch-only or missing)"]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return [f"{path} is not valid TOML: {e}"]

    schema = json.loads((SCHEMAS / "plan.schema.json").read_text(encoding="utf-8"))
    problems = [f"{path}: {e.json_path}: {e.message}"
                for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: e.json_path)]
    if data.get("id") != plan_id:
        problems.append(f"{path}: id {data.get('id')!r} does not match the file name")
    return problems + signed_on_ref(repo, path, ref, signers_ref)
