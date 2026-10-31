"""Quality selection, conversion feedback and project option persistence."""

import os

from playwright.sync_api import expect, sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(os.environ["TRACEGARDEN_URL"])
    expect(page.locator("#quality")).to_have_value("fast")
    page.locator("#quality").select_option("high")
    assert page.evaluate("config().quality") == "high"
    expect(page.locator("#precision")).to_have_value("6")
    expect(page.locator("#gradients")).to_be_checked()
    page.locator("#demo").click()
    page.locator("#convert").click()
    expect(page.locator("#status")).to_contain_text(
        "1 of 1 images converted.", timeout=60000
    )
    expect(page.locator("#parityFeedback")).to_contain_text("High Quality")
    assert page.evaluate("async () => (await project()).options.quality") == "high"
    page.evaluate("async () => { window.qualityProject = await project(); }")
    page.locator("#quality").select_option("fast")
    expect(page.locator("#precision")).to_have_value("4")
    # Result labels describe the completed conversion, independent of current controls.
    expect(page.locator("#parityFeedback")).to_contain_text("High Quality")
    page.evaluate("async () => { await restore(window.qualityProject); }")
    expect(page.locator("#quality")).to_have_value("high")
    page.evaluate("applyConfig({quality:'high',precision:7})")
    expect(page.locator("#quality")).to_have_value("high")
    expect(page.locator("#precision")).to_have_value("7")
    page.evaluate("applyConfig({preset:'auto'})")
    expect(page.locator("#quality")).to_have_value("fast")
    page.locator("#convert").click()
    expect(page.locator("#parityFeedback")).to_contain_text("Fast", timeout=60000)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors, errors
    browser.close()
print("Quality browser checks passed")
