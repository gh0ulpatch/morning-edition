from pathlib import Path
from datetime import datetime
import json
import html

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "sample_events.json"
ISSUES_DIR = ROOT / "issues"
INDEX_FILE = ROOT / "index.html"

ISSUES_DIR.mkdir(exist_ok=True)

def load_events():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def render_issue(issue_date, conferences):
    def esc(x):
        return html.escape(str(x))

    items = []
    for i, c in enumerate(conferences, start=1):
        items.append(f"""
        <section style="padding:40px;border-top:1px solid #ccc;">
          <h2 style="font-size:48px;margin:0 0 10px 0;">{i:02d}. {esc(c["title"])}</h2>
          <p style="font-size:24px;"><strong>Date:</strong> {esc(c["date"])}</p>
          <p style="font-size:24px;"><strong>Where:</strong> {esc(c["location"])}</p>
          <p style="font-size:24px;"><strong>Host:</strong> {esc(c["host"])}</p>
          <p style="font-size:24px;"><strong>Why it matters:</strong> {esc(c["why"])}</p>
          <p style="font-size:24px;"><strong>Watch:</strong> {esc(c["watch"])}</p>
          <p style="font-size:24px;"><a href="{esc(c['source'])}" target="_blank">Open source link</a></p>
        </section>
        """)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Morning Edition · {issue_date}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f7f3ea;
      color: #111;
    }}
    header {{
      padding: 40px;
      background: #ead9b8;
    }}
    h1 {{
      font-size: 72px;
      margin: 0 0 20px 0;
    }}
    p {{
      line-height: 1.4;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Morning Edition</h1>
    <p style="font-size:28px;">Issue date: {issue_date}</p>
    <p style="font-size:28px;">A simple first version of your daily AI conference magazine.</p>
  </header>
  {''.join(items)}
</body>
</html>"""

def render_latest_index(issue_date):
    issue_href = f"./issues/{issue_date}.html"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url={issue_href}">
  <title>Morning Edition · Latest</title>
</head>
<body>
  <p>Redirecting to the latest issue: <a href="{issue_href}">{issue_href}</a></p>
</body>
</html>
"""

def main():
    events = load_events()
    issue_date = datetime.now().strftime("%Y-%m-%d")

    issue_file = ISSUES_DIR / f"{issue_date}.html"
    issue_html = render_issue(issue_date, events[:10])

    issue_file.write_text(issue_html, encoding="utf-8")
    INDEX_FILE.write_text(render_latest_index(issue_date), encoding="utf-8")

    print(f"Created {issue_file}")
    print(f"Updated {INDEX_FILE}")

if __name__ == "__main__":
    main()
