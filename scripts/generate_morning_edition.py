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
    """Load and validate the JSON event list."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing data file: {DATA_FILE}")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("sample_events.json must contain a JSON list")

    cleaned = []
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {i} in sample_events.json is not an object")

        cleaned.append({
            "title": str(item.get("title", "Untitled conference")),
            "date": str(item.get("date", "TBC")),
            "location": str(item.get("location", "TBC")),
            "host": str(item.get("host", "TBC")),
            "applies": str(item.get("applies", "APPLIES")),
            "tag": str(item.get("tag", "policy")),
            "angle": str(item.get("angle", "AI conference")),
            "why": str(item.get("why", "")),
            "watch": str(item.get("watch", "")),
            "source": str(item.get("source", "#")),
        })

    return cleaned


def esc(value):
    return html.escape(str(value), quote=True)


def render_issue(issue_date, conferences):
    spreads = []

    palettes = [
        {"bg": "#fffdf8", "fg": "#111111", "accent": "#ead9b8"},
        {"bg": "#0e1a32", "fg": "#f7f8fb", "accent": "#1a2650"},
        {"bg": "#f7dbe2", "fg": "#541729", "accent": "#f3c3cf"},
        {"bg": "#eee5d5", "fg": "#111111", "accent": "#ddd1bd"},
        {"bg": "#07150f", "fg": "#d8ffdf", "accent": "#0d2018"},
        {"bg": "#dbe8ff", "fg": "#111111", "accent": "#cfddff"},
        {"bg": "#e7e1d1", "fg": "#111111", "accent": "#d6cfbb"},
        {"bg": "#efc7bc", "fg": "#111111", "accent": "#df9f8f"},
        {"bg": "#dae8ff", "fg": "#111111", "accent": "#c7dbff"},
        {"bg": "#432522", "fg": "#fff6ef", "accent": "#a45f50"},
    ]

    for i, c in enumerate(conferences[:10], start=1):
        theme = palettes[(i - 1) % len(palettes)]
        spreads.append(f"""
<section style="min-height:100vh;padding:36px 30px;border-top:1px solid rgba(0,0,0,.15);background:{theme['bg']};color:{theme['fg']};">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:start;min-height:calc(100vh - 72px);">
    <div>
      <div style="font-size:18px;font-weight:900;text-transform:uppercase;letter-spacing:.12em;margin-bottom:10px;">{esc(c['angle'])}</div>
      <div style="font-family:Georgia,serif;font-size:140px;line-height:.85;letter-spacing:-.08em;">{i:02d}</div>
      <h2 style="font-family:Georgia,serif;font-size:64px;line-height:.95;letter-spacing:-.05em;margin:8px 0 0;max-width:9ch;">{esc(c['title'])}</h2>
    </div>
    <div>
      <div style="display:grid;gap:10px;font-size:24px;line-height:1.25;margin-top:8px;">
        <div><strong>Date</strong> {esc(c['date'])}</div>
        <div><strong>Where</strong> {esc(c['location'])}</div>
        <div><strong>Host</strong> {esc(c['host'])}</div>
      </div>

      <div style="display:flex;gap:12px;flex-wrap:wrap;margin:18px 0 18px;">
        <div style="font-size:16px;font-weight:900;padding:10px 14px;border:1px solid currentColor;border-radius:999px;">{esc(c['applies'])}</div>
        <div style="font-size:16px;font-weight:900;padding:10px 14px;border:1px solid currentColor;border-radius:999px;">{esc(c['tag'])}</div>
      </div>

      <div style="font-size:28px;line-height:1.2;max-width:30ch;">{esc(c['why'])}</div>

      <div style="margin-top:18px;border:1px solid rgba(0,0,0,.18);border-radius:20px;padding:18px 20px;font-size:22px;line-height:1.35;max-width:42ch;background:{theme['accent']};">
        <strong>Why it matters:</strong> {esc(c['watch'])}
      </div>

      <p style="margin-top:16px;font-size:18px;font-weight:700;">
        <a href="{esc(c['source'])}" target="_blank" rel="noopener" style="color:inherit;">Open source ↗</a>
      </p>
    </div>
  </div>
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
      color: #111111;
    }}
    .cover {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 1.15fr .85fr;
      gap: 26px;
      padding: 48px 32px 34px;
      background: linear-gradient(160deg,#f7f1e7 0%, #efe4c9 55%, #e5d5b6 100%);
    }}
    .cover h1 {{
      font-family: Georgia, serif;
      font-size: 110px;
      line-height: .9;
      letter-spacing: -.07em;
      margin: 0;
      max-width: 8ch;
    }}
    .kicker {{
      font-size: 20px;
      font-weight: 900;
      letter-spacing: .12em;
      text-transform: uppercase;
      margin-bottom: 16px;
    }}
    .deck {{
      margin-top: 22px;
      font-size: 28px;
      line-height: 1.2;
      max-width: 18ch;
    }}
    .index {{
      margin-top: 26px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0,1fr));
      gap: 12px;
    }}
    .index-item {{
      border-top: 2px solid #111111;
      padding-top: 10px;
      font-size: 20px;
      line-height: 1.2;
    }}
    .signal-col {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .signal {{
      border: 1px solid rgba(17,17,17,.16);
      border-radius: 24px;
      background: rgba(255,255,255,.38);
      padding: 18px;
      font-size: 20px;
      line-height: 1.3;
    }}
    .signal strong {{
      display: block;
      font-size: 21px;
      margin-bottom: 8px;
    }}
    @media (max-width: 1050px) {{
      .cover {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <section class="cover">
    <div>
      <div class="kicker">AI harm · safety · security · policy</div>
      <h1>Ten conferences worth your attention now.</h1>
      <div class="deck">
        A policy-leaning morning magazine focused on conferences that matter for AI safety,
        security, governance, law, and multilateral signal.
      </div>

      <div class="index">
        {''.join(f"<div class='index-item'>{i:02d}. {esc(c['title'])}</div>" for i, c in enumerate(conferences[:10], start=1))}
      </div>
    </div>

    <div class="signal-col">
      <div class="signal"><strong>Signal</strong>Strong weight given to multilateral, government, legal, security, and governance relevance.</div>
      <div class="signal"><strong>Signal</strong>Built as a single self-contained HTML issue with large editorial typography.</div>
      <div class="signal"><strong>Signal</strong>Each conference gets its own spread and source link.</div>
    </div>
  </section>

  {''.join(spreads)}
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
    issue_html = render_issue(issue_date, events)

    issue_file.write_text(issue_html, encoding="utf-8")
    INDEX_FILE.write_text(render_latest_index(issue_date), encoding="utf-8")

    print(f"Created {issue_file}")
    print(f"Updated {INDEX_FILE}")


if __name__ == "__main__":
    main()
