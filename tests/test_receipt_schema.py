"""The receipt schema accepts the three examples and rejects receipts that drop required evidence."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/receipt.schema.json").read_text(encoding="utf-8"))
EXAMPLES = sorted((ROOT / "tests/fixtures/receipts").glob("*.json"))
VALIDATOR = Draft202012Validator(SCHEMA)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def errors(receipt):
    return [e.message for e in VALIDATOR.iter_errors(receipt)]


def test_schema_is_valid_2020_12():
    Draft202012Validator.check_schema(SCHEMA)


def test_three_examples_exist():
    assert len(EXAMPLES) == 3


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_examples_validate(path):
    assert errors(load(path)) == []


def test_unit_receipts_validate():
    for path in sorted((ROOT / "receipts").glob("*.json")):
        assert errors(load(path)) == [], path.name


def broken(change):
    receipt = copy.deepcopy(load(ROOT / "tests/fixtures/receipts/not-run-and-refusal.json"))
    change(receipt)
    return receipt


@pytest.mark.parametrize("name, change", [
    ("missing head commit", lambda r: r["commits"].pop("head")),
    ("short head commit", lambda r: r["commits"].update(head="2222222")),
    ("missing check exit code", lambda r: r["checks"][0].pop("exit_code")),
    ("null exit code on a PASS", lambda r: r["checks"][0].update(exit_code=None)),
    ("FAIL without reason", lambda r: r["checks"][2].pop("reason")),
    ("NOT_RUN without reason", lambda r: r["checks"][1].pop("reason")),
    ("unknown top-level field", lambda r: r.update(verdict="trust me")),
    ("missing not_measured list", lambda r: r.pop("not_measured")),
    ("negative tokens", lambda r: r["model_calls"].append(
        {"model": "m", "input_tokens": -1, "output_tokens": 0, "cost_usd": 0})),
    ("unknown status", lambda r: r["checks"][0].update(status="SKIPPED")),
])
def test_broken_receipts_fail(name, change):
    assert errors(broken(change)), name
