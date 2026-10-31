"""Start a disposable server and run both browser suites."""

import os
import subprocess
import sys
import time
from pathlib import Path
import httpx

if __name__ == "__main__":
    Path("work").mkdir(exist_ok=True)
    port = "8799"
    env = {**os.environ, "TRACEGARDEN_URL": f"http://127.0.0.1:{port}"}
    with open("work/browser-server.log", "w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "tracegarden", "--no-browser", "--port", port],
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                try:
                    if httpx.get(env["TRACEGARDEN_URL"], timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Browser test server did not start")
            for script in [
                "tests/browser_check.py",
                "tests/studio_browser_check.py",
                "tests/parity_browser_check.py",
            ]:
                subprocess.run([sys.executable, script], env=env, check=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
