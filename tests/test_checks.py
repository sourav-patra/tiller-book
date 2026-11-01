"""tlb check run: each check is PASS, FAIL or NOT_RUN, and the aggregate fails closed."""

import io
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from tiller_book import cli
from tiller_book.checks import Check, aggregate, registry, run_check

PY = sys.executable
SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "receipt.schema.json").read_text(encoding="utf-8"))
CHECKS_SCHEMA = Draft202012Validator(SCHEMA["properties"]["checks"])


def ok(name="ok", required=True):
    return Check(name, (PY, "-c", "print('fine')"), required=required)


def fails(name="bad", required=True):
    return Check(name, (PY, "-c", "import sys; print('first'); print('last words'); sys.exit(1)"), required=required)


def missing_tool(name="needs-tool"):
    return Check(name, (PY, "-c", "pass"), tools=("tlb-no-such-tool-xyz",))


def run(checks, monkeypatch, capsys, *args):
    monkeypatch.setattr(registry, "CHECKS", checks)
    code = cli.main(["check", "run", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_pass():
    r = run_check(ok())
    assert (r["status"], r["exit_code"], r["reason"]) == ("PASS", 0, "exit 0")


def test_fail_names_exit_code_and_last_line():
    r = run_check(fails())
    assert (r["status"], r["exit_code"]) == ("FAIL", 1)
    assert r["reason"] == "exit 1: last words"


def test_fail_with_no_output():
    r = run_check(Check("quiet", (PY, "-c", "raise SystemExit(2)")))
    assert r["reason"] == "exit 2: no output"


def test_missing_tool_is_not_run():
    r = run_check(missing_tool())
    assert (r["status"], r["exit_code"]) == ("NOT_RUN", None)
    assert "tlb-no-such-tool-xyz" in r["reason"]


def test_timeout_is_not_run():
    r = run_check(Check("slow", (PY, "-c", "import time; time.sleep(30)"), timeout=0.5))
    assert (r["status"], r["exit_code"]) == ("NOT_RUN", None)
    assert "timed out after 0.5 s" in r["reason"]


def test_command_that_cannot_start_is_not_run():
    r = run_check(Check("ghost", ("tlb-no-such-binary-xyz",)))
    assert (r["status"], r["exit_code"]) == ("NOT_RUN", None)
    assert r["reason"].startswith("could not start:")


def test_all_required_pass_exits_0(monkeypatch, capsys):
    code, out, _ = run([ok("a"), ok("b")], monkeypatch, capsys)
    assert code == 0
    assert "PASS a: exit 0" in out and "PASS: all 2 required checks passed" in out


def test_one_required_fail_exits_1(monkeypatch, capsys):
    code, out, _ = run([ok("a"), fails("b")], monkeypatch, capsys)
    assert code == 1
    assert "FAIL b: exit 1: last words" in out
    assert "FAIL: required checks not PASS: b" in out


def test_missing_tool_fails_aggregate_with_reason_printed(monkeypatch, capsys):
    code, out, _ = run([ok("a"), missing_tool("t")], monkeypatch, capsys)
    assert code == 1
    assert "NOT_RUN t: tool not on PATH: tlb-no-such-tool-xyz" in out
    assert "FAIL: required checks not PASS: t" in out


def test_timeout_fails_aggregate(monkeypatch, capsys):
    slow = Check("slow", (PY, "-c", "import time; time.sleep(30)"), timeout=0.5)
    code, out, _ = run([ok("a"), slow], monkeypatch, capsys)
    assert code == 1
    assert "NOT_RUN slow: timed out" in out


def test_optional_fail_does_not_decide(monkeypatch, capsys):
    code, out, _ = run([ok("a"), fails("opt", required=False)], monkeypatch, capsys)
    assert code == 0
    assert "FAIL opt (optional): exit 1: last words" in out


def test_no_required_checks_exits_1(monkeypatch, capsys):
    code, out, _ = run([ok("opt", required=False)], monkeypatch, capsys)
    assert code == 1
    assert "FAIL: no required checks" in out


def test_empty_registry_exits_1():
    assert aggregate([], [])[0] == 1


def test_json_items_validate_as_receipt_checks(monkeypatch, capsys):
    checks = [ok("a"), fails("b"), missing_tool("c"), Check("ghost", ("tlb-no-such-binary-xyz",))]
    code, out, err = run(checks, monkeypatch, capsys, "--json")
    items = json.loads(out)
    assert code == 1 and "FAIL: required checks not PASS: b, c, ghost" in err
    assert [i["status"] for i in items] == ["PASS", "FAIL", "NOT_RUN", "NOT_RUN"]
    assert items[0]["reason"] == "exit 0"
    assert list(CHECKS_SCHEMA.iter_errors(items)) == []


def test_every_result_kind_validates_including_malformed_commands():
    checks = [ok(), fails(), missing_tool(), Check("slow", (PY, "-c", "import time; time.sleep(30)"), timeout=0.5),
              Check("ghost", ("tlb-no-such-binary-xyz",)), Check("empty", ()), Check("nul", (PY, "-c", "pass\0"))]
    results = [run_check(c) for c in checks]
    assert [r["status"] for r in results] == ["PASS", "FAIL", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN"]
    assert list(CHECKS_SCHEMA.iter_errors(results)) == []


def test_malformed_command_fails_aggregate_without_traceback(monkeypatch, capsys):
    code, out, err = run([ok("a"), Check("nul", (PY, "-c", "pass\0"))], monkeypatch, capsys, "--json")
    assert code == 1 and "FAIL: required checks not PASS: nul" in err


def test_missing_or_mismatched_results_fail():
    a, b = ok("a"), ok("b")
    passed = {"name": "a", "command": "x", "status": "PASS", "exit_code": 0, "reason": "exit 0"}
    assert aggregate([a, b], [passed])[0] == 1
    assert aggregate([b], [passed]) == (1, "FAIL: results do not match the registered checks")


def test_unencodable_output_prints_on_a_cp1252_console(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    monkeypatch.setattr(registry, "CHECKS", [Check("bytes", (PY, "-c", "import sys; sys.stdout.buffer.write(b'bad \\xff'); sys.exit(1)"))])
    code = cli.main(["check", "run"])
    sys.stdout.flush()
    out = raw.getvalue().decode("cp1252")
    assert code == 1
    assert "FAIL bytes: exit 1: bad" in out and "FAIL: required checks not PASS: bytes" in out


def test_registry_holds_tests_leak_scan_and_floor_checks_all_required():
    assert [(c.name, c.required) for c in registry.CHECKS] == [
        ("tests", True), ("leak-scan", True), ("path-scope", True), ("receipt", True)]
    assert dict((c.name, c.command) for c in registry.CHECKS)["receipt"] == (PY, "-m", "tiller_book.checks.floor.receipt")
    assert dict((c.name, c.tools) for c in registry.CHECKS)["leak-scan"] == ("gitleaks",)
