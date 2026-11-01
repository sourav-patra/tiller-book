"""tlb release gate against throwaway repositories, a throwaway SSH key and an invented deny-list."""

import hashlib
import random
import shutil
import string
import sys

import pytest
from test_plan_verify import commit, git, keygen, signers_line

from tiller_book import cli
from tiller_book.checks import Check, registry

NOREPLY = "1+test@users.noreply.github.com"
VISION = "# Vision\n\nInvented text for a test.\n"
TERMS = "zorblatt\nquillfen\n"  # invented; neither is in any real deny-list
REAL_WHICH = shutil.which

pytestmark = pytest.mark.skipif(REAL_WHICH("ssh-keygen") is None or REAL_WHICH("grep") is None,
                                reason="needs ssh-keygen and grep")
needs_gitleaks = pytest.mark.skipif(REAL_WHICH("gitleaks") is None, reason="needs gitleaks")


def lock_text(vision):
    return f"{hashlib.sha256(vision.encode()).hexdigest()} *VISION.md\n"


def publish(repo):
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


@pytest.fixture(autouse=True)
def passing_checks(monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", [Check("ok", (sys.executable, "-c", "pass"))])


@pytest.fixture
def key(tmp_path):
    return keygen(tmp_path / "owner")


@pytest.fixture
def repo(tmp_path, key):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for k, v in {"user.email": NOREPLY, "user.name": "Test", "commit.gpgsign": "false",
                 "gpg.format": "ssh", "core.autocrlf": "false"}.items():
        git(r, "config", k, v)
    commit(r, {".github/allowed_signers": signers_line(key)}, "bootstrap", key)
    commit(r, {"VISION.md": VISION, "locks/VISION.md.sha256": lock_text(VISION)}, "lock vision", key)
    publish(r)
    return r


@pytest.fixture
def denylist(tmp_path):
    p = tmp_path / "deny.txt"
    p.write_text(TERMS, newline="\n")
    return p


def run(repo, denylist, capsys):
    code = cli.main(["release", "gate", "--denylist", str(denylist), "--repo", str(repo)])
    return code, capsys.readouterr().out


def step(out, name):
    return next(line for line in out.splitlines() if line.split(" ", 1)[1].startswith(f"{name}:"))


@needs_gitleaks
def test_clean_repository_passes_every_step(repo, denylist, capsys):
    code, out = run(repo, denylist, capsys)
    assert code == 0, out
    for name in ("head", "deny-list", "identities", "leak-scan", "vision-lock", "checks"):
        assert step(out, name).startswith("PASS ")
    assert out.splitlines()[-1] == "PASS: all 6 release steps passed"


def test_head_not_origin_main_fails(repo, denylist, capsys):
    commit(repo, {"later.txt": "x\n"}, "not yet on main")
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert "is not origin/main" in step(out, "head") and step(out, "head").startswith("FAIL ")
    assert out.splitlines()[-1].startswith("FAIL: release steps not PASS: head")


def test_deny_list_hit_is_reported_by_count_without_the_text(repo, denylist, capsys):
    commit(repo, {"notes.txt": "a Zorblatt here\nand QUILLFEN there\nclean line\n"}, "notes mention zorblatt")
    publish(repo)
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "deny-list") == ("FAIL deny-list: 2 matching lines in 1 tracked files, "
                                      "3 matching lines in git log -p --all")
    assert "zorblatt" not in out.lower() and "quillfen" not in out.lower()


def test_deny_list_hit_in_history_only_fails(repo, denylist, capsys):
    commit(repo, {"notes.txt": "zorblatt\n"}, "add")
    commit(repo, {"notes.txt": "gone\n"}, "remove")
    publish(repo)
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "deny-list").startswith("FAIL deny-list: 0 matching lines in 0 tracked files, 2 matching")


def test_crlf_deny_list_still_matches(repo, tmp_path, capsys):
    crlf = tmp_path / "crlf.txt"
    crlf.write_bytes(b"zorblatt\r\n")
    commit(repo, {"notes.txt": "zorblatt\n"}, "add")
    publish(repo)
    assert step(run(repo, crlf, capsys)[1], "deny-list").startswith("FAIL deny-list: 1 matching lines")


