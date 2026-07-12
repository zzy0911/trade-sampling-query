from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the packaged Windows application")
    parser.add_argument("executable", type=Path)
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()

    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"Executable not found: {executable}")

    with tempfile.TemporaryDirectory(prefix="trade-query-smoke-") as data_dir:
        env = os.environ.copy()
        env.update({"DATA_DIR": data_dir, "SERVER_PORT": str(args.port), "OPEN_BROWSER": "0"})
        process = subprocess.Popen([str(executable)], env=env)
        try:
            url = f"http://127.0.0.1:{args.port}/api/options"
            for _ in range(40):
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200 and response.read():
                            print(f"Packaged application smoke test passed: {url}")
                            return
                except OSError:
                    time.sleep(0.25)
            raise SystemExit("Packaged application did not become ready in time")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
