"""
Run the offline test suite and record the outcome for the dashboard.

    ./venv/bin/python scripts/record_test_run.py

Writes data/test_run_metadata.json: start/finish time (UTC), Python version,
git HEAD, and totals plus per-module counts (tests, failures, errors, skips).
The dashboard only READS this file; it never runs tests. NCBI_API_KEY is
removed from this process's environment first (the shell exports a
placeholder that some tests deliberately reject).
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = "data/test_run_metadata.json"


class _Recorder(unittest.TextTestResult):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.modules = {}

    def _mod(self, test, key):
        name = test.id().split(".")[0]
        m = self.modules.setdefault(name, {"tests": 0, "failures": 0, "errors": 0, "skipped": 0})
        m[key] += 1

    def startTest(self, test):
        super().startTest(test)
        self._mod(test, "tests")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._mod(test, "failures")

    def addError(self, test, err):
        super().addError(test, err)
        self._mod(test, "errors")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._mod(test, "skipped")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run tests/ and record the outcome to data/test_run_metadata.json")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    os.environ.pop("NCBI_API_KEY", None)
    os.chdir(ROOT)
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    started = datetime.now(timezone.utc)
    suite = unittest.defaultTestLoader.discover("tests")
    with open(os.devnull, "w") as sink:
        result = unittest.TextTestRunner(stream=sink, resultclass=_Recorder, verbosity=0).run(suite)
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=ROOT).stdout.strip() or None
    except OSError:
        head = None
    meta = {"command": "./venv/bin/python scripts/record_test_run.py (unittest discover -s tests)",
            "started_utc": started.isoformat(timespec="seconds"),
            "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "python": platform.python_version(), "git_head": head,
            "working_tree_note": "uncommitted changes are not identified by git_head",
            "total": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped), "ok": result.wasSuccessful(),
            "modules": dict(sorted(result.modules.items())),
            "failed_tests": [t.id() for t, _ in result.failures + result.errors]}
    path = os.path.join(ROOT, args.out)
    with open(path + ".tmp", "w") as fh:
        json.dump(meta, fh, indent=1)
    os.replace(path + ".tmp", path)
    print(f"Ran {meta['total']} tests: failures {meta['failures']}, errors {meta['errors']}, "
          f"skipped {meta['skipped']} -> {args.out}")
    return 0 if meta["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
