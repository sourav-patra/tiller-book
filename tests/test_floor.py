"""Floor checkers path-scope and receipt against throwaway repositories with an origin/main and an owner-signed plan."""

import json
import subprocess
import sys

import pytest

from test_plan_verify import PRINCIPAL, commit, git, keys, signers_line, pytestmark  # noqa: F401
from tiller_book.checks import floor
from tiller_book.checks.floor import path_scope, receipt

PLAN = 'id = "U9"\ntitle = "test"\nallowed_paths = ["src/", "receipts/U9.json"]\nmin_held_out_cases = 20\n'
CONFIG = {"user.email": PRINCIPAL, "user.name": "Test", "commit.gpgsign": "false",
          "gpg.format": "ssh", "core.autocrlf": "false"}


@pytest.fixture(autouse=True)
def no_ci_branch(monkeypatch):
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)


def configure(r):
    for k, v in CONFIG.items():
        git(r, "config", k, v)


@pytest.fixture
def make(tmp_path, keys):
    """Build origin/main with signers, src/keep.py and plans/U9.toml, clone it, and switch to `branch`."""
    def make(plan="signed", branch="unit/U9"):
        seed = tmp_path / "seed"
        seed.mkdir()
        git(seed, "init", "-q", "-b", "main")
        configure(seed)
        commit(seed, {".github/allowed_signers": signers_line(keys["owner"]), "src/keep.py": "x\n"},
               "bootstrap", keys["owner"])
        if plan != "missing":
            commit(seed, {"plans/U9.toml": PLAN}, "plan", keys["owner"] if plan == "signed" else None)
        git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
        work = tmp_path / "work"
        # autocrlf off before checkout, or a CRLF checkout makes every file look changed
        git(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(tmp_path / "origin.git"), "work")
        configure(work)
        git(work, "switch", "-q", "-c", branch)
        return work
    return make


@pytest.fixture
def work(make):
    return make()


def check(module, repo, capsys):
    code = floor.run(module.check, repo)
    return code, capsys.readouterr().out.strip()


def add_receipt(repo, unit="U9", start=None, head=None, extra_files=None, drop=None):
    parent = git(repo, "rev-parse", "HEAD").strip()
    data = {"schema_version": "0.1", "unit": unit, "runner": {"agent": "test"},
            "commits": {"start": start or git(repo, "merge-base", "origin/main", "HEAD").strip(),
                        "head": head or parent},
            "model_calls": [], "checks": [], "refusals": [], "evidence": [], "not_measured": []}
    data.pop(drop, None)
    commit(repo, {"receipts/U9.json": json.dumps(data, indent=2) + "\n", **(extra_files or {})}, "receipt")


# path scope

