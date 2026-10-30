"""Run against a running local server: python tests/browser_check.py."""

from pathlib import Path
import os
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1150})
    page.on("dialog", lambda dialog: dialog.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(os.environ.get("TRACEGARDEN_URL", "http://127.0.0.1:8741"))
    page.get_by_role("button", name="Try a sample image").click()
    page.get_by_role("button", name="Vectorize images").click()
    page.wait_for_selector("#editor:not([hidden])")
    assert page.locator("#vector svg path").count() > 0
    page.locator("#palette input").first.fill("#ff0000")
    page.locator("#palette input").first.dispatch_event("change")
    with page.expect_download() as download:
        page.get_by_role("button", name="Download selected").click()
    download.value.save_as("work/browser-export.svg")
    assert "<svg" in Path("work/browser-export.svg").read_text()
    page.locator("#vector svg path").first.dispatch_event("click")
    count = page.locator("#vector svg path").count()
    page.get_by_role("button", name="Delete selected shape").click()
    assert page.locator("#vector svg path").count() == count - 1
    page.get_by_role("button", name="Undo edit", exact=True).click()
    assert page.locator("#vector svg path").count() == count
    page.get_by_role("button", name="Try a sample image").click()
    page.get_by_role("button", name="Vectorize images").click()
    expect(page.locator("#status")).to_contain_text("2 of 2", timeout=30000)
    with page.expect_download() as download:
        page.get_by_role("button", name="Download all").click()
    download.value.save_as("work/browser-batch.zip")
    page.screenshot(path="work/studio-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path="work/studio-mobile.png", full_page=True)
    assert not errors, errors
    page.get_by_role("button", name="Clear this session").click()
    assert page.locator("#queue button").count() == 0
    browser.close()
    print(
        "Browser check passed: sample, trace, recolor, export, delete/undo, batch ZIP, mobile, clear; no JS errors."
    )
