"""tlb receipt write against throwaway repositories, with fast fake checks in place of the real suite."""

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from test_checks import SCHEMA, fails, ok
from test_floor import check, keys, make, no_ci_branch, work  # noqa: F401 - fixtures
from test_plan_verify import commit, git, pytestmark  # noqa: F401
from tiller_book import cli
from tiller_book.checks import registry
from tiller_book.checks.floor import receipt

VALIDATOR = Draft202012Validator(SCHEMA)


@pytest.fixture(autouse=True)
def fake_checks(monkeypatch):
    # receipt fails if it ever runs, so a test sees the default skip break
    monkeypatch.setattr(registry, "CHECKS", [ok("tests"), ok("path-scope"), fails("receipt")])


def write(repo, capsys, *args, unit="U9"):
    code = cli.main(["receipt", "write", unit, "--repo", str(repo), *args])
    return code, capsys.readouterr().out.strip()


def written(repo, unit="U9"):
    return json.loads((repo / "receipts" / f"{unit}.json").read_text(encoding="utf-8"))


def code_commit(repo):
    commit(repo, {"src/a.py": "a\n"}, "code")


def test_no_model_calls_receipt_validates_and_passes_the_receipt_check_once_committed(work, capsys):
    code_commit(work)
    head = git(work, "rev-parse", "HEAD").strip()
    assert write(work, capsys, "--agent", "claude-code", "--model", "m1") == (
        0, "PASS: wrote receipts/U9.json; commit it alone as the last commit")
    text = (work / "receipts" / "U9.json").read_text(encoding="utf-8")
    data = json.loads(text)
    assert text == json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    assert not list(VALIDATOR.iter_errors(data))
    assert data["runner"] == {"agent": "claude-code", "model": "m1"}
    assert data["commits"] == {"start": git(work, "merge-base", "origin/main", "HEAD").strip(), "head": head}
    assert [c["name"] for c in data["checks"]] == ["tests", "path-scope"]
    assert data["not_measured"] == [{"claim": "receipt check, skipped by the writer", "command": "tlb check run"}]
    assert write(work, capsys)[0] == 0  # an untracked receipt from an earlier run does not block a rerun
    assert written(work)["runner"] == {"agent": "unknown"}
    git(work, "add", "receipts/U9.json")
    git(work, "commit", "-q", "-m", "receipt")
    assert check(receipt, work, capsys) == (0, "PASS: receipts/U9.json is valid and names the head commit's parent")


def test_model_call_with_unmeasured_cost_gets_null_cost_and_a_not_measured_entry(work, capsys):
    code_commit(work)
    assert write(work, capsys, "--model-call", "m1,10,20,-", "--model-call", "m2,1,2,0.5",
                 "--model-call", "m1,3,4,-")[0] == 0
    data = written(work)
    assert data["model_calls"] == [
        {"model": "m1", "input_tokens": 10, "output_tokens": 20, "cost_usd": None},
        {"model": "m2", "input_tokens": 1, "output_tokens": 2, "cost_usd": 0.5},
        {"model": "m1", "input_tokens": 3, "output_tokens": 4, "cost_usd": None}]
    assert data["not_measured"][1:] == [{"claim": "cost of m1 call", "command": "report the cost from the model session"}]
    assert not list(VALIDATOR.iter_errors(data))


def test_caller_not_measured_entry_replaces_the_automatic_one(work, capsys):
    code_commit(work)
    assert write(work, capsys, "--model-call", "m1,10,20,-",
                 "--not-measured", "cost of m1 call=/cost in that session",
                 "--evidence", "notes, review=round one verdict")[0] == 0
    data = written(work)
    assert data["not_measured"] == [{"claim": "cost of m1 call", "command": "/cost in that session"},
                                    {"claim": "receipt check, skipped by the writer", "command": "tlb check run"}]
    assert data["evidence"] == [{"location": "notes, review", "what": "round one verdict"}]


