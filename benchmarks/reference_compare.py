"""Evaluate publicly downloadable demo pairs; never train on vendor output.

--download-public-examples fetches only example URLs advertised in the public
homepage HTML. Cached artwork stays in gitignored work/. Reports include URLs,
hashes and measurements, never redistributed copies of third-party artwork.
"""

import argparse
import hashlib
import html
import io
import json
import platform
import re
import threading
import time
from importlib.metadata import version
from pathlib import Path
import httpx
import numpy as np
import resvg_py
import psutil
from PIL import Image
from tracegarden.core import trace, Options
from parity_corpus import metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-public-examples", action="store_true")
    parser.add_argument(
        "--one-cpu",
        action="store_true",
        help="Restrict this benchmark to one available logical CPU (Windows/Linux).",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/reference-results.json")
    )
    args = parser.parse_args()
    if args.one_cpu:
        process = psutil.Process()
        if not hasattr(process, "cpu_affinity"):
            raise SystemExit("CPU affinity is unavailable on this platform.")
        process.cpu_affinity([process.cpu_affinity()[0]])
    folder = Path("work/reference-examples")
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "manifest.json"
    if args.download_public_examples:
        response = httpx.get(
            "https://vectorizer.ai/", timeout=30, follow_redirects=True
        )
        response.raise_for_status()
        urls = sorted(
            set(
                re.findall(
                    r"/cf/vai/animations2/[a-z0-9_-]+\.(?:jpg|svg)",
                    html.unescape(response.text),
                )
            )
        )
        pairs = {}
        for url in urls:
            if "-thumbnail_" in url:
                continue
            stem = Path(url).name.split("_")[0]
            ext = url.rsplit(".", 1)[1]
            pairs.setdefault(stem, {})[ext] = "https://vectorizer.ai" + url
        entries = []
        for name, pair in pairs.items():
            if set(pair) != {"jpg", "svg"}:
                continue
            entry = {"case": name, "urls": pair, "sha256": {}}
            for ext, url in pair.items():
                response = httpx.get(url, timeout=30)
                response.raise_for_status()
                if len(response.content) > 10_000_000:
                    raise ValueError("Unexpectedly large public example.")
                (folder / f"{name}.{ext}").write_bytes(response.content)
                entry["sha256"][ext] = hashlib.sha256(response.content).hexdigest()
            entries.append(entry)
        manifest.write_text(json.dumps(entries, indent=2))
    if not manifest.exists():
        raise SystemExit(
            "No cache. Pass --download-public-examples to fetch the advertised public demo files."
        )
    rows = []
    for entry in json.loads(manifest.read_text()):
        name = entry["case"]
        data = (folder / f"{name}.jpg").read_bytes()
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        size = im.size
        reference = (folder / f"{name}.svg").read_text()
        vendor = (
            np.asarray(
                Image.open(
                    io.BytesIO(
                        resvg_py.svg_to_bytes(
                            svg_string=reference,
                            width=size[0],
                            height=size[1],
                            skip_system_fonts=True,
                        )
                    )
                ).convert("RGBA"),
                dtype=float,
            )
            / 255
        )
        source = np.asarray(im, dtype=float) / 255
        process = psutil.Process()
        baseline = process.memory_info().rss
        peak = [baseline]
        stop = threading.Event()

        def sample_memory():
            while not stop.wait(0.002):
                peak[0] = max(peak[0], process.memory_info().rss)

        monitor = threading.Thread(target=sample_memory, daemon=True)
        monitor.start()
        started = time.perf_counter()
        try:
            result = trace(
                data, Options(preset="auto", layering="auto", geometry=True, speckle=1)
            )
            elapsed = time.perf_counter() - started
        finally:
            peak[0] = max(peak[0], process.memory_info().rss)
            stop.set()
            monitor.join()
        actual = (
            np.asarray(
                Image.open(
                    io.BytesIO(
                        resvg_py.svg_to_bytes(
                            svg_string=result["svg"], skip_system_fonts=True
                        )
                    )
                ).convert("RGBA"),
                dtype=float,
            )
            / 255
        )
        if actual.shape != vendor.shape:
            raise ValueError("Comparison dimensions differ.")
        reference_error, boundary = metrics(vendor, actual)
        input_error, _ = metrics(source, actual)
        vendor_input, _ = metrics(source, vendor)
        row = {
            **entry,
            "size": list(size),
            "seconds": round(elapsed, 4),
            "process_peak_rss_mib": round(peak[0] / 1024**2, 2),
            "process_rss_growth_mib": round((peak[0] - baseline) / 1024**2, 2),
            "paths": result["paths"],
            "svg_bytes": len(result["svg"].encode()),
            "reference_svg_bytes": len(reference.encode()),
            "mae_vs_vendor": reference_error,
            "boundary_vs_vendor_px": boundary,
            "mae_vs_input": input_error,
            "vendor_mae_vs_input": vendor_input,
            "analysis": result["analysis"],
        }
        rows.append(row)
        print(row, flush=True)
        (folder / f"{name}-tracegarden.svg").write_text(result["svg"])
        args.output.write_text(
            json.dumps(
                {
                    "environment": {
                        "platform": platform.platform(),
                        "python": platform.python_version(),
                        "cpu": platform.processor(),
                        "vtracer": version("vtracer"),
                        "tracegarden": version("tracegarden"),
                        "renderer": version("resvg-py"),
                        "one_logical_cpu": args.one_cpu,
                    },
                    "options": {
                        "preset": "auto",
                        "layering": "auto",
                        "geometry": True,
                        "speckle": 1,
                    },
                    "memory_method": "Whole-process RSS sampled every 2ms during tracing. Includes interpreter, imported libraries and preceding benchmark images; growth is relative to each case's baseline, not isolated worker memory. Vendor timing and memory unavailable.",
                    "notes": "Publicly offered demo pairs only. No uploads, accounts, private artwork, model training or vendor assets redistributed. Error to vendor output measures agreement, not objective superiority; input error can reward preserving JPEG artifacts. Sample set is vendor-selected.",
                    "results": rows,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
