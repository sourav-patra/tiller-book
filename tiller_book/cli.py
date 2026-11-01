"""tlb: the tiller-book command line."""

import argparse
import json
import sys
from pathlib import Path

from tiller_book.checks import aggregate, line, registry, run_check
from tiller_book.plan.verify import CouldNotRun, verify_plan
from tiller_book.release import gate


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
    release = sub.add_parser("release", help="release").add_subparsers(dest="release_command", required=True)
    gate_cmd = release.add_parser("gate", help="exit 0 only if every release step passes on origin/main")
    gate_cmd.add_argument("--denylist", required=True,
                          help="file of grep patterns, one per line, kept outside the repository")
    gate_cmd.add_argument("--repo", default=".", help="repository path (default the current directory)")
    args = parser.parse_args(argv)

    if args.command == "release":
        return release_gate(Path(args.repo), args.denylist)
    if args.command == "check":
        return check_run(Path(args.repo), args.json)
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


def release_gate(repo, denylist):
    if hasattr(sys.stdout, "reconfigure"):  # tool output may hold characters the console code page cannot encode
        sys.stdout.reconfigure(errors="backslashreplace")
    results = gate(repo, denylist)
    for name, ok, reason in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}: {reason}")
    bad = [name for name, ok, _ in results if not ok]
    print(f"FAIL: release steps not PASS: {', '.join(bad)}" if bad else f"PASS: all {len(results)} release steps passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
