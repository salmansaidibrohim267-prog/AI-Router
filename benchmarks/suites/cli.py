"""CLI entry point for benchmark suites.

Usage:
    python -m benchmarks.suites --target-name default --suites throughput,latency
"""

from __future__ import annotations

import argparse
import json
import time

from .runner import SUITE_BUILDERS, SuiteRunner


def _noop_target() -> None:
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run benchmark suites")
    parser.add_argument("--target-name", default="default", help="name for the benchmark report")
    parser.add_argument("--suites", default=",".join(SUITE_BUILDERS), help="comma separated suite names")
    parser.add_argument("--iterations", type=int, default=200, help="iterations for latency suite")
    parser.add_argument("--json", action="store_true", help="emit report as JSON")
    args = parser.parse_args(argv)

    names = [name.strip() for name in args.suites.split(",") if name.strip()]
    runner = SuiteRunner(target=_noop_target, target_name=args.target_name)
    for name in names:
        if name == "latency":
            runner.register("latency", __import__("benchmarks.suites.suites", fromlist=["LatencySuite"]).LatencySuite(iterations=args.iterations))
    report = runner.run(names)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Benchmark report for {report.target_name} ({time.ctime(report.timestamp)})")
        for result in report.results:
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.name}: {result.metrics}")
        print(f"Overall: {'PASS' if report.overall_passed() else 'FAIL'}")
    return 0 if report.overall_passed() else 1


if __name__ == "__main__":
    raise SystemExit(main())
