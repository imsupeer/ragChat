import sys
from playwright.sync_api import sync_playwright


def check(name: str, passed: bool) -> None:
    print(f"{'OK' if passed else 'FAIL'}: {name}")
    if not passed:
        sys.exit(1)


def visible_panel(page):
    return page.get_by_text("Evidence Workspace").locator("xpath=ancestor::aside[1]").first


def open_debug_tab(page) -> None:
    visible_panel(page).get_by_role("button", name="Debug", exact=True).click()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        try:
            page.goto("http://localhost:3000", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)

            chat = page.get_by_text("Batch 4 manual check", exact=False).first
            if chat.count():
                chat.click()
                page.wait_for_timeout(1500)

            page.locator("text=Assistant").first.click()
            open_debug_tab(page)
            page.wait_for_timeout(1000)

            aside = visible_panel(page).inner_text().upper()
            check("UI debug panel shows Used in Prompt", "USED IN PROMPT" in aside)
            check("UI debug panel shows Retrieved Candidates", "RETRIEVED CANDIDATES" in aside)
            check("UI debug panel shows trace metrics", "TOTAL LATENCY" in aside and "PROMPT TOKENS" in aside)
            check(
                "UI debug panel is not unavailable placeholder",
                "DEBUG METADATA IS NOT AVAILABLE FOR THIS MESSAGE" not in aside,
            )

            page.reload(wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2500)

            chat = page.get_by_text("Batch 4 manual check", exact=False).first
            if chat.count():
                chat.click()
                page.wait_for_timeout(1500)

            page.locator("text=Assistant").first.click()
            open_debug_tab(page)
            page.wait_for_timeout(1000)

            reloaded = visible_panel(page).inner_text().upper()
            check("Debug persists after reload (Used in Prompt)", "USED IN PROMPT" in reloaded)
            check("Debug persists after reload (trace metrics)", "TOTAL LATENCY" in reloaded)

            regenerate = page.get_by_role("button", name="Regenerate").first
            if regenerate.count():
                regenerate.click()
                page.wait_for_timeout(15000)
                open_debug_tab(page)
                page.wait_for_timeout(1000)
                regen = visible_panel(page).inner_text().upper()
                check(
                    "Debug panel populated after regenerate",
                    "USED IN PROMPT" in regen and "OUTPUT TOKENS" in regen,
                )
            else:
                print("SKIP: Regenerate button not found")
        finally:
            browser.close()

    print("\nAll UI manual checks passed.")


if __name__ == "__main__":
    main()
