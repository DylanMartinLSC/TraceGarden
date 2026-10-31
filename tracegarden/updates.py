"""User-initiated release lookup. No polling, tracking or automatic execution."""

import json
import urllib.request
import urllib.error
from importlib.metadata import version
from packaging.version import Version, InvalidVersion


def check_updates():
    current = version("tracegarden")
    request = urllib.request.Request(
        "https://api.github.com/repos/DylanMartinLSC/TraceGarden/releases?per_page=20",
        headers={
            "User-Agent": "TraceGarden-update-check",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ValueError("Release information was unexpectedly large.")
            releases = json.loads(data)
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError(
            "Could not check for updates. You can keep using TraceGarden offline."
        ) from exc
    published = [r for r in releases if not r.get("draft")]
    stable = [r for r in published if not r.get("prerelease")]
    candidates = stable or published
    if not candidates:
        return {"current": current, "available": False}
    release = candidates[0]
    tag = release.get("tag_name", "").removeprefix("v")
    try:
        available = Version(tag) > Version(current)
    except InvalidVersion:
        raise ValueError("The published release version could not be read.")
    return {
        "current": current,
        "latest": tag,
        "available": available,
        "prerelease": release.get("prerelease", False),
        "url": "https://github.com/DylanMartinLSC/TraceGarden/releases",
        "notes": release.get("body", "")[:8000],
    }
