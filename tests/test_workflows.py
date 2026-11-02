"""The CI rules a script can read from the workflow files, and the behaviours gate.yml relies on."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
from test_floor import make, no_ci_branch  # noqa: F401
from test_plan_verify import commit, keys  # noqa: F401
from test_release_gate import TERM, denylist, init, key, needs_gitleaks, token  # noqa: F401

from tiller_book import cli

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
GATES = sorted(p for p in WORKFLOWS.glob("*.yml") if p.name != "docs-lint.yml")  # docs-lint is the public template


def jobs(text):
    """Map each job name to its text. shortcut: reads the two-space layout these files use, not YAML in general."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([A-Za-z0-9_-]+):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_gate_exists():
    assert "gate.yml" in [p.name for p in GATES]


@pytest.mark.parametrize("path", GATES, ids=lambda p: p.name)
def test_definition_comes_from_main(path):
    text = path.read_text(encoding="utf-8")
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "pull_request_target:" in triggers or "workflow_run:" in triggers
    assert not re.search(r"^  pull_request:", triggers, re.M)
    assert "\npermissions: {}\n" in text


@pytest.mark.parametrize("path", GATES, ids=lambda p: p.name)
def test_actions_are_pinned_and_credentials_dropped(path):
    text = path.read_text(encoding="utf-8")
    for used in re.findall(r"uses:\s*(\S+)", text):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", used), used
    assert text.count("actions/checkout@") == text.count("persist-credentials: false")


@pytest.mark.parametrize("path", GATES, ids=lambda p: p.name)
def test_pull_request_text_never_reaches_a_shell(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        for expr in re.findall(r"\$\{\{(.*?)\}\}", line):
            assert not re.search(r"title|body|head_ref|head\.ref|label|message|comment", expr), line


def test_a_job_that_runs_pull_request_code_holds_nothing():
    text = (WORKFLOWS / "gate.yml").read_text(encoding="utf-8")
    runs_pr_code = {name: job for name, job in jobs(text).items() if "pytest" in job or "install --quiet -e" in job}
    assert list(runs_pr_code) == ["tests"]
    job = runs_pr_code["tests"]
    assert "permissions: {}" in job and "secrets." not in job and "github.token" not in job


def test_jobs_that_read_a_secret_only_install_from_main():
    for name, job in jobs((WORKFLOWS / "gate.yml").read_text(encoding="utf-8")).items():
        if "secrets." in job:
            assert "install --quiet ./trusted" in job and "-I -m tiller_book" in job, name
            assert "working-directory: pr" not in job, name


def test_the_gate_runs_on_main_only_and_each_checkout_names_an_immutable_commit():
    text = (WORKFLOWS / "gate.yml").read_text(encoding="utf-8")
    assert "    branches: [main]\n" in text
    refs = re.findall(r"^\s+ref: (.+)$", text, re.M)
    assert refs.count("${{ github.workflow_sha }}") == 2
    assert refs.count("${{ github.event.pull_request.head.sha }}") == 3 and len(refs) == 5
    for name, job in jobs(text).items():
        assert "= \"$HEAD_SHA\"" in job, name  # each job confirms what it checked out


def test_every_gate_job_can_fail_closed():
    # a job skipped by an `if` counts as success for a required check
    for name, job in jobs((WORKFLOWS / "gate.yml").read_text(encoding="utf-8")).items():
        assert not re.search(r"^\s+if:", job, re.M), name
        assert "continue-on-error" not in job, name


def test_isolated_python_ignores_a_tiller_book_folder_in_the_pull_request(make):
    work = make()
    fake = work / "tiller_book" / "checks" / "floor"
    fake.mkdir(parents=True)
    for folder in (work / "tiller_book", work / "tiller_book" / "checks", fake):
        (folder / "__init__.py").write_text("")
    (fake / "path_scope.py").write_text("print('PASS: pull request code ran')\n")

    def run(*flags):
        return subprocess.run([sys.executable, *flags, "-m", "tiller_book.checks.floor.path_scope"],
                              cwd=work, capture_output=True, text=True)

    assert "pull request code ran" in run().stdout  # the danger is real without -I
    isolated = run("-I")
    assert "pull request code ran" not in isolated.stdout
    assert isolated.returncode == 0 and isolated.stdout.startswith("PASS: "), isolated.stdout + isolated.stderr  # the real one ran


def scan(repo, denylist, capsys):
    code = cli.main(["release", "scan", "--denylist", str(denylist), "--repo", str(repo)])
    return code, capsys.readouterr().out


@needs_gitleaks
def test_scan_passes_a_clean_repository(tmp_path, key, denylist, capsys):
    repo = init(tmp_path / "pr", key)
    code, out = scan(repo, denylist, capsys)
    assert code == 0, out
    assert [line.split()[1] for line in out.splitlines()[:3]] == ["deny-list:", "identities:", "leak-scan:"]


@needs_gitleaks
def test_a_seeded_secret_fails_and_a_config_in_the_repository_cannot_stop_it(tmp_path, key, denylist, capsys):
    repo = init(tmp_path / "pr", key)
    commit(repo, {"config.txt": f"token = {token()}\n",
                  ".gitleaks.toml": "[allowlist]\npaths = ['.*']\n", ".gitleaksignore": "*\n"}, "seed", None)
    code, out = scan(repo, denylist, capsys)
    assert code == 1 and "FAIL leak-scan" in out, out


@needs_gitleaks
def test_a_seeded_term_fails_the_scan_without_printing_it(tmp_path, key, denylist, capsys):
    repo = init(tmp_path / "pr", key)
    commit(repo, {"notes.txt": f"{TERM}\n"}, "seed", None)
    code, out = scan(repo, denylist, capsys)
    assert code == 1 and "FAIL deny-list" in out and TERM not in out, out


def test_scan_fails_closed_on_a_missing_or_empty_deny_list(tmp_path, key, capsys):
    repo = init(tmp_path / "pr", key)
    empty = tmp_path / "empty.txt"
    empty.write_text("\n")
    for path in (empty, tmp_path / "absent.txt"):
        code, out = scan(repo, path, capsys)
        assert code == 1 and "FAIL deny-list: could not run" in out, out
