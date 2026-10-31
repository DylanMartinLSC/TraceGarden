import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_core import fixture_image

from tracegarden.app import app
from tracegarden.core import Options, trace
from tracegarden.quality import resolve_options
from tracegarden.tuning import current, experimental_tuning


def test_cli_high_quality_batch(tmp_path):
    source = tmp_path / "input.png"
    source.write_bytes(fixture_image())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tracegarden",
            "convert",
            str(source),
            "--quality",
            "high",
            "--output",
            str(tmp_path / "vectors"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(result.stdout)
    assert metadata["quality"]["profile"] == "graph-fidelity-v1"
    assert (
        Path(metadata["output"]).read_text()
        == trace(source.read_bytes(), Options(quality="high"))["svg"]
    )


def test_high_reproduces_published_candidate_and_restores_context():
    candidate = json.loads(
        Path("docs/experiments/graphseeds/raw-fidelity-finalist.json").read_text()
    )
    before = current()
    with experimental_tuning(candidate["tuning"]):
        expected = trace(fixture_image(), Options(**candidate["options"]))
    actual = trace(fixture_image(), Options(quality="high"))
    assert actual["svg"] == expected["svg"]
    assert actual["quality"]["status"] == "applied"
    assert current() is before
    assert (
        trace(fixture_image(), Options())["svg"]
        == trace(fixture_image(), Options(quality="fast"))["svg"]
    )
    with pytest.raises(ValueError):
        trace(b"bad image", Options(quality="high"))
    assert current() is before


def test_explicit_controls_and_specialized_styles_retained():
    options = Options(
        quality="high",
        precision=3,
        geometry=False,
        max_size=80,
        palette=["#ffffff", "#000000"],
        crop=(0, 0, 60, 60),
    )
    resolved = resolve_options(options)
    assert resolved.precision == 3 and not resolved.geometry and resolved.max_size == 80
    result = trace(fixture_image(), options)
    assert result["width"] == 60 and result["quality"]["status"] == "not_applicable"
    for preset in ["ink", "pixel", "centerline"]:
        options = Options(quality="high", preset=preset)
        assert resolve_options(options) is options
        assert trace(fixture_image(), options)["quality"]["status"] == "not_applicable"


def test_transparency_and_budget_feedback(monkeypatch):
    image = Image.new("RGBA", (32, 32), (120, 60, 20, 128))
    data = io.BytesIO()
    image.save(data, "PNG")
    assert (
        trace(data.getvalue(), Options(quality="high"))["quality"]["status"]
        == "not_applicable"
    )
    monkeypatch.setattr(
        "tracegarden.regions.merge_regions",
        lambda *a, **kw: (
            None,
            {"applied": False, "reason": "merge work budget exceeded"},
        ),
    )
    result = trace(fixture_image(), Options(quality="high"))
    assert result["quality"]["status"] == "fallback"
    assert result["quality"]["message"] in result["warnings"]


def test_api_and_spawned_job_match_direct_high_profile():
    data = fixture_image()
    expected = trace(data, Options(quality="high"))
    with TestClient(app) as client:
        files = {"file": ("fixture.png", data, "image/png")}
        options = {"options": '{"quality":"high"}'}
        direct = client.post("/api/trace", files=files, data=options)
        assert direct.status_code == 200 and direct.json()["svg"] == expected["svg"]
        response = client.post("/api/jobs", files=files, data=options)
        assert response.status_code == 202
        ident = response.json()["id"]
        for _ in range(200):
            job = client.get(f"/api/jobs/{ident}").json()
            if job["state"] not in {"queued", "running"}:
                break
            time.sleep(0.1)
        assert job["state"] == "complete", job
        assert job["result"]["svg"] == expected["svg"]
        assert job["result"]["quality"] == expected["quality"]
        assert (
            client.post(
                "/api/trace", files=files, data={"options": '{"quality":"unknown"}'}
            ).status_code
            == 400
        )


def test_app_sessions_do_not_reuse_tasks_from_closed_event_loops():
    import importlib

    app_module = importlib.import_module("tracegarden.app")
    managers = []
    for _ in range(2):
        with TestClient(app) as client:
            manager = app_module.jobs
            assert not manager.jobs
            assert all(manager is not previous for previous in managers)
            managers.append(manager)
            response = client.post(
                "/api/jobs",
                files={"file": ("fixture.png", fixture_image(), "image/png")},
            )
            ident = response.json()["id"]
            for _ in range(200):
                state = client.get(f"/api/jobs/{ident}").json()
                if state["state"] not in {"queued", "running"}:
                    break
                time.sleep(0.1)
            assert state["state"] == "complete", state
        assert all(
            job.task.done() and job.process is None for job in manager.jobs.values()
        )
        assert all(job.task.get_loop().is_closed() for job in manager.jobs.values())