def test_missing_deny_list_fails(repo, tmp_path, capsys):
    code, out = run(repo, tmp_path / "absent.txt", capsys)
    assert code == 1
    assert step(out, "deny-list").startswith("FAIL deny-list: could not run: deny-list")
    assert "is not readable" in out and "Traceback" not in out


def test_deny_list_with_no_patterns_fails(repo, tmp_path, capsys):
    blank = tmp_path / "blank.txt"
    blank.write_text("\n  \n")
    assert "has no patterns" in step(run(repo, blank, capsys)[1], "deny-list")


def test_missing_grep_fails(repo, denylist, capsys, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "grep" else REAL_WHICH(name))
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "deny-list") == "FAIL deny-list: could not run: grep not on PATH"


def test_non_noreply_identity_fails_without_the_address(repo, denylist, capsys):
    git(repo, "-c", "user.email=someone@example.com", "commit", "-q", "--allow-empty", "-m", "other identity")
    publish(repo)
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "identities").startswith("FAIL identities: 1 of 2 author and committer addresses")
    assert "someone" not in out


def test_web_flow_committer_passes_identities(repo, denylist, capsys):
    git(repo, "-c", "user.email=noreply@github.com", "commit", "-q", "--allow-empty", "-m", "web merge")
    publish(repo)
    assert step(run(repo, denylist, capsys)[1], "identities").startswith("PASS identities: all 2")


@needs_gitleaks
def test_leaked_secret_fails_leak_scan(repo, denylist, capsys):
    token = "ghp_" + "".join(random.choices(string.ascii_letters + string.digits, k=36))  # built at run time
    commit(repo, {"config.txt": f"token = {token}\n"}, "oops")
    publish(repo)
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "leak-scan").startswith("FAIL leak-scan: gitleaks git .: exit")
    assert token not in out


def test_missing_gitleaks_fails(repo, denylist, capsys, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "gitleaks" else REAL_WHICH(name))
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "leak-scan") == "FAIL leak-scan: gitleaks git .: tool not on PATH: gitleaks"


def test_unsigned_vision_edit_fails(repo, denylist, capsys):
    edited = VISION + "More.\n"
    commit(repo, {"VISION.md": edited, "locks/VISION.md.sha256": lock_text(edited)}, "unsigned edit")
    publish(repo)
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert "carries no SSH signature" in step(out, "vision-lock")


def test_signed_lock_with_wrong_hash_fails(repo, denylist, key, capsys):
    commit(repo, {"VISION.md": VISION + "More.\n"}, "signed edit, lock not updated", key)
    publish(repo)
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert "hashes to" in step(out, "vision-lock") and step(out, "vision-lock").startswith("FAIL ")


def test_vision_missing_on_origin_main_fails(tmp_path, key, denylist, capsys):
    r = tmp_path / "bare"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for k, v in {"user.email": NOREPLY, "user.name": "Test", "gpg.format": "ssh"}.items():
        git(r, "config", k, v)
    commit(r, {".github/allowed_signers": signers_line(key)}, "bootstrap", key)
    publish(r)
    assert "VISION.md not found at origin/main" in step(run(r, denylist, capsys)[1], "vision-lock")


def test_failing_registered_check_fails(repo, denylist, capsys, monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", [Check("bad", (sys.executable, "-c", "raise SystemExit(3)"))])
    code, out = run(repo, denylist, capsys)
    assert code == 1
    assert step(out, "checks") == "FAIL checks: required checks not PASS: bad"


def test_not_a_repository_fails_without_traceback(tmp_path, denylist, capsys, monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", [Check("ghost", ("tlb-no-such-binary-xyz",))])
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out = run(plain, denylist, capsys)
    assert code == 1
    fails = [line.split(":", 1)[0] for line in out.splitlines() if line.startswith("FAIL ")]
    # gitleaks exits 0 outside a repository, so leak-scan alone passes; the head step still fails the gate.
    assert fails == ["FAIL head", "FAIL deny-list", "FAIL identities", "FAIL vision-lock", "FAIL checks"]
    assert "could not run: HEAD does not resolve to a commit" in out
    assert "Traceback" not in out
