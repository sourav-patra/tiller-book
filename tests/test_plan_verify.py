"""tlb plan verify against throwaway repositories and throwaway SSH keys."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tiller_book import cli
from tiller_book.plan import verify

PRINCIPAL = "owner@example.com"
PLAN = 'id = "U9"\ntitle = "test"\nallowed_paths = ["src/"]\nmin_held_out_cases = 20\n'

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def keygen(path):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(path)], check=True)
    return path


def signers_line(key):
    kind, body = Path(f"{key}.pub").read_text().split()[:2]
    return f'{PRINCIPAL} namespaces="git" {kind} {body}\n'


def commit(repo, files, message, key=None):
    for name, text in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    sign = ["-c", f"user.signingkey={Path(key).as_posix()}", "commit", "-S"] if key else ["commit"]
    git(repo, *sign, "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def keys(tmp_path):
    return {"owner": keygen(tmp_path / "owner"), "other": keygen(tmp_path / "other")}


@pytest.fixture
def repo(tmp_path, keys):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for k, v in {"user.email": PRINCIPAL, "user.name": "Test", "commit.gpgsign": "false",
                 "gpg.format": "ssh", "core.autocrlf": "false"}.items():
        git(r, "config", k, v)
    commit(r, {".github/allowed_signers": signers_line(keys["owner"])}, "bootstrap", keys["owner"])
    return r


def run(repo, plan_id="U9", ref="main", signers_ref="main"):
    return cli.main(["plan", "verify", plan_id, "--repo", str(repo), "--ref", ref, "--signers-ref", signers_ref])


def test_owner_signed_plan_on_main_passes(repo, keys, capsys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    assert run(repo) == 0
    assert "PASS" in capsys.readouterr().out


def test_signed_plan_through_unsigned_merge_commit_passes(repo, keys):
    git(repo, "switch", "-q", "-c", "plan")
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    git(repo, "switch", "-q", "main")
    commit(repo, {"other.txt": "x\n"}, "main moves")
    git(repo, "merge", "-q", "--no-ff", "plan", "-m", "merge pull request")
    assert run(repo) == 0


def test_signed_plan_on_pull_request_head_with_signers_from_main_passes(repo, keys):
    git(repo, "switch", "-q", "-c", "plan")
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    assert run(repo, ref="plan", signers_ref="main") == 0


def test_unsigned_plan_fails(repo, capsys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan")
    assert run(repo) == 1
    assert "carries no SSH signature" in capsys.readouterr().out


def test_branch_only_plan_fails(repo, keys, capsys):
    git(repo, "switch", "-q", "-c", "plan")
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    assert run(repo, ref="main") == 1
    assert "not found at main" in capsys.readouterr().out


def test_plan_signed_by_unlisted_key_fails(repo, keys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["other"])
    assert run(repo) == 1


def test_unsigned_edit_after_signed_plan_fails(repo, keys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    commit(repo, {"plans/U9.toml": PLAN.replace('"src/"', '"src/", "secrets/"')}, "widen")
    assert run(repo) == 1


def test_signer_added_on_the_pull_request_branch_is_ignored(repo, keys):
    git(repo, "switch", "-q", "-c", "plan")
    both = signers_line(keys["owner"]) + signers_line(keys["other"])
    commit(repo, {".github/allowed_signers": both, "plans/U9.toml": PLAN}, "plan", keys["other"])
    assert run(repo, ref="plan", signers_ref="plan") == 0  # the branch would vouch for itself
    assert run(repo, ref="plan", signers_ref="main") == 1  # signers from main do not


def test_signer_added_in_working_tree_only_is_ignored(repo, keys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["other"])
    (repo / ".github/allowed_signers").write_text(signers_line(keys["owner"]) + signers_line(keys["other"]))
    assert run(repo) == 1


def test_merge_commit_that_rewrites_the_plan_fails(repo, keys, capsys):
    git(repo, "switch", "-q", "-c", "plan")
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    git(repo, "switch", "-q", "main")
    commit(repo, {"other.txt": "x\n"}, "main moves")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "plan")
    (repo / "plans/U9.toml").write_text(PLAN.replace('"src/"', '"src/", "secrets/"'), newline="\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "merge that rewrites the plan")
    assert run(repo) == 1
    assert "a merge rewrote it" in capsys.readouterr().out


@pytest.mark.parametrize("text, message", [
    (PLAN.replace('id = "U9"', 'id = "U8"'), "does not match the file name"),
    (PLAN.replace('allowed_paths = ["src/"]\n', ""), "'allowed_paths' is a required property"),
    (PLAN.replace('"src/"', '"../src/"'), "does not match"),
    (PLAN + 'extra = "x"\n', "Additional properties"),
    ("id = ", "not valid TOML"),
])
def test_invalid_plan_fails(repo, keys, capsys, text, message):
    commit(repo, {"plans/U9.toml": text}, "plan", keys["owner"])
    assert run(repo) == 1
    assert message in capsys.readouterr().out


def test_missing_ssh_keygen_fails_with_reason(repo, keys, capsys, monkeypatch):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    monkeypatch.setattr(verify.shutil, "which", lambda name: None)
    assert run(repo) == 1
    assert "could not run: ssh-keygen not on PATH" in capsys.readouterr().out


def test_invalid_plan_id_fails(repo):
    assert run(repo, plan_id="../U9") == 1


@pytest.mark.skipif(shutil.which("gpg") is None, reason="needs gpg")
def test_trusted_openpgp_signature_fails(repo, monkeypatch, capsys):
    # A short home: gpg-agent's socket path breaks under pytest's deep tmp_path.
    home = Path(tempfile.mkdtemp(prefix="g")).resolve()
    # Git for Windows ships an MSYS gpg, which reads GNUPGHOME only as a POSIX path.
    monkeypatch.setenv("GNUPGHOME", f"/{home.drive[0].lower()}{home.as_posix()[2:]}" if home.drive else str(home))
    try:
        _sign_plan_with_trusted_openpgp_key(repo)
        assert run(repo) == 1
        assert "carries no SSH signature" in capsys.readouterr().out
    finally:
        subprocess.run(["gpgconf", "--kill", "gpg-agent"], capture_output=True)
        shutil.rmtree(home, ignore_errors=True)


def _sign_plan_with_trusted_openpgp_key(repo):
    subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key", PRINCIPAL, "ed25519", "sign", "never"],
                   check=True, capture_output=True)
    (repo / "plans").mkdir()
    (repo / "plans/U9.toml").write_text(PLAN, newline="\n")
    git(repo, "add", "-A")
    git(repo, "-c", "gpg.format=openpgp", "-c", f"user.signingkey={PRINCIPAL}", "commit", "-S", "-q", "-m", "plan")
    assert git(repo, "log", "-1", "--format=%G?").strip() == "G"  # git itself trusts it


def test_shallow_clone_fails_with_reason(repo, keys, tmp_path, capsys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", repo.resolve().as_uri(), str(shallow)],
                   check=True, capture_output=True)
    assert run(shallow, ref="origin/main", signers_ref="origin/main") == 1
    assert "shallow clone" in capsys.readouterr().out


def test_failed_blob_lookup_fails(repo, keys, monkeypatch, capsys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    real = verify._blob
    monkeypatch.setattr(verify, "_blob", lambda r, rev, path: None if rev != "main" else real(r, rev, path))
    assert run(repo) == 1
    assert "could not run: git could not read" in capsys.readouterr().out


def test_git_that_cannot_start_fails_with_reason(repo, monkeypatch, capsys):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(verify.subprocess, "run", no_git)
    assert run(repo) == 1
    assert "could not run" in capsys.readouterr().out


def test_unwritable_temp_dir_fails_with_reason(repo, keys, monkeypatch, capsys):
    commit(repo, {"plans/U9.toml": PLAN}, "plan", keys["owner"])
    def denied(*args, **kwargs):
        raise PermissionError("temp dir denied")
    monkeypatch.setattr(verify.tempfile, "TemporaryDirectory", denied)
    assert run(repo) == 1
    assert "could not write a temporary allowed_signers file" in capsys.readouterr().out