def test_build_inside_plan_passes(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    code, out = check(path_scope, work, capsys)
    assert code == 0 and out.startswith("PASS: all 1 changed paths inside allowed_paths of plans/U9.toml")


def test_one_path_outside_plan_fails_naming_it(work, capsys):
    commit(work, {"src/a.py": "a\n", "docs/x.md": "x\n"}, "code")
    assert check(path_scope, work, capsys) == (1, "FAIL: outside allowed_paths of plans/U9.toml at origin/main: docs/x.md")


def test_widening_own_plan_in_build_pull_request_fails(work, capsys):
    commit(work, {"src/a.py": "a\n", "plans/U9.toml": PLAN.replace('"src/"', '"src/", "docs/"'),
                  "docs/x.md": "x\n"}, "widen")
    assert check(path_scope, work, capsys) == (
        1, "FAIL: outside allowed_paths of plans/U9.toml at origin/main: docs/x.md, plans/U9.toml")


def test_move_from_inside_to_outside_fails_naming_new_path(work, capsys):
    (work / "other").mkdir()
    git(work, "mv", "src/keep.py", "other/keep.py")
    git(work, "commit", "-q", "-m", "move")
    assert check(path_scope, work, capsys) == (1, "FAIL: outside allowed_paths of plans/U9.toml at origin/main: other/keep.py")


def test_plans_file_with_code_is_a_build_pull_request(work, capsys):
    commit(work, {"plans/U10.toml": PLAN.replace("U9", "U10"), "src/a.py": "a\n"}, "mixed")
    code, out = check(path_scope, work, capsys)
    assert (code, out) == (1, "FAIL: outside allowed_paths of plans/U9.toml at origin/main: plans/U10.toml")
    code, out = check(receipt, work, capsys)
    assert code == 1 and "no receipt" in out


# shared gates

@pytest.mark.parametrize("plan, reason", [("unsigned", "carries no SSH signature"),
                                          ("missing", "plans/U9.toml not found at origin/main")])
def test_plan_unsigned_or_missing_fails_both(make, capsys, plan, reason):
    w = make(plan)
    commit(w, {"src/a.py": "a\n"}, "code")
    add_receipt(w)
    for module in (path_scope, receipt):
        code, out = check(module, w, capsys)
        assert code == 1 and reason in out, (module.__name__, out)


def test_plan_class_pull_request_passes_both(make, capsys):
    w = make(branch="plan/U10")
    commit(w, {"plans/U10.toml": PLAN.replace("U9", "U10")}, "plan")
    for module in (path_scope, receipt):
        assert check(module, w, capsys) == (0, "PASS: not applicable: plan-class pull request, every path under plans/")


def test_branch_not_unit_fails_both(make, capsys):
    w = make(branch="feature")
    commit(w, {"src/a.py": "a\n"}, "code")
    add_receipt(w)
    for module in (path_scope, receipt):
        code, out = check(module, w, capsys)
        assert code == 1 and "branch 'feature' is not unit/<id>" in out


def test_github_head_ref_names_the_branch_in_ci(make, capsys, monkeypatch):
    w = make(branch="feature")
    commit(w, {"src/a.py": "a\n"}, "code")
    monkeypatch.setenv("GITHUB_HEAD_REF", "unit/U9")
    assert check(path_scope, w, capsys)[0] == 0


def test_no_changes_passes_both(work, capsys):
    for module in (path_scope, receipt):
        assert check(module, work, capsys) == (0, "PASS: no changes against origin/main")


# receipt

def test_no_receipt_commit_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    code, out = check(receipt, work, capsys)
    assert code == 1 and "no receipt: head commit" in out and "does not change receipts/U9.json" in out


def test_receipt_invalid_against_schema_fails_with_first_error(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    add_receipt(work, drop="runner")
    assert check(receipt, work, capsys) == (1, "FAIL: receipts/U9.json: $: 'runner' is a required property")


def test_receipt_for_another_unit_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    add_receipt(work, unit="U8")
    assert check(receipt, work, capsys) == (1, "FAIL: receipts/U9.json: unit 'U8' is not 'U9'")


def test_receipt_naming_an_older_commit_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code one")
    older = git(work, "rev-parse", "HEAD").strip()
    commit(work, {"src/b.py": "b\n"}, "code two")
    add_receipt(work, head=older)
    code, out = check(receipt, work, capsys)
    assert code == 1 and f"commits.head {older[:12]} is not the receipt commit's parent" in out


def test_code_commit_after_receipt_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    add_receipt(work)
    commit(work, {"src/b.py": "b\n"}, "late code")
    code, out = check(receipt, work, capsys)
    assert code == 1 and "no receipt" in out
    assert check(path_scope, work, capsys)[0] == 0  # in scope; only the receipt binding breaks


def test_receipt_commit_that_changes_another_file_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    add_receipt(work, extra_files={"src/b.py": "b\n"})
    code, out = check(receipt, work, capsys)
    assert code == 1 and "also changes: src/b.py" in out


def test_receipt_start_not_merge_base_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    add_receipt(work, start=git(work, "rev-parse", "HEAD").strip())
    code, out = check(receipt, work, capsys)
    assert code == 1 and "is not the merge base" in out


def test_valid_receipt_only_last_commit_passes(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    add_receipt(work)
    assert check(receipt, work, capsys) == (0, "PASS: receipts/U9.json is valid and names the head commit's parent")
    assert check(path_scope, work, capsys)[0] == 0


def test_receipt_on_a_merge_commit_fails(work, capsys):
    commit(work, {"src/a.py": "a\n"}, "code")
    git(work, "switch", "-q", "-c", "side", "origin/main")
    commit(work, {"src/b.py": "b\n"}, "side")
    git(work, "switch", "-q", "unit/U9")
    git(work, "merge", "-q", "--no-ff", "side", "-m", "merge")
    code, out = check(receipt, work, capsys)
    assert code == 1 and "has 2 parents" in out


@pytest.mark.parametrize("name", ["path_scope", "receipt"])
def test_module_without_origin_main_fails_with_reason_and_no_traceback(tmp_path, name):
    git(tmp_path, "init", "-q", "-b", "main")
    p = subprocess.run([sys.executable, "-m", f"tiller_book.checks.floor.{name}"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert p.returncode == 1 and p.stdout.startswith("FAIL: could not run: git merge-base failed")
    assert len(p.stdout.splitlines()) == 1 and "Traceback" not in p.stderr
