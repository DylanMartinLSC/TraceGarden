"""Real-image benchmark using scikit-image's locally bundled NASA astronaut image."""

import io
import argparse
import json
import multiprocessing as mp
import platform
import statistics
import time
from pathlib import Path
from importlib.metadata import version
import psutil
from PIL import Image
import skimage
from studio import worker


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("benchmarks/photograph-results.json")
    )
    args = parser.parse_args()
    image = Image.open(
        Path(skimage.__file__).parent / "data" / "astronaut.png"
    ).convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PNG")
    data = out.getvalue()
    config = {"preset": "photo", "precision": 6, "smooth": True, "layer_difference": 48}
    results = []
    peaks = []
    times = []
    for _ in range(3):
        parent, child = mp.get_context("spawn").Pipe(duplex=False)
        process = mp.get_context("spawn").Process(
            target=worker, args=(child, data, config)
        )
        start = time.perf_counter()
        process.start()
        child.close()
        peak = 0
        try:
            while not parent.poll():
                if not process.is_alive():
                    raise RuntimeError("Benchmark worker stopped")
                if time.perf_counter() - start > 120:
                    raise RuntimeError("Photo benchmark timed out")
                try:
                    peak = max(peak, psutil.Process(process.pid).memory_info().rss)
                except psutil.NoSuchProcess:
                    pass
                time.sleep(0.01)
            results.append(parent.recv())
            times.append(time.perf_counter() - start)
            peaks.append(peak / 1024**2)
        finally:
            process.join(3)
            if process.is_alive():
                process.terminate()
                process.join()
            parent.close()
    result = {
        "case": "NASA astronaut (Eileen Collins)",
        "source": "https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut",
        "license": "Public domain, per scikit-image documentation",
        "platform": platform.platform(),
        "engine": version("vtracer"),
        "tracegarden": version("tracegarden"),
        "size": list(image.size),
        "runs": 3,
        "trace_median_s": round(statistics.median(r["seconds"] for r in results), 4),
        "process_wall_median_s": round(statistics.median(times), 4),
        "peak_rss_mib": round(max(peaks), 1),
        "mae": results[-1]["mae"],
        "paths": results[-1]["paths"],
        "svg_bytes": results[-1]["svg_bytes"],
        "config": config,
        "notes": "One natural photograph, three fresh CPU workers. Peak RSS sampled every 10ms includes quality rendering. No paid-service comparison; no claim that one photograph establishes general quality parity.",
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
