"""Verify all formats against the packaged app on port 8742."""

import io
import time
import zipfile
import httpx
from PIL import Image, ImageDraw

client = httpx.Client(base_url="http://127.0.0.1:8742", timeout=60)
for _ in range(30):
    try:
        assert client.get("/").status_code == 200
        break
    except httpx.ConnectError:
        time.sleep(0.2)
else:
    raise RuntimeError("Portable app did not start")
im = Image.new("RGB", (128, 128), "white")
ImageDraw.Draw(im).ellipse((20, 20, 100, 100), fill="green")
buf = io.BytesIO()
im.save(buf, format="PNG")
r = client.post("/api/trace", files={"file": ("logo.png", buf.getvalue(), "image/png")})
assert r.status_code == 200, r.text
svg = r.json()["svg"]
for fmt in ["svg", "pdf", "eps", "dxf", "png"]:
    r = client.post("/api/export", json={"svg": svg, "format": fmt})
    assert r.status_code == 200, (fmt, r.text)
    assert len(r.content) > 100, (fmt, len(r.content))
    if fmt == "png":
        assert Image.open(io.BytesIO(r.content)).size == (128, 128)
    print(fmt, "OK", len(r.content))
r = client.post(
    "/api/export-batch",
    json={"items": [{"svg": svg, "format": "svg"}], "names": ["test"]},
)
assert (
    r.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 1
)
print(
    "Portable app: home, CPU trace, all five export formats, PNG dimensions and ZIP passed."
)
