"""Real browser workflows for project recovery and advanced editing."""

import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1200})
    page.on("dialog", lambda d: d.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(os.environ.get("TRACEGARDEN_URL", "http://127.0.0.1:8743"))
    page.get_by_role("button", name="Try a sample image").click()
    page.get_by_role("button", name="Vectorize images").click()
    expect(page.locator("#status")).to_contain_text(
        "1 of 1 images converted.", timeout=30000
    )
    original_count = page.locator("#vector svg path").count()
    # New polygon with actual pointer coordinates.
    page.locator("#tool").select_option("pen")
    page.locator("#vector svg").scroll_into_view_if_needed()
    box = page.locator("#vector svg").bounding_box()
    for x, y in [(0.2, 0.2), (0.35, 0.2), (0.35, 0.35)]:
        page.mouse.click(box["x"] + box["width"] * x, box["y"] + box["height"] * y)
    page.get_by_role("button", name="Finish drawing").click()
    assert page.locator("#vector svg path").count() == original_count + 1
    # Node editor roundtrip, opacity and redo.
    page.locator("#vector svg path").last.dispatch_event("click")
    page.get_by_role("button", name="Edit nodes", exact=True).click()
    expect(page.locator("#nodePanel")).to_be_visible()
    page.locator("#nodes").fill("30,30\n80,30\n80,80\n30,80")
    page.get_by_role("button", name="Apply nodes").click()
    expect(page.locator("#nodePanel")).to_be_hidden()
    page.locator("#vector svg path").last.dispatch_event("click")
    page.locator("#shapeOpacity").fill("0.5")
    page.locator("#shapeOpacity").dispatch_event("change")
    assert page.locator("#vector svg path").last.get_attribute("opacity") == "0.5"
    page.get_by_role("button", name="Undo edit", exact=True).click()
    page.get_by_role("button", name="Redo edit", exact=True).click()
    assert page.locator("#vector svg path").last.get_attribute("opacity") == "0.5"
    # Save portable project and recover an IndexedDB autosave after reload.
    with page.expect_download() as d:
        page.get_by_role("button", name="Save project", exact=True).click()
    d.value.save_as("work/project.tracegarden")
    page.wait_for_timeout(900)
    page.reload()
    page.get_by_role("button", name="Recover autosave").click()
    expect(page.locator("#status")).to_have_text("Project restored.", timeout=10000)
    assert page.locator("#vector svg path").count() == original_count + 1
    page.get_by_role("button", name="Clear this session").click()
    expect(page.locator("#status")).to_have_text("Session and autosave cleared.")
    page.locator("#projectFile").set_input_files("work/project.tracegarden")
    expect(page.locator("#status")).to_have_text("Project restored.")
    assert page.locator("#vector svg path").count() == original_count + 1
    # Export settings and all formats after a recovered edited document.
    for fmt in ["pdf", "eps", "dxf", "ai", "png"]:
        page.locator("#format").select_option(fmt)
        with page.expect_download() as d:
            page.get_by_role("button", name="Download selected").click()
        d.value.save_as(f"work/studio-result.{fmt}")
        assert Path(f"work/studio-result.{fmt}").stat().st_size > 100
    # Brush corrections change source and invalidate the old trace.
    page.locator("#repair summary").click()
    page.get_by_role("button", name="Enable brush", exact=True).click()
    box = page.locator("#repairCanvas").bounding_box()
    page.mouse.move(box["x"] + 30, box["y"] + 30)
    page.mouse.down()
    page.mouse.move(box["x"] + 60, box["y"] + 60)
    page.mouse.up()
    expect(page.locator("#editor")).to_be_hidden()
    page.get_by_role("button", name="Undo brush", exact=True).click()
    # Cancel a batch and confirm it leaves the UI usable.
    page.get_by_role("button", name="Vectorize images").click()
    page.get_by_role("button", name="Cancel current batch").click()
    expect(page.locator("#convert")).to_be_enabled(timeout=30000)
    page.screenshot(path="work/studio-v2-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path="work/studio-v2-mobile.png", full_page=True)
    assert not errors, errors
    browser.close()
    print(
        "Studio browser checks passed: pen, nodes, opacity, undo/redo, save/import/recovery, five exports, brush, cancel, mobile."
    )
