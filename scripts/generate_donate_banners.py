import os
from playwright.sync_api import sync_playwright

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<style>
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}
  body {{
    width: 3200px;
    height: 480px;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }}
  .card {{
    width: 3160px;
    height: 440px;
    background: #080d1a;
    border: 5px solid #1d4ed8;
    border-radius: 40px;
    display: flex;
    align-items: center;
    padding: 0 100px;
    position: relative;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), inset 0 0 40px rgba(29, 78, 216, 0.15);
  }}
  .heart-box {{
    flex-shrink: 0;
    margin-right: 70px;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .heart-icon {{
    width: 170px;
    height: 170px;
    filter: drop-shadow(0 10px 25px rgba(217, 70, 239, 0.45));
  }}
  .content {{
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}
  .title {{
    font-size: 82px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
    line-height: 1.1;
    margin-bottom: 12px;
  }}
  .subtitle {{
    font-size: 40px;
    font-weight: 400;
    color: #94a3b8;
    line-height: 1.25;
    margin-bottom: 14px;
  }}
  .action {{
    font-size: 42px;
    font-weight: 700;
    color: #38bdf8;
    line-height: 1.2;
    display: flex;
    align-items: center;
    gap: 16px;
  }}
  .chart-box {{
    flex-shrink: 0;
    margin-left: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .chart-svg {{
    width: 420px;
    height: 280px;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="heart-box">
    <svg class="heart-icon" viewBox="0 0 24 24">
      <defs>
        <linearGradient id="heartGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#ec4899" />
          <stop offset="100%" stop-color="#c026d3" />
        </linearGradient>
      </defs>
      <path fill="url(#heartGrad)" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
    </svg>
  </div>
  <div class="content">
    <div class="title">{title}</div>
    <div class="subtitle">{subtitle}</div>
    <div class="action">{action}</div>
  </div>
  <div class="chart-box">
    <svg class="chart-svg" viewBox="0 0 340 220">
      <defs>
        <linearGradient id="goldArrow" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#fde047" />
          <stop offset="100%" stop-color="#f59e0b" />
        </linearGradient>
      </defs>
      <!-- Ascending Bars -->
      <rect x="20"  y="150" width="34" height="60" rx="8" fill="#d946ef" />
      <rect x="70"  y="120" width="34" height="90" rx="8" fill="#2563eb" />
      <rect x="120" y="140" width="34" height="70" rx="8" fill="#d946ef" />
      <rect x="170" y="80"  width="34" height="130" rx="8" fill="#2563eb" />
      <rect x="220" y="110" width="34" height="100" rx="8" fill="#d946ef" />
      <rect x="270" y="30"  width="34" height="180" rx="8" fill="#3b82f6" />

      <!-- Growth Trend Arrow -->
      <path d="M 10 160 Q 150 110 300 25" fill="none" stroke="url(#goldArrow)" stroke-width="9" stroke-linecap="round" />
      <polygon points="300,10 322,26 304,40" fill="#f59e0b" />
    </svg>
  </div>
</div>
</body>
</html>
"""

def generate():
    os.makedirs("docs/assets", exist_ok=True)
    
    configs = [
        {
            "lang": "en",
            "title": "Support BormoClass",
            "subtitle": "Sovereign, Zero-PII classroom platform & interactive whiteboard. If it empowers your school —",
            "action": "buy the author a coffee → dalink.to/bormotoon",
            "out_png": "docs/assets/donate_banner.png",
        },
        {
            "lang": "ru",
            "title": "Поддержать BormoClass",
            "subtitle": "Суверенная Zero-PII платформа и школьная доска. Если она помогает вашей школе —",
            "action": "угостите автора кофе → dalink.to/bormotoon",
            "out_png": "docs/assets/donate_banner_ru.png",
        }
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True)
        for cfg in configs:
            page = browser.new_page(viewport={"width": 3200, "height": 480}, device_scale_factor=1)
            html = HTML_TEMPLATE.format(**cfg)
            page.set_content(html)
            page.wait_for_timeout(500)
            # Take screenshot of the exact 3200x480 box
            page.screenshot(path=cfg["out_png"], omit_background=True)
            print(f"Generated {cfg['out_png']} (3200x480)")
            page.close()
        browser.close()

if __name__ == "__main__":
    generate()
