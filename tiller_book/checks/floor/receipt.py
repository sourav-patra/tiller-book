"""Receipt: the head commit adds receipts/<id>.json and nothing else, and the receipt names that commit's parent.

The receipt names the parent rather than the head itself, which would be circular. A code commit after the
receipt, or a receipt copied from an older run, therefore fails. This proves the receipt's shape and its
binding to the head; it cannot prove the listed checks ran, which only CI's own tlb check run shows.
"""

import json
import sys

from jsonschema import Draft202012Validator

from tiller_book.checks.floor import BASE, gate, git, names, run
from tiller_book.plan.verify import SCHEMAS, verify_plan


def _reject_constant(name):
    raise ValueError(f"non-standard JSON constant {name}")


def receipt_problem(repo, unit, base):
    """Return the first receipt rule the head breaks, or None."""
    path = f"receipts/{unit}.json"
    head, *parents = git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) != 1:
        return f"head commit {head[:12]} has {len(parents)} parents; the receipt commit must have exactly one"
    parent = parents[0]
    touched = names(repo, parent, head)
    if path not in touched:
        return f"no receipt: head commit {head[:12]} does not change {path}"
    if touched != [path]:
        return f"receipt commit {head[:12]} also changes: {', '.join(p for p in touched if p != path)}"
    try:
        data = json.loads(git(repo, "show", f"{head}:{path}"), parse_constant=_reject_constant)
    except ValueError as e:
        return f"{path} is not valid JSON: {e}"
    schema = json.loads((SCHEMAS / "receipt.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: e.json_path)
    if errors:
        return f"{path}: {errors[0].json_path}: {errors[0].message}"
    if data["unit"] != unit:
        return f"{path}: unit {data['unit']!r} is not {unit!r}"
    if data["commits"]["head"] != parent:
        return f"{path}: commits.head {data['commits']['head'][:12]} is not the receipt commit's parent {parent[:12]}"
    if data["commits"]["start"] != base:
        return f"{path}: commits.start {data['commits']['start'][:12]} is not the merge base {base[:12]} with {BASE}"
    return None


def check(repo):
    base, _, unit, verdict = gate(repo)
    if verdict:
        return verdict
    # The plan problems and the receipt problem are independent; report both so neither hides the other.
    problems = verify_plan(repo, unit, BASE, BASE)
    receipt = receipt_problem(repo, unit, base)
    problems += [receipt] if receipt else []
    if problems:
        return False, "; ".join(problems)
    return True, f"receipts/{unit}.json is valid and names the head commit's parent"


if __name__ == "__main__":
    sys.exit(run(check))
