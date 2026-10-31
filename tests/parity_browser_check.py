"""Acceptance workflows for the advertised comparison, corners and export controls."""

import os
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1200})
    page.on("dialog", lambda dialog: dialog.accept())
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(os.environ["TRACEGARDEN_URL"])
    page.locator("#demo").click()
    expect(page.locator("#queue button")).to_have_count(1)
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
    # A slow edit response must never overwrite a different queued document.
    page.locator("#demo").click()
    expect(page.locator("#queue button")).to_have_count(2)
    page.locator("#convert").click()
    expect(page.locator("#status")).to_contain_text("2 of 2", timeout=30000)
    page.locator("#queue button").first.click()
    page.locator("#vector svg path").first.dispatch_event("click")
    pending = []
    page.route("**/api/edit", lambda route: pending.append(route))
    page.locator('[data-op="simplify"]').click()
    page.wait_for_timeout(100)
    assert pending
    page.locator("#queue button").nth(1).click()
    original = page.locator("#vector").inner_html()
    response = pending[0].fetch()
    pending[0].fulfill(response=response)
    page.wait_for_timeout(100)
    assert page.locator("#vector").inner_html() == original
    page.unroute("**/api/edit")
    transfer = page.evaluate(
        """() => {const dt=new DataTransfer(); document.getElementById('dragVector').dispatchEvent(new DragEvent('dragstart',{dataTransfer:dt})); return {svg:dt.getData('image/svg+xml'),files:Array.from(dt.files).map(f=>({name:f.name,type:f.type}))};}"""
    )
    assert "<path" in transfer["svg"]
    assert transfer["files"][0]["type"] == "image/svg+xml"
    page.locator("summary").filter(has_text="Fine-tune your trace").click()
    page.locator("#background").select_option("auto")
    page.locator("#convert").click()
    expect(page.locator("#convert")).to_be_enabled(timeout=30000)
    expect(page.locator("#status")).to_contain_text("2 of 2", timeout=30000)
    page.locator("#repair summary").click()
    page.locator("#editBackground").click()
    expect(page.locator("#status")).to_contain_text("Brush over pixels to keep")
    canvas = page.locator("#repairCanvas")
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    assert (
        page.evaluate(
            "document.getElementById('repairCanvas').getContext('2d').getImageData(20,20,1,1).data[3]"
        )
        == 0
    )
    page.mouse.click(
        box["x"] + 20 * box["width"] / 512, box["y"] + 20 * box["height"] / 512
    )
    page.wait_for_timeout(100)
    assert (
        page.evaluate(
            "document.getElementById('repairCanvas').getContext('2d').getImageData(20,20,1,1).data[3]"
        )
        == 255
    )
    page.locator("#brushMode").select_option("remove")
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    page.mouse.click(
        box["x"] + 20 * box["width"] / 512, box["y"] + 20 * box["height"] / 512
    )
    page.wait_for_timeout(100)
    assert (
        page.evaluate(
            "document.getElementById('repairCanvas').getContext('2d').getImageData(20,20,1,1).data[3]"
        )
        == 0
    )
    page.screenshot(path="work/parity-desktop.png", full_page=True)
    assert not errors, errors
    browser.close()
    print(
        "Parity UI passed: wipe, outline, star parameters, corner preview/apply, all bitmap formats, grouped quadratic SVG."
    )