@pytest.mark.parametrize("call, reason", [
    ("m1,10,20", "expected MODEL,INPUT_TOKENS,OUTPUT_TOKENS,COST_USD"),
    ("m1,10,20,0.1,x", "expected MODEL,INPUT_TOKENS,OUTPUT_TOKENS,COST_USD"),
    ("m1,ten,20,0.1", "token counts must be whole numbers"),
    ("m1,-1,20,0.1", "token counts must be whole numbers"),
    ("m1,1.5,20,0.1", "token counts must be whole numbers"),
    ("m1,10,20,-0.1", "cost must be a finite number of at least 0"),
    ("m1,10,20,nan", "cost must be a finite number of at least 0"),
    ("m1,10,20,free", "cost must be a number or -"),
    (",10,20,0.1", "$.model_calls[0].model"),
])
def test_malformed_model_call_exits_1_and_writes_nothing(work, capsys, call, reason):
    code_commit(work)
    code, out = write(work, capsys, "--model-call", call)
    assert code == 1 and out.startswith("FAIL: ") and reason in out
    assert not (work / "receipts").exists()


@pytest.mark.parametrize("items, reason", [
    ([{"name": "review round one", "command": "codex exec", "status": "FAIL", "exit_code": 0}],
     "$.checks[2]: 'reason' is a required property"),
    ([{"name": "review", "command": "codex exec", "status": "DONE", "exit_code": 0, "reason": "x"}],
     "$.checks[2].status: 'DONE' is not one of"),
    ({"name": "review"}, "expected a JSON list"),
    ("not json", "not valid JSON"),
])
def test_invalid_check_file_exits_1_and_writes_nothing(work, capsys, tmp_path, items, reason):
    code_commit(work)
    f = tmp_path / "checks.json"
    f.write_text(items if isinstance(items, str) else json.dumps(items), encoding="utf-8")
    code, out = write(work, capsys, "--check-file", str(f))
    assert code == 1 and reason in out
    assert not (work / "receipts").exists()


def test_check_file_items_are_appended(work, capsys, tmp_path):
    code_commit(work)
    item = {"name": "review round one", "command": "codex exec", "status": "PASS", "exit_code": 0}
    f = tmp_path / "checks.json"
    f.write_text(json.dumps([item]), encoding="utf-8")
    assert write(work, capsys, "--check-file", str(f))[0] == 0
    assert written(work)["checks"][-1] == item


def test_failing_registered_check_is_recorded_and_the_receipt_is_still_written(work, capsys, monkeypatch):
    monkeypatch.setattr(registry, "CHECKS", [ok("tests"), fails("path-scope"), fails("receipt")])
    code_commit(work)
    assert write(work, capsys)[0] == 0
    failed = written(work)["checks"][1]
    assert (failed["name"], failed["status"], failed["exit_code"], failed["reason"]) == (
        "path-scope", "FAIL", 1, "exit 1: last words")


@pytest.mark.parametrize("change", ["modified", "staged", "untracked", "other receipt"])
def test_uncommitted_change_exits_1_and_writes_nothing(work, capsys, change):
    code_commit(work)
    if change == "modified":
        (work / "src" / "keep.py").write_text("changed\n", encoding="utf-8")
    elif change == "staged":
        (work / "src" / "b.py").write_text("b\n", encoding="utf-8")
        git(work, "add", "src/b.py")
    elif change == "untracked":
        (work / "src" / "b.py").write_text("b\n", encoding="utf-8")
    else:
        (work / "receipts").mkdir()
        (work / "receipts" / "U8.json").write_text("{}\n", encoding="utf-8")
    code, out = write(work, capsys)
    assert code == 1 and out.startswith("FAIL: uncommitted changes; a receipt must describe a commit")
    assert not (work / "receipts" / "U9.json").exists()


