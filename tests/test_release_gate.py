"""tlb release gate against throwaway repositories, a throwaway SSH key and an invented deny-list."""

import hashlib
import random
import shutil
import string
import subprocess
import sys

import pytest
from test_plan_verify import commit, git, keygen, signers_line

from tiller_book import cli, release
from tiller_book.checks import Check, registry
from tiller_book.plan import verify

NOREPLY = "1+test@users.noreply.github.com"
VISION = "# Vision\n\nInvented text for a test.\n"
TERM = "zorblatt"  # invented, like everything below; none of it is in any real deny-list
ADDR = "quillfen@oxbrindle.example"
SECRETS = (TERM, "quillfen", "oxbrindle")
REAL_WHICH = shutil.which

pytestmark = pytest.mark.skipif(REAL_WHICH("ssh-keygen") is None or REAL_WHICH("grep") is None,
                                reason="needs ssh-keygen and grep")
needs_gitleaks = pytest.mark.skipif(REAL_WHICH("gitleaks") is None, reason="needs gitleaks")


def lock_text(vision):
    return f"{hashlib.sha256(vision.encode()).hexdigest()} *VISION.md\n"


def publish(repo):
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def commit_bytes(repo, name, data, message):
    (repo / name).write_bytes(data)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def token():
    return "ghp_" + "".join(random.choices(string.ascii_letters + string.digits, k=36))  # built at run time


def clean(out):
    """No invented term or address placed in the triggering input reaches the gate's output."""
    assert not [s for s in SECRETS if s in out.lower()], out
    assert "Traceback" not in out


def init(path, key):
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    for k, v in {"user.email": NOREPLY, "user.name": "Test", "commit.gpgsign": "false",
                 "gpg.format": "ssh", "core.autocrlf": "false"}.items():
        git(path, "config", k, v)
    commit(path, {".github/allowed_signers": signers_line(key)}, "bootstrap", key)
    return path


