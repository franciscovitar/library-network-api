"""Fail unless a pytest JUnit report proves the real-PostgreSQL tests actually ran.

Independent second guard (the first is tests/conftest.py). Standard library only.

    python scripts/ci/check_test_report.py report.xml --min-integration 100

Exit status 0 only if: no failures/errors, NO skipped test at all, and at least
`--min-integration` integration test cases passed. The floor is a deliberate tripwire against
the suite silently shrinking; raise it when tests are added, lower it only on purpose.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - our own CI artifact, not untrusted input


def summarize(path: str) -> dict[str, int]:
    root = ET.parse(path).getroot()
    totals = {"total": 0, "failed": 0, "skipped": 0, "integration_passed": 0, "unit_passed": 0}
    for case in root.iter("testcase"):
        totals["total"] += 1
        failed = case.find("failure") is not None or case.find("error") is not None
        skipped = case.find("skipped") is not None
        totals["failed"] += failed
        totals["skipped"] += skipped
        if not failed and not skipped:
            is_integration = case.get("classname", "").startswith("tests.integration")
            totals["integration_passed" if is_integration else "unit_passed"] += 1
    return totals


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--min-integration", type=int, default=1)
    args = parser.parse_args(argv)

    t = summarize(args.report)
    print(
        f"total={t['total']} failed={t['failed']} skipped={t['skipped']} "
        f"integration_passed={t['integration_passed']} unit_passed={t['unit_passed']}"
    )
    problems = []
    if t["failed"]:
        problems.append(f"{t['failed']} failed/errored")
    if t["skipped"]:
        problems.append(f"{t['skipped']} skipped (integration tests must run, not skip)")
    if t["integration_passed"] < args.min_integration:
        problems.append(
            f"only {t['integration_passed']} integration tests passed; "
            f"expected at least {args.min_integration}"
        )
    if problems:
        print("TEST REPORT CHECK FAILED: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("test report check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
