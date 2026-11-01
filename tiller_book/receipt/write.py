"""Write receipts/<unit>.json for the head commit, so that committing it alone passes the receipt check.

commits.head is HEAD now; once the receipt is committed, HEAD is the receipt commit's parent, which is the
binding the receipt check reads. Token counts and cost come from the caller: the writer cannot see a model session.
"""

import json
import math
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

from tiller_book.checks import registry, run_check
from tiller_book.checks.floor import BASE, git
from tiller_book.checks.floor.receipt import _reject_constant
from tiller_book.plan.verify import PLAN_ID, SCHEMAS

TOKENS = re.compile(r"[0-9]+")
COST_COMMAND = "report the cost from the model session"


class Refused(Exception):
    """An input or repository state the writer will not describe; nothing is written."""


def parse_model_call(text):
    fields = text.split(",")
    if len(fields) != 4:
        raise Refused(f"--model-call {text!r}: expected MODEL,INPUT_TOKENS,OUTPUT_TOKENS,COST_USD")
    model, tokens_in, tokens_out, cost = fields
    if not (TOKENS.fullmatch(tokens_in) and TOKENS.fullmatch(tokens_out)):
        raise Refused(f"--model-call {text!r}: token counts must be whole numbers")
    if cost == "-":
        cost_usd = None
    else:
        try:
            cost_usd = float(cost)
        except ValueError:
            raise Refused(f"--model-call {text!r}: cost must be a number or -") from None
        if not math.isfinite(cost_usd) or cost_usd < 0:
            raise Refused(f"--model-call {text!r}: cost must be a finite number of at least 0, or -")
    return {"model": model, "input_tokens": int(tokens_in), "output_tokens": int(tokens_out), "cost_usd": cost_usd}


def split_pair(text, option, left, right):
    a, sep, b = text.partition("=")  # first '=' only: commands often hold one
    if not sep:
        raise Refused(f"{option} {text!r}: expected {left}={right}")
    return a, b


def read_check_file(path):
    try:
        items = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except ValueError as e:
        raise Refused(f"--check-file {path}: not valid JSON: {e}") from None
    if not isinstance(items, list):
        raise Refused(f"--check-file {path}: expected a JSON list of checks[] items")
    return items


def portable(result):
    """Name the interpreter `python` in a recorded command, so a receipt never carries a local path."""
    command = result["command"]
    for form in (shlex.quote(sys.executable), sys.executable):
        command = command.replace(form, "python")
    return {**result, "command": command}


def dirty(repo, unit):
    """Paths git status reports, other than an untracked receipts/<unit>.json."""
    entries = git(repo, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    return [e for e in entries if e and e != f"?? receipts/{unit}.json"]


def build(repo, unit, agent="unknown", model=None, model_calls=(), check_file=None, evidence=(),
          not_measured=(), skip=("receipt",)):
    """Return the receipt for HEAD; raise Refused for a bad unit id, a dirty tree or a malformed input."""
    if not PLAN_ID.match(unit):
        raise Refused(f"invalid unit id {unit!r}")
    changes = dirty(repo, unit)
    if changes:
        raise Refused(f"uncommitted changes; a receipt must describe a commit: {changes[0][3:]}")
    calls = [parse_model_call(c) for c in model_calls]
    extra = read_check_file(check_file) if check_file else []
    runner = {"agent": agent, **({"model": model} if model is not None else {})}
    gaps = [dict(zip(("claim", "command"), split_pair(n, "--not-measured", "CLAIM", "COMMAND"))) for n in not_measured]
    data = {
        "schema_version": "0.1",
        "unit": unit,
        "runner": runner,
        "commits": {"start": git(repo, "merge-base", BASE, "HEAD").strip(), "head": git(repo, "rev-parse", "HEAD").strip()},
        "model_calls": calls,
        "checks": [portable(run_check(c, repo)) for c in registry.CHECKS if c.name not in skip] + extra,
        "refusals": [],
        "evidence": [dict(zip(("location", "what"), split_pair(e, "--evidence", "LOCATION", "WHAT"))) for e in evidence],
        "not_measured": gaps + [{"claim": f"{name} check, skipped by the writer", "command": "tlb check run"}
                                for name in dict.fromkeys(skip)],
    }
    claims = {g["claim"] for g in data["not_measured"]}
    for call in calls:
        claim = f"cost of {call['model']} call"
        if call["cost_usd"] is None and claim not in claims:
            claims.add(claim)
            data["not_measured"].append({"claim": claim, "command": COST_COMMAND})
    return data


def first_error(data):
    schema = json.loads((SCHEMAS / "receipt.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: e.json_path)
    return f"{errors[0].json_path}: {errors[0].message}" if errors else None


def write(repo, unit, **options):
    """Return (exit code, message line). Nothing is written unless the whole receipt validates."""
    try:
        data = build(repo, unit, **options)
    except Refused as e:
        return 1, f"FAIL: {e}"
    error = first_error(data)
    if error:
        return 1, f"FAIL: receipt not written: {error}"
    path = Path(repo) / "receipts" / f"{unit}.json"
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(exist_ok=True)
    # write beside the target, then rename, so a failed write never leaves a partial receipt
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{unit}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return 0, f"PASS: wrote receipts/{unit}.json; commit it alone as the last commit"
