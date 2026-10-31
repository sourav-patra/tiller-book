"""The checks tlb check run executes. Kept in code so CI reads them from main with the rest of the tool."""

import sys

from tiller_book.checks import Check

CHECKS = [
    Check("tests", (sys.executable, "-m", "pytest", "-q")),
    Check("leak-scan", ("gitleaks", "git", "."), tools=("gitleaks",), timeout=300),
]
