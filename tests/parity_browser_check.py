"""Acceptance workflows for the advertised comparison, corners and export controls."""

import os
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1200})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(os.environ["TRACEGARDEN_URL"])
    page.locator("#demo").click()
    page.locator("#convert").click()
    expect(page.locator("#status")).to_contain_text(
        "1 of 1 images converted.", timeout=30000
    )
    page.locator("[data-view=wipe]").click()
    assert "wipe-mode" in page.locator("#previews").get_attribute("class")
    page.locator("#compareSplit").fill("25")
    page.locator("#compareSplit").dispatch_event("input")
    assert "25%" in page.locator("#vectorPane").get_attribute("style")
    page.locator("[data-view=outlines]").click()
    expect(page.locator("#originalPane")).to_be_hidden()
    page.locator("[data-view=vector]").click()
    page.locator("#vector svg path").first.dispatch_event("click")
    page.locator("summary").filter(has_text="Parameterized shapes").click()
    page.locator("#paramKind").select_option("star")
    page.locator("#paramRotate").fill("27")
    page.locator("#applyShape").click()
    expect(page.locator("#status")).to_have_text("Shape geometry applied.")
    expect(page.locator("#vector svg path").first).to_have_attribute(
        "d", __import__("re").compile(".*L.*")
    )
    page.locator("#vector svg path").first.dispatch_event("click")
    page.locator("#cornerWorkspace summary").click()
    page.locator("#loadCorners").click()
    expect(page.locator("#status")).to_contain_text("10 corners loaded")
    page.locator("#cornerRadius").fill("5")
    page.locator("#cornerRadius").dispatch_event("input")
    expect(page.locator("#status")).to_contain_text("Corner preview", timeout=10000)
    page.locator("#applyCorners").click()
    assert "A" in page.locator("#vector svg path").first.get_attribute("d")
    for fmt in ["jpg", "tiff", "gif", "bmp"]:
        page.locator("#format").select_option(fmt)
        with page.expect_download() as download:
            page.locator("#save").click()
        path = Path(f"work/parity-export.{fmt}")
        download.value.save_as(path)
        assert Image.open(path).size == (512, 512)
    page.locator("summary").filter(has_text="Export settings").click()
    page.locator("#grouping").select_option("color")
    page.locator("#curve_mode").select_option("quadratic")
    page.locator("#format").select_option("svg")
    with page.expect_download() as download:
        page.locator("#save").click()
    download.value.save_as("work/grouped-quadratic.svg")
    assert "<g>" in Path("work/grouped-quadratic.svg").read_text()
    page.screenshot(path="work/parity-desktop.png", full_page=True)
    assert not errors, errors
    browser.close()
    print(
        "Parity UI passed: wipe, outline, star parameters, corner preview/apply, all bitmap formats, grouped quadratic SVG."
    )
