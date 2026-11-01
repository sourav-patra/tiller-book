"""tlb: the tiller-book command line."""

import argparse
import json
import sys
from pathlib import Path

from tiller_book.checks import aggregate, line, registry, run_check
from tiller_book.plan.verify import CouldNotRun, verify_plan
from tiller_book.receipt import write as receipt


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tlb")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="plan files").add_subparsers(dest="plan_command", required=True)
    verify = plan.add_parser("verify", help="exit 0 only if plans/<id>.toml on the ref is valid and owner-signed")
    verify.add_argument("id")
    verify.add_argument("--ref", default="origin/main", help="where the plan is read (default origin/main)")
    verify.add_argument("--signers-ref", default="origin/main",
                        help="where .github/allowed_signers is read (default origin/main)")
    verify.add_argument("--repo", default=".", help="repository path (default the current directory)")
    check = sub.add_parser("check", help="checks").add_subparsers(dest="check_command", required=True)
    run = check.add_parser("run", help="run every registered check; exit 0 only if every required check is PASS")
    run.add_argument("--json", action="store_true", help="print the results as receipt checks[] items")
    run.add_argument("--repo", default=".", help="directory the checks run in (default the current directory)")
    receipts = sub.add_parser("receipt", help="receipts").add_subparsers(dest="receipt_command", required=True)
    rw = receipts.add_parser("write", help="write receipts/<unit>.json for HEAD; commit it alone as the last commit")
    rw.add_argument("unit")
    rw.add_argument("--repo", default=".", help="repository path (default the current directory)")
    rw.add_argument("--agent", default="unknown", help="the agent that did the work (default unknown)")
    rw.add_argument("--model", help="the agent's model")
    rw.add_argument("--model-call", action="append", default=[], metavar="MODEL,IN,OUT,COST",
                    help="one model call, as reported by the caller; a COST of - means not measured; repeatable")
    rw.add_argument("--check-file", metavar="FILE", help="a JSON list of extra receipt checks[] items")
    rw.add_argument("--evidence", action="append", default=[], metavar="LOCATION=WHAT", help="repeatable")
    rw.add_argument("--not-measured", action="append", default=[], metavar="CLAIM=COMMAND", help="repeatable")
    rw.add_argument("--skip-check", action="append", choices=("receipt", "tests"), metavar="NAME",
                    help="a registered check not to run: receipt or tests; repeatable (default receipt)")
    args = parser.parse_args(argv)

    if args.command == "check":
        return check_run(Path(args.repo), args.json)
    if args.command == "receipt":
        return receipt_write(args)
    try:
        problems = verify_plan(Path(args.repo), args.id, args.ref, args.signers_ref)
    except (CouldNotRun, OSError) as e:
        problems = [f"could not run: {e}"]
    for p in problems:
        print(f"FAIL: {p}")
    if not problems:
        print(f"PASS: plans/{args.id}.toml at {args.ref} is valid and signed by a key in "
              f".github/allowed_signers at {args.signers_ref}")
    return 1 if problems else 0


def check_run(repo, as_json):
    results = [run_check(c, repo) for c in registry.CHECKS]
    code, verdict = aggregate(registry.CHECKS, results)
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        if hasattr(sys.stdout, "reconfigure"):  # check output may hold characters the console code page cannot encode
            sys.stdout.reconfigure(errors="backslashreplace")
        for c, r in zip(registry.CHECKS, results):
            print(line(c, r))
    print(verdict, file=sys.stderr if as_json else sys.stdout)
    return code


def receipt_write(args):
    if hasattr(sys.stdout, "reconfigure"):  # check reasons may hold characters the console code page cannot encode
        sys.stdout.reconfigure(errors="backslashreplace")
    try:
        code, message = receipt.write(
            Path(args.repo), args.unit, agent=args.agent, model=args.model, model_calls=args.model_call,
            check_file=args.check_file, evidence=args.evidence, not_measured=args.not_measured,
            skip=args.skip_check or ["receipt"])
    except Exception as e:  # noqa: BLE001 - fail closed on anything, never a traceback
        code, message = 1, f"FAIL: could not run: {e}"
    print(" ".join(str(message).splitlines()))
    return code


if __name__ == "__main__":
    sys.exit(main())
