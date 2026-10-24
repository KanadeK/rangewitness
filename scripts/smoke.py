"""Exercise an installed wheel through the CLI against a real loopback server."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
from fixture_server import PAYLOAD, running_server  # noqa: E402


def main(python):
    console = Path(python).with_name(
        "rangewitness.exe" if sys.platform == "win32" else "rangewitness"
    )
    version = subprocess.run(
        [str(console), "--version"], capture_output=True, text=True, check=True
    )
    if version.stdout.strip() != "0.1.0":
        raise RuntimeError("Installed console entry point has the wrong version")
    with tempfile.TemporaryDirectory(prefix="range-demo-") as folder, running_server() as base:
        reference = Path(folder) / "canary.bin"
        reference.write_bytes(PAYLOAD)
        for route, code in (("ok", 0), ("corrupt", 1), ("ignored", 1)):
            result = subprocess.run(
                [
                    python,
                    "-m",
                    "rangewitness",
                    base + "/" + route,
                    "--reference",
                    str(reference),
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if result.returncode != code:
                raise RuntimeError(f"Unexpected {route} exit: {result.returncode}; {result.stderr}")
            report = json.loads(result.stdout)
            if report["reference_checked"] is not True or report["bytes_read"] > 5 * 65:
                raise RuntimeError("Reference or body-bound contract was not honored")
            print(f"{route}: exit {code}, {report['status']}, {report['requests']} real GETs")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.executable)
