import sys
from playwright.sync_api import sync_playwright

def run():
    print("Launching Chromium via Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        errors = []
        page.on("console", lambda msg: print(f"[{msg.type}] {msg.text}") if msg.type in ["error", "warning"] else None)
        page.on("pageerror", lambda err: errors.append(f"PageError: {err}"))

        # 1. Main landing page
        print("\n--- 1. Testing Landing Page (/) ---")
        res = page.goto("http://localhost:8010/", wait_until="networkidle")
        print(f"Status: {res.status}")
        page.screenshot(path="tests/e2e_results/01_landing_page.png")
        title = page.title()
        print(f"Title: {title}")
        hero_btn = page.query_selector("#heroRegBtn")
        print(f"Hero Reg Button present: {bool(hero_btn)}")

        # 2. Passport page
        print("\n--- 2. Testing Passport Page (/passport) ---")
        res = page.goto("http://localhost:8010/passport", wait_until="networkidle")
        print(f"Status: {res.status}")
        page.screenshot(path="tests/e2e_results/02_passport_page.png")
        print(f"Passport Title: {page.title()}")

        # 3. Board page
        print("\n--- 3. Testing Board Page (/board) ---")
        res = page.goto("http://localhost:8010/board", wait_until="networkidle")
        print(f"Status: {res.status}")
        # wait a bit for canvas / assets
        page.wait_for_timeout(2000)
        page.screenshot(path="tests/e2e_results/03_board_page.png")
        print(f"Board Title: {page.title()}")

        browser.close()

        if errors:
            print(f"\nEncountered page errors: {errors}")
            sys.exit(1)
        else:
            print("\nInitial smoke check passed successfully!")

if __name__ == "__main__":
    run()
