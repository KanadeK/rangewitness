"""Command-line entry point."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, audit


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check a stable asset's HTTP byte-serving contract"
    )
    parser.add_argument("url", help="direct HTTP(S) asset URL; redirects are not followed")
    parser.add_argument(
        "--reference", type=Path, help="optional local copy for actual byte comparison"
    )
    parser.add_argument("--sample-bytes", type=int, default=64, help="1..4096; default 64")
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="socket timeout, 0 < seconds <= 60"
    )
    parser.add_argument("--json", action="store_true", help="print value-minimized JSON")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.url, reference=args.reference, sample_bytes=args.sample_bytes, timeout=args.timeout
        )
    except (InputError, OSError) as exc:
        message = str(exc) if isinstance(exc, InputError) else "Cannot read local reference file"
        print("Input error: " + message, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for check in report["checks"]:
            detail = ", ".join(check.get("errors", [])) or check.get("reason", "ok")
            print(f"{check['status'].upper():7} {check['name']}: {detail}")
        mode = (
            "reference bytes" if report["reference_checked"] else "headers and sample consistency"
        )
        print(f"{report['status'].upper()} — {report['requests']} requests; checked {mode}")
    return 0 if report["status"] == "passed" else 1