def test_receipt_written_then_code_committed_then_receipt_committed_fails_the_receipt_check(work, capsys):
    code_commit(work)
    assert write(work, capsys)[0] == 0
    (work / "src" / "b.py").write_text("b\n", encoding="utf-8")
    git(work, "add", "src/b.py")
    git(work, "commit", "-q", "-m", "late code")
    git(work, "add", "receipts/U9.json")
    git(work, "commit", "-q", "-m", "receipt")
    code, out = check(receipt, work, capsys)
    assert code == 1 and "is not the receipt commit's parent" in out


def test_skip_tests_is_not_run_and_is_listed_as_not_measured(work, capsys):
    code_commit(work)
    assert write(work, capsys, "--skip-check", "tests", "--skip-check", "receipt")[0] == 0
    data = written(work)
    assert [c["name"] for c in data["checks"]] == ["path-scope"]
    assert data["not_measured"] == [{"claim": f"{n} check, skipped by the writer", "command": "tlb check run"}
                                    for n in ("receipt", "tests")]


def test_recorded_commands_name_python_not_the_local_interpreter_path(work, capsys):
    code_commit(work)
    assert write(work, capsys)[0] == 0
    commands = [c["command"] for c in written(work)["checks"]]
    assert commands and all(c.startswith("python -c ") for c in commands)
    assert not any(sys.executable in c or str(Path(sys.executable).parent) in c for c in commands)


def test_only_the_interpreter_in_first_position_is_renamed(work, capsys, monkeypatch):
    from tiller_book.checks import Check
    echo = Check("tests", (sys.executable, "-c", "import sys; print(sys.argv[1])", sys.executable))
    monkeypatch.setattr(registry, "CHECKS", [echo, ok("path-scope"), fails("receipt")])
    code_commit(work)
    assert write(work, capsys)[0] == 0
    recorded = written(work)["checks"][0]["command"]
    assert recorded == shlex.join(["python", "-c", "import sys; print(sys.argv[1])", sys.executable])


def test_skip_tests_alone_still_skips_the_receipt_check(work, capsys):
    code_commit(work)
    assert write(work, capsys, "--skip-check", "tests")[0] == 0
    data = written(work)
    assert [c["name"] for c in data["checks"]] == ["path-scope"]
    assert {m["claim"] for m in data["not_measured"]} == {"tests check, skipped by the writer",
                                                          "receipt check, skipped by the writer"}


@pytest.mark.parametrize("existing", [None, "old receipt\n"])
def test_failed_write_leaves_no_partial_receipt(work, capsys, monkeypatch, existing):
    code_commit(work)
    target = work / "receipts" / "U9.json"
    if existing is not None:
        target.parent.mkdir(exist_ok=True)
        target.write_text(existing, encoding="utf-8", newline="\n")

    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("tiller_book.receipt.write.os.replace", fail)
    code, out = write(work, capsys)
    assert code == 1
    if existing is None:
        assert not target.exists()
    else:
        assert target.read_text(encoding="utf-8") == existing
    assert [p.name for p in target.parent.iterdir() if p.name != "U9.json"] == []


def test_skip_check_names_outside_receipt_and_tests_are_rejected(work, capsys):
    with pytest.raises(SystemExit):
        write(work, capsys, "--skip-check", "path-scope")


@pytest.mark.parametrize("unit", ["../x", ".U9", "U 9", ""])
def test_invalid_unit_id_exits_1_and_writes_nothing(work, capsys, unit):
    code_commit(work)
    code, out = write(work, capsys, unit=unit)
    assert (code, out) == (1, f"FAIL: invalid unit id {unit!r}")
    assert not (work / "receipts").exists()


def test_without_origin_main_fails_with_reason_and_no_traceback(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    p = subprocess.run([sys.executable, "-m", "tiller_book.cli", "receipt", "write", "U9", "--skip-check", "tests"],
                       cwd=tmp_path, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert p.returncode == 1 and p.stdout.startswith("FAIL: could not run: git merge-base failed")
    assert len(p.stdout.splitlines()) == 1 and "Traceback" not in p.stderr
    assert not (tmp_path / "receipts").exists()