@pytest.fixture(autouse=True)
def passing_checks(monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", [Check("ok", (sys.executable, "-c", "pass"))])


@pytest.fixture
def key(tmp_path):
    return keygen(tmp_path / "owner")


@pytest.fixture
def repo(tmp_path, key):
    r = init(tmp_path / "repo", key)
    commit(r, {"VISION.md": VISION, "locks/VISION.md.sha256": lock_text(VISION)}, "lock vision", key)
    publish(r)
    return r


@pytest.fixture
def denylist(tmp_path):
    p = tmp_path / "deny.txt"
    p.write_text(f"{TERM}\nquillfen\n", newline="\n")
    return p


def run(repo, denylist, capsys):
    code = cli.main(["release", "gate", "--denylist", str(denylist), "--repo", str(repo)])
    return code, capsys.readouterr().out


def step(out, name):
    return next(line for line in out.splitlines() if line.split(" ", 1)[1].startswith(f"{name}:"))


def fails(repo, denylist, capsys, name):
    code, out = run(repo, denylist, capsys)
    assert code == 1 and step(out, name).startswith(f"FAIL {name}: "), out
    clean(out)
    return step(out, name)


@needs_gitleaks
def test_clean_repository_passes_every_step(repo, denylist, capsys):
    code, out = run(repo, denylist, capsys)
    assert code == 0, out
    for name in ("head", "deny-list", "identities", "leak-scan", "vision-lock", "checks"):
        assert step(out, name).startswith("PASS ")
    assert out.splitlines()[-1] == "PASS: all 6 release steps passed"


# head

def test_head_not_origin_main_fails(repo, denylist, capsys):
    commit(repo, {"later.txt": "x\n"}, "not yet on main")
    assert "is not origin/main" in fails(repo, denylist, capsys, "head")


def test_head_failure_prints_no_commit_text_or_address(repo, denylist, capsys):
    git(repo, "-c", f"user.email={ADDR}", "commit", "-q", "--allow-empty", "-m", f"{TERM} {ADDR}")
    fails(repo, denylist, capsys, "head")


# deny-list

def test_deny_list_hit_is_reported_by_count_without_the_text(repo, denylist, capsys):
    commit(repo, {"notes.txt": f"a Zorblatt here\nand {ADDR.upper()} there\nclean line\n"}, "notes mention zorblatt")
    publish(repo)
    assert fails(repo, denylist, capsys, "deny-list").startswith(
        "FAIL deny-list: 2 matching lines in 1 files at HEAD, 3 matching lines across ")


def test_deny_list_hit_in_history_only_fails(repo, denylist, capsys):
    commit(repo, {"notes.txt": f"{TERM}\n"}, "add")
    commit(repo, {"notes.txt": "gone\n"}, "remove")
    publish(repo)
    assert fails(repo, denylist, capsys, "deny-list").startswith(
        "FAIL deny-list: 0 matching lines in 0 files at HEAD, 1 matching lines across ")


def test_deny_list_hit_introduced_only_by_a_merge_commit_fails(repo, denylist, capsys):
    git(repo, "switch", "-q", "-c", "side")
    commit(repo, {"side.txt": "side\n"}, "side")
    git(repo, "switch", "-q", "main")
    commit(repo, {"main.txt": "main\n"}, "main")
    git(repo, "merge", "-q", "--no-commit", "--no-ff", "side")
    (repo / "evil.txt").write_text(f"{TERM}\n", newline="\n")
    git(repo, "add", "evil.txt")
    git(repo, "commit", "-q", "-m", "merge side")
    commit(repo, {"evil.txt": "clean\n"}, "tidy")
    publish(repo)
    reason = fails(repo, denylist, capsys, "deny-list")
    assert reason.startswith("FAIL deny-list: 0 matching lines in 0 files at HEAD, ")
    assert "0 matching lines across" not in reason


def test_binary_file_at_head_fails(repo, denylist, capsys):
    commit_bytes(repo, "blob.bin", b"\x00\x01" + TERM.encode() + b"\x00\xff", "add data")
    publish(repo)
    fails(repo, denylist, capsys, "deny-list")


def test_binary_file_only_in_history_fails(repo, denylist, capsys):
    commit_bytes(repo, "blob.bin", b"\x00\x01" + TERM.encode() + b"\x00\xff", "add data")
    git(repo, "rm", "-q", "blob.bin")
    git(repo, "commit", "-q", "-m", "remove data")
    publish(repo)
    assert "0 files at HEAD" in fails(repo, denylist, capsys, "deny-list")


def test_annotated_tag_message_fails(repo, denylist, capsys):
    git(repo, "tag", "-a", "v1", "-m", f"release {TERM}")
    fails(repo, denylist, capsys, "deny-list")


def test_ref_pointing_at_a_blob_fails(repo, denylist, capsys, tmp_path):
    loose = tmp_path / "loose.txt"
    loose.write_text(f"{TERM}\n", newline="\n")
    blob = git(repo, "hash-object", "-w", str(loose)).strip()
    git(repo, "update-ref", "refs/tags/loose", blob)
    fails(repo, denylist, capsys, "deny-list")


def test_git_note_fails(repo, denylist, capsys):
    git(repo, "notes", "add", "-m", TERM, "HEAD")
    fails(repo, denylist, capsys, "deny-list")


def test_root_commit_on_another_branch_fails_with_show_root_off(repo, denylist, capsys):
    git(repo, "config", "log.showRoot", "false")
    git(repo, "switch", "-q", "--orphan", "other")
    commit(repo, {"root.txt": f"{TERM}\n"}, "root")
    git(repo, "switch", "-q", "main")
    fails(repo, denylist, capsys, "deny-list")


def write_object(repo, kind, body):
    return subprocess.run(["git", "-C", str(repo), "hash-object", "-t", kind, "-w", "--stdin"], input=body,
                          capture_output=True, check=True).stdout.decode().strip()


def crafted_commit(repo, signature_text, message):
    tree, parent = git(repo, "rev-parse", "HEAD^{tree}").strip(), git(repo, "rev-parse", "HEAD").strip()
    who = f"Test <{NOREPLY}> 1700000000 +0000"
    body = (f"tree {tree}\nparent {parent}\nauthor {who}\ncommitter {who}\n"
            f"gpgsig -----BEGIN PGP SIGNATURE-----\n \n wsBc{signature_text}AA==\n =ab12\n -----END PGP SIGNATURE-----\n"
            f"\n{message}\n")
    git(repo, "update-ref", "refs/heads/main", write_object(repo, "commit", body.encode()))
    publish(repo)


def test_term_inside_a_commit_signature_header_is_not_counted(repo, denylist, capsys):
    crafted_commit(repo, TERM, "web merge")
    assert step(run(repo, denylist, capsys)[1], "deny-list").startswith("PASS deny-list: 0 matching lines")


def test_term_in_the_commit_message_is_counted(repo, denylist, capsys):
    crafted_commit(repo, TERM, f"merge {TERM}")
    assert " 1 matching lines across " in fails(repo, denylist, capsys, "deny-list")


def test_term_inside_a_tag_signature_block_is_not_counted(repo, denylist, capsys):
    head = git(repo, "rev-parse", "HEAD").strip()
    body = (f"object {head}\ntype commit\ntag v1\ntagger Test <{NOREPLY}> 1700000000 +0000\n\nrelease\n"
            f"-----BEGIN SSH SIGNATURE-----\nU1NIU0lH{TERM}AAAA\n-----END SSH SIGNATURE-----\n")
    git(repo, "update-ref", "refs/tags/v1", write_object(repo, "tag", body.encode()))
    assert step(run(repo, denylist, capsys)[1], "deny-list").startswith("PASS deny-list: 0 matching lines")


def test_fake_signature_block_in_a_file_is_counted(repo, denylist, capsys):
    fake = f"gpgsig {TERM}\n-----BEGIN PGP SIGNATURE-----\n\n{TERM}\n-----END PGP SIGNATURE-----\n"
    commit(repo, {"fake.txt": fake}, "add a file")
    publish(repo)
    assert fails(repo, denylist, capsys, "deny-list").startswith(
        "FAIL deny-list: 2 matching lines in 1 files at HEAD, 2 matching lines across ")


def test_term_in_a_path_name_is_counted(repo, denylist, capsys):
    commit(repo, {f"docs/{TERM}/notes.txt": "clean\n"}, "add a file")
    publish(repo)
    assert fails(repo, denylist, capsys, "deny-list").startswith(
        "FAIL deny-list: 0 matching lines in 0 files at HEAD, ")


def test_replaced_blob_is_scanned_as_stored(repo, denylist, capsys, tmp_path):
    commit(repo, {"notes.txt": f"{TERM}\n"}, "add")
    publish(repo)
    stored = git(repo, "rev-parse", "HEAD:notes.txt").strip()
    cover = tmp_path / "cover.txt"
    cover.write_text("clean\n", newline="\n")
    git(repo, "replace", stored, git(repo, "hash-object", "-w", str(cover)).strip())
    assert git(repo, "show", "HEAD:notes.txt") == "clean\n"  # git itself now shows the replacement
    fails(repo, denylist, capsys, "deny-list")


def test_name_of_a_renamed_file_with_unchanged_content_is_counted(repo, denylist, capsys):
    commit(repo, {f"{TERM}.txt": "clean\n"}, "add")
    git(repo, "mv", f"{TERM}.txt", "clean.txt")
    git(repo, "commit", "-q", "-m", "rename")
    publish(repo)
    assert fails(repo, denylist, capsys, "deny-list").startswith(
        "FAIL deny-list: 0 matching lines in 0 files at HEAD, 1 matching lines across ")


def test_pattern_spanning_a_historical_directory_and_file_name_is_counted(repo, tmp_path, capsys):
    deny = tmp_path / "paths.txt"
    deny.write_text("plumbar/vexmoor\n", newline="\n")
    commit(repo, {"plumbar/vexmoor.txt": "clean\n"}, "add")
    git(repo, "mv", "plumbar/vexmoor.txt", "clean.txt")
    git(repo, "commit", "-q", "-m", "move")
    publish(repo)
    assert fails(repo, deny, capsys, "deny-list").startswith(
        "FAIL deny-list: 0 matching lines in 0 files at HEAD, 1 matching lines across ")


def test_grafts_file_fails_the_head_step(repo, denylist, capsys):
    commit(repo, {"notes.txt": f"{TERM}\n"}, "add")
    commit(repo, {"notes.txt": "gone\n"}, "remove")
    publish(repo)
    hidden_parent_cut = git(repo, "rev-parse", "HEAD").strip()
    grafts = repo / git(repo, "rev-parse", "--git-path", "info/grafts").strip()
    grafts.parent.mkdir(parents=True, exist_ok=True)
    grafts.write_text(hidden_parent_cut + "\n", newline="\n")
    assert "a grafts file exists" in fails(repo, denylist, capsys, "head")


def test_graft_file_variable_fails_the_head_step(repo, denylist, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_GRAFT_FILE", str(tmp_path / "grafts"))
    assert "GIT_GRAFT_FILE is set" in fails(repo, denylist, capsys, "head")


def test_shallow_clone_fails_the_head_step(repo, denylist, capsys, tmp_path):
    commit(repo, {"more.txt": "x\n"}, "more")
    publish(repo)
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", "-c", "core.autocrlf=false", repo.as_uri(), "shallow")
    assert "the clone is shallow" in fails(shallow, denylist, capsys, "head")


def test_term_in_a_branch_name_is_counted(repo, denylist, capsys):
    git(repo, "branch", f"{TERM}-work")
    fails(repo, denylist, capsys, "deny-list")


def test_object_only_in_the_reflog_is_not_scanned(repo, denylist, capsys):
    commit(repo, {"notes.txt": f"{TERM}\n"}, "dropped before publishing")
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    assert step(run(repo, denylist, capsys)[1], "deny-list").startswith("PASS deny-list: 0 matching lines")


def test_uncommitted_working_tree_text_is_not_what_the_gate_scans(repo, denylist, capsys):
    (repo / "VISION.md").write_text(f"{TERM}\n", newline="\n")
    code, out = run(repo, denylist, capsys)
    assert step(out, "deny-list").startswith("PASS deny-list: 0 matching lines in 0 files at HEAD, 0 ")


def test_crlf_deny_list_still_matches(repo, tmp_path, capsys):
    crlf = tmp_path / "crlf.txt"
    crlf.write_bytes(TERM.encode() + b"\r\n")
    commit(repo, {"notes.txt": f"{TERM}\n"}, "add")
    publish(repo)
    assert fails(repo, crlf, capsys, "deny-list").startswith("FAIL deny-list: 1 matching lines")


def test_missing_deny_list_fails_without_the_path(repo, tmp_path, capsys):
    reason = fails(repo, tmp_path / f"{TERM}-{ADDR}.txt", capsys, "deny-list")
    assert reason == "FAIL deny-list: could not run: deny-list file not readable"


def test_deny_list_with_no_patterns_fails(repo, tmp_path, capsys):
    blank = tmp_path / f"{TERM}.txt"
    blank.write_text("\n  \n")
    assert fails(repo, blank, capsys, "deny-list") == "FAIL deny-list: could not run: deny-list file has no patterns"


def test_invalid_pattern_fails_without_echoing_it(repo, tmp_path, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_text(f"{TERM}[\n{ADDR}\n", newline="\n")
    assert "could not run: git grep exited" in fails(repo, bad, capsys, "deny-list")


def test_missing_grep_fails(repo, tmp_path, capsys, monkeypatch):
    deny = tmp_path / f"{TERM}.txt"
    deny.write_text(f"{TERM}\n")
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "grep" else REAL_WHICH(name))
    assert fails(repo, deny, capsys, "deny-list") == "FAIL deny-list: could not run: grep not on PATH"


# identities

def test_non_noreply_identity_fails_without_the_address(repo, denylist, capsys):
    git(repo, "-c", f"user.email={ADDR}", "commit", "-q", "--allow-empty", "-m", "other identity")
    publish(repo)
    assert fails(repo, denylist, capsys, "identities").startswith(
        "FAIL identities: 1 of 2 author, committer and tagger addresses")


def test_web_flow_committer_passes_identities(repo, denylist, capsys):
    git(repo, "-c", "user.email=noreply@github.com", "commit", "-q", "--allow-empty", "-m", "web merge")
    publish(repo)
    assert step(run(repo, denylist, capsys)[1], "identities").startswith("PASS identities: all 2")


def test_personal_tagger_address_fails_without_the_address(repo, denylist, capsys):
    git(repo, "-c", f"user.email={ADDR}", "tag", "-a", "v1", "-m", "release")
    assert fails(repo, denylist, capsys, "identities").startswith(
        "FAIL identities: 1 of 2 author, committer and tagger addresses")


def tag_chain(repo, inner_message, inner_email=NOREPLY, depth=3):
    """Tag a tag a tag; only the outermost tag keeps a ref."""
    git(repo, "-c", f"user.email={inner_email}", "tag", "-a", "level1", "-m", inner_message)
    for n in range(2, depth + 1):
        git(repo, "-c", "advice.nestedTag=false", "tag", "-a", f"level{n}", f"level{n - 1}", "-m", f"level {n}")
    git(repo, "tag", "-d", *[f"level{n}" for n in range(1, depth)])


def test_personal_tagger_on_an_inner_tag_fails(repo, denylist, capsys):
    tag_chain(repo, "inner", inner_email=ADDR, depth=2)
    assert git(repo, "for-each-ref", "--format=%(refname)", "refs/tags") == "refs/tags/level2\n"
    assert "1 of 2 author, committer and tagger addresses" in fails(repo, denylist, capsys, "identities")


def test_personal_tagger_under_another_ref_namespace_fails(repo, denylist, capsys):
    git(repo, "-c", f"user.email={ADDR}", "tag", "-a", "archived", "-m", "old")
    git(repo, "update-ref", "refs/archive/inner", git(repo, "rev-parse", "refs/tags/archived").strip())
    git(repo, "tag", "-d", "archived")
    assert "1 of 2 author, committer and tagger addresses" in fails(repo, denylist, capsys, "identities")


def test_noreply_tagger_and_lightweight_tag_pass_identities(repo, denylist, capsys):
    git(repo, "-c", "user.email=noreply@github.com", "tag", "-a", "v1", "-m", "release")
    git(repo, "tag", "light")
    assert step(run(repo, denylist, capsys)[1], "identities") == (
        "PASS identities: all 2 author, committer and tagger addresses are GitHub noreply addresses")


# leak-scan

@needs_gitleaks
def test_leaked_secret_in_a_commit_fails_leak_scan(repo, denylist, capsys):
    secret = token()
    commit(repo, {"config.txt": f"token = {secret}\n"}, "oops")
    publish(repo)
    reason = fails(repo, denylist, capsys, "leak-scan")
    assert reason.startswith("FAIL leak-scan: gitleaks git exit 1, gitleaks dir exit 0")
    assert secret not in reason


@needs_gitleaks
def test_leaked_secret_in_an_annotated_tag_message_fails_leak_scan(repo, denylist, capsys):
    secret = token()
    git(repo, "tag", "-a", "v1", "-m", f"token = {secret}")
    code, out = run(repo, denylist, capsys)
    assert step(out, "leak-scan").startswith("FAIL leak-scan: gitleaks git exit 0, gitleaks dir exit 1"), out
    assert secret not in out


@needs_gitleaks
def test_leaked_secret_in_the_innermost_of_three_tags_fails_leak_scan(repo, denylist, capsys):
    secret = token()
    tag_chain(repo, f"token = {secret}")
    code, out = run(repo, denylist, capsys)
    assert step(out, "leak-scan").startswith("FAIL leak-scan: gitleaks git exit 0, gitleaks dir exit 1"), out
    assert secret not in out


@needs_gitleaks
def test_gitleaks_config_error_prints_none_of_its_output(repo, denylist, capsys):
    commit(repo, {".gitleaks.toml": f"[[rules]]\nid = \"{TERM} {ADDR}\"\nregex = '''(['''\n"}, "config")
    publish(repo)
    fails(repo, denylist, capsys, "leak-scan")


def test_missing_gitleaks_fails(repo, denylist, capsys, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "gitleaks" else REAL_WHICH(name))
    assert fails(repo, denylist, capsys, "leak-scan") == "FAIL leak-scan: could not run: gitleaks not on PATH"


# vision-lock

def test_unsigned_vision_edit_fails(repo, denylist, capsys):
    edited = VISION + f"{TERM} {ADDR}\n"
    commit(repo, {"VISION.md": edited, "locks/VISION.md.sha256": lock_text(edited)}, "unsigned edit")
    publish(repo)
    assert "is not as written by a commit signed" in fails(repo, denylist, capsys, "vision-lock")


def test_signed_lock_with_wrong_hash_fails(repo, denylist, key, capsys):
    commit(repo, {"VISION.md": VISION + "More.\n"}, "signed edit, lock not updated", key)
    publish(repo)
    assert fails(repo, denylist, capsys, "vision-lock") == "FAIL vision-lock: lock hash does not match VISION.md"


def test_lock_field_is_never_printed(repo, denylist, key, capsys):
    commit(repo, {"locks/VISION.md.sha256": f"{TERM}-{ADDR} *VISION.md\n"}, "signed bad lock", key)
    publish(repo)
    assert fails(repo, denylist, capsys, "vision-lock") == "FAIL vision-lock: lock hash does not match VISION.md"


def test_crlf_vision_against_the_lf_hash_fails(repo, denylist, key, capsys):
    crlf = VISION.replace("\n", "\r\n")
    (repo / "VISION.md").write_bytes(crlf.encode())
    (repo / "locks/VISION.md.sha256").write_text(lock_text(VISION), newline="\n")
    git(repo, "add", "-A")
    git(repo, "-c", f"user.signingkey={key.as_posix()}", "commit", "-S", "-q", "-m", "crlf vision")
    publish(repo)
    stored = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", "HEAD:VISION.md"], capture_output=True)
    assert b"\r\n" in stored.stdout
    assert fails(repo, denylist, capsys, "vision-lock") == "FAIL vision-lock: lock hash does not match VISION.md"


def test_vision_missing_on_origin_main_fails(tmp_path, key, denylist, capsys):
    r = init(tmp_path / "bare", key)
    publish(r)
    assert fails(r, denylist, capsys, "vision-lock") == "FAIL vision-lock: VISION.md missing on origin/main"


def test_lock_missing_on_origin_main_fails(tmp_path, key, denylist, capsys):
    r = init(tmp_path / "nolock", key)
    commit(r, {"VISION.md": VISION}, "vision without a lock", key)
    publish(r)
    assert fails(r, denylist, capsys, "vision-lock") == ("FAIL vision-lock: locks/VISION.md.sha256 "
                                                         "missing on origin/main")


def test_missing_ssh_keygen_fails(repo, denylist, capsys, monkeypatch):
    monkeypatch.setattr(verify.shutil, "which", lambda name: None if name == "ssh-keygen" else REAL_WHICH(name))
    assert fails(repo, denylist, capsys, "vision-lock") == "FAIL vision-lock: could not run: ssh-keygen not on PATH"


def test_signature_check_that_cannot_run_prints_only_its_class(repo, denylist, capsys, monkeypatch):
    def broken(*args):
        raise verify.CouldNotRun(f"{TERM} {ADDR}")
    monkeypatch.setattr(release, "signed_on_ref", broken)
    assert fails(repo, denylist, capsys, "vision-lock") == "FAIL vision-lock: could not run: CouldNotRun in vision-lock"


# checks

def test_failing_registered_check_fails_without_its_output(repo, denylist, capsys, monkeypatch):
    noisy = Check("bad", (sys.executable, "-c", f"print('{TERM} {ADDR}'); raise SystemExit(3)"))
    monkeypatch.setattr(registry, "CHECKS", [noisy])
    assert fails(repo, denylist, capsys, "checks") == "FAIL checks: required checks not PASS: bad"


# any step

def test_exception_prints_only_its_class_and_step(repo, denylist, capsys, monkeypatch):
    def broken(repo):
        raise RuntimeError(f"{TERM} {ADDR}")
    monkeypatch.setattr(release, "identities", broken)
    assert fails(repo, denylist, capsys, "identities") == "FAIL identities: could not run: RuntimeError in identities"


def test_not_a_repository_fails_every_step_without_traceback(tmp_path, denylist, capsys, monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", [Check("ghost", ("tlb-no-such-binary-xyz",))])
    plain = tmp_path / TERM
    plain.mkdir()
    code, out = run(plain, denylist, capsys)
    assert code == 1
    assert [line.split(":", 1)[0] for line in out.splitlines() if line.startswith("FAIL ")] == [
        "FAIL head", "FAIL deny-list", "FAIL identities", "FAIL leak-scan", "FAIL vision-lock", "FAIL checks"]
    clean(out)
