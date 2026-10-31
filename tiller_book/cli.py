"""tlb: the tiller-book command line."""

import argparse
import sys
from pathlib import Path

from tiller_book.plan.verify import CouldNotRun, verify_plan


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
    args = parser.parse_args(argv)

    try:
        problems = verify_plan(Path(args.repo), args.id, args.ref, args.signers_ref)
    except CouldNotRun as e:
        problems = [f"could not run: {e}"]
    for p in problems:
        print(f"FAIL: {p}")
    if not problems:
        print(f"PASS: plans/{args.id}.toml at {args.ref} is valid and signed by a key in "
              f".github/allowed_signers at {args.signers_ref}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
