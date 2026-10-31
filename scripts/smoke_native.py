"""Verify a packaged desktop executable without a development Python path."""

import io
import json
import subprocess
import sys
import time
from pathlib import Path
import httpx
from PIL import Image, ImageDraw

if __name__ == "__main__":
    executable = str(Path(sys.argv[1]).resolve())
    port = "8798"
    process = subprocess.Popen([executable, "--no-browser", "--port", port])
    client = httpx.Client(base_url="http://127.0.0.1:" + port, timeout=60)
    try:
        for _ in range(200):
            try:
                if client.get("/").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise RuntimeError("Packaged app exited during startup")
            time.sleep(0.1)
        else:
            raise RuntimeError("Packaged app did not start")
        im = Image.new("RGB", (128, 128), "white")
        ImageDraw.Draw(im).rectangle((20, 20, 100, 100), fill="red")
        buffer = io.BytesIO()
        im.save(buffer, format="PNG")
        for options in [
            {"layering": "smooth", "geometry": True},
            {"preset": "centerline"},
        ]:
            r = client.post(
                "/api/jobs",
                files={"file": ("test.png", buffer.getvalue())},
                data={"options": json.dumps(options)},
            )
            assert r.status_code == 202, r.text
            ident = r.json()["id"]
            for _ in range(300):
                job = client.get("/api/jobs/" + ident).json()
                if job["state"] in {"complete", "failed"}:
                    break
                time.sleep(0.1)
            assert job["state"] == "complete", job
            for fmt in [
                "svg",
                "pdf",
                "eps",
                "ai",
                "dxf",
                "png",
                "jpg",
                "gif",
                "bmp",
                "tiff",
            ]:
                r = client.post(
                    "/api/export", json={"svg": job["result"]["svg"], "format": fmt}
                )
                assert r.status_code == 200, (fmt, r.text)
                assert len(r.content) > 30
            client.delete("/api/jobs/" + ident)
        assert client.post("/api/shutdown").status_code == 200
        process.wait(timeout=15)
        assert process.returncode == 0
        print(
            "Native package passed startup, isolated CPU jobs, all exports and graceful shutdown."
        )
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
