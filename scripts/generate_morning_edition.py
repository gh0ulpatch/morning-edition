from pathlib import Path
from datetime import datetime
import html
import json
import os
import re

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "sample_events.json"
TRACKER_FILE = ROOT / "data" / "tracker.json"
ISSUES_DIR = ROOT / "issues"
INDEX_FILE = ROOT / "index.html"
TRACKER_HTML = ROOT / "tracker.html"

ISSUES_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# DATA
# ──────────────────────────────────────────────────────────────────────────────

def load_events():
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
            "title":    str(item.get("title",    "Untitled conference")),
            "date":     str(item.get("date",     "TBC")),
            "location": str(item.get("location", "TBC")),
            "host":     str(item.get("host",     "TBC")),
            "applies":  str(item.get("applies",  "Monitor")),
            "tag":      str(item.get("tag",      "AI Governance")),
            "angle":    str(item.get("angle",    "AI conference")),
            "why":      str(item.get("why",      "")),
            "watch":    str(item.get("watch",    "")),
            "source":   str(item.get("source",   "#")),
        })
    return cleaned


def update_tracker(issue_date, conferences):
    """Append today's conferences to the cumulative tracker, deduped by source URL."""
    if TRACKER_FILE.exists():
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            tracker = json.load(f)
    else:
        tracker = []

    existing_sources = {row["source"] for row in tracker}
    added = 0
    for i, c in enumerate(conferences, start=1):
        if c["source"] not in existing_sources:
            tracker.append({
                "issue_date": issue_date,
                "issue_index": i,
                "region": infer_region(c.get("location", "")),
                "month": extract_month(c.get("date", ""), issue_date),
                **c,
            })
            existing_sources.add(c["source"])
            added += 1

    # Most-recent issues first
    tracker.sort(key=lambda r: (r["issue_date"], r["issue_index"]), reverse=True)

    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)

    print(f"Tracker: +{added} new, {len(tracker)} total → {TRACKER_FILE}")
    return tracker


def _pages_base() -> str:
    base = os.environ.get("MORNING_EDITION_PAGES_URL", "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo:
            owner, name = repo.split("/", 1)
            base = f"https://{owner}.github.io/{name}"
    return base

def magazine_url(issue_date):
    base = _pages_base()
    return f"{base}/issues/{issue_date}.html" if base else f"./issues/{issue_date}.html"

def tracker_page_url():
    base = _pages_base()
    return f"{base}/tracker.html" if base else "./tracker.html"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def esc(value):
    return html.escape(str(value), quote=True)


VERDICT_STYLE = {
    "Attend":  "background:#1a4d2e;color:#c6f0d5;",
    "Monitor": "background:#6b4000;color:#ffeaa0;",
    "Ignore":  "background:#3a3a3a;color:#e8e8e8;",
}

def verdict_badge(applies):
    style = VERDICT_STYLE.get(applies, "background:#444;color:#fff;")
    return (
        f'<span style="display:inline-block;{style}'
        f'font-size:10px;font-weight:900;letter-spacing:.1em;'
        f'text-transform:uppercase;padding:3px 8px;border-radius:999px;'
        f'font-family:Arial,Helvetica,sans-serif;">{esc(applies)}</span>'
    )


# Region inference
_REGION_MAP = [
    (["virtual", "online", "remote", "hybrid", "zoom", "webinar"], "Online / Virtual"),
    (["uk", "united kingdom", "england", "scotland", "wales", "london", "oxford",
      "cambridge", "edinburgh", "manchester", "birmingham", "brussels", "belgium",
      "paris", "france", "berlin", "germany", "frankfurt", "munich", "amsterdam",
      "netherlands", "the hague", "rotterdam", "geneva", "switzerland", "zurich",
      "rome", "italy", "milan", "madrid", "spain", "barcelona", "stockholm",
      "sweden", "oslo", "norway", "copenhagen", "denmark", "helsinki", "finland",
      "vienna", "austria", "prague", "czech", "warsaw", "poland", "budapest",
      "hungary", "lisbon", "portugal", "dublin", "ireland", "greece", "athens",
      "estonia", "latvia", "lithuania", "luxembourg", "malta", "iceland"], "Europe"),
    (["usa", "united states", "washington", "new york", "san francisco", "chicago",
      "boston", "seattle", "los angeles", "austin", "denver", "atlanta", "miami",
      "silicon valley", "bay area", "canada", "toronto", "vancouver", "montreal",
      "ottawa", "calgary", " dc", "d.c."], "North America"),
    (["brazil", "são paulo", "sao paulo", "rio", "argentina", "buenos aires",
      "chile", "santiago", "colombia", "bogotá", "bogota", "peru", "lima",
      "venezuela", "ecuador", "uruguay", "paraguay", "bolivia"], "Latin America"),
    (["mexico", "costa rica", "panama", "cuba", "guatemala", "honduras",
      "el salvador", "nicaragua", "caribbean", "dominican", "puerto rico", "jamaica"], "Central America"),
    (["china", "beijing", "shanghai", "japan", "tokyo", "india", "delhi", "mumbai",
      "bangalore", "bengaluru", "korea", "seoul", "singapore", "hong kong", "taiwan",
      "thailand", "bangkok", "indonesia", "jakarta", "malaysia", "kuala lumpur",
      "philippines", "manila", "vietnam", "hanoi", "cambodia", "myanmar",
      "sri lanka", "pakistan", "bangladesh", "nepal", "kazakhstan", "uzbekistan"], "Asia"),
    (["uae", "dubai", "abu dhabi", "saudi arabia", "riyadh", "jeddah", "qatar",
      "doha", "kuwait", "bahrain", "israel", "tel aviv", "jordan", "amman",
      "egypt", "cairo", "iran", "tehran", "iraq", "turkey", "istanbul",
      "ankara", "lebanon", "oman"], "Middle East"),
    (["south africa", "johannesburg", "cape town", "nigeria", "lagos", "kenya",
      "nairobi", "ghana", "ethiopia", "addis ababa", "morocco", "casablanca",
      "tunisia", "rwanda", "kigali", "senegal", "dakar", "tanzania",
      "uganda", "cameroon", "ivory coast", "zimbabwe", "angola", "mozambique"], "Africa"),
    (["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide",
      "canberra", "new zealand", "auckland", "wellington", "fiji", "samoa",
      "tonga", "papua new guinea"], "Oceania"),
]

def infer_region(location: str) -> str:
    loc = location.lower()
    for keywords, region in _REGION_MAP:
        if any(k in loc for k in keywords):
            return region
    return "Other"


_MONTH_ABBRS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}
_MONTH_LABELS = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May",     "06": "June",     "07": "July",  "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}

def extract_month(date_str: str, issue_date: str = "") -> str:
    dl = date_str.lower()
    year_m = re.search(r'\b(20\d{2})\b', date_str)
    year = year_m.group(1) if year_m else (issue_date[:4] if issue_date else "")
    for abbr, num in _MONTH_ABBRS.items():
        if abbr in dl:
            return f"{year}-{num}" if year else num
    return ""

def format_month(ym: str) -> str:
    if not ym or "-" not in ym:
        return ym
    year, mon = ym.split("-", 1)
    return f"{_MONTH_LABELS.get(mon, mon)} {year}"


# ──────────────────────────────────────────────────────────────────────────────
# RENDERER 1 — Full magazine (existing)
# ──────────────────────────────────────────────────────────────────────────────

def render_issue(issue_date, conferences, tracker_url="./tracker.html"):
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
    spreads = []
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
</section>""")

    shown = conferences[:10]
    attend  = sum(1 for c in shown if c.get("applies") == "Attend")
    monitor = sum(1 for c in shown if c.get("applies") == "Monitor")
    ignore  = sum(1 for c in shown if c.get("applies") == "Ignore")
    harm_areas = list(dict.fromkeys(c.get("tag", "") for c in shown if c.get("tag")))
    harm_str = " · ".join(harm_areas[:4]) + (" + more" if len(harm_areas) > 4 else "")
    verdict_line = " · ".join(filter(None, [
        f"{attend} Attend" if attend else "",
        f"{monitor} Monitor" if monitor else "",
        f"{ignore} Ignore" if ignore else "",
    ]))

    index_items = ''.join(
        f'<div class="index-item" style="animation-delay:{0.55 + i*0.07:.2f}s">'
        f'{i:02d}. {esc(c["title"])}</div>'
        for i, c in enumerate(shown, start=1)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Morning Edition · {issue_date}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    @keyframes fadeUp {{
      from {{ opacity:0; transform:translateY(22px); }}
      to   {{ opacity:1; transform:translateY(0); }}
    }}
    @keyframes fadeIn {{
      from {{ opacity:0; }}
      to   {{ opacity:1; }}
    }}
    @keyframes gradientShift {{
      0%   {{ background-position: 0% 50%; }}
      50%  {{ background-position: 100% 50%; }}
      100% {{ background-position: 0% 50%; }}
    }}

    body {{ margin:0; font-family:Arial,sans-serif; background:#f7f3ea; color:#111111; }}

    .cover {{
      min-height:100vh;
      display:grid;
      grid-template-columns:1.15fr .85fr;
      gap:26px;
      padding:48px 32px 34px;
      background:linear-gradient(160deg,#f7f1e7,#efe4c9,#e5d5b6,#ede3ca,#f2e8d5);
      background-size:300% 300%;
      animation: gradientShift 12s ease infinite;
    }}

    .kicker {{
      font-size:20px; font-weight:900; letter-spacing:.12em; text-transform:uppercase;
      margin-bottom:16px;
      opacity:0; animation: fadeUp .6s ease forwards; animation-delay:.1s;
    }}
    .cover h1 {{
      font-family:Georgia,serif; font-size:110px; line-height:.9;
      letter-spacing:-.07em; margin:0; max-width:8ch;
      opacity:0; animation: fadeUp .7s ease forwards; animation-delay:.25s;
    }}
    .deck {{
      margin-top:22px; font-size:28px; line-height:1.2; max-width:18ch;
      opacity:0; animation: fadeUp .6s ease forwards; animation-delay:.42s;
    }}
    .index {{
      margin-top:26px;
      display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px;
    }}
    .index-item {{
      border-top:2px solid #111111; padding-top:10px;
      font-size:20px; line-height:1.2;
      opacity:0; animation: fadeUp .5s ease forwards;
    }}

    .signal-col {{
      display:grid; gap:14px; align-content:start;
      opacity:0; animation: fadeIn .8s ease forwards; animation-delay:.9s;
    }}
    .signal {{
      border:1px solid rgba(17,17,17,.16); border-radius:24px;
      background:rgba(255,255,255,.38); padding:18px;
      font-size:20px; line-height:1.3;
    }}
    .signal strong {{ display:block; font-size:21px; margin-bottom:8px; }}
    .signal a {{ color:inherit; font-weight:700; }}

    @media (max-width:1050px) {{ .cover {{ grid-template-columns:1fr; }} }}
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation-duration:.01ms !important;
        animation-delay:.01ms !important;
      }}
    }}
  </style>
</head>
<body>
  <section class="cover">
    <div>
      <div class="kicker">AI harm · safety · security · policy</div>
      <h1>{len(shown)} conference{'s' if len(shown) != 1 else ''} worth your attention now.</h1>
      <div class="deck">{issue_date} · {verdict_line}</div>
      <div class="index">{index_items}</div>
    </div>
    <div class="signal-col">
      <div class="signal"><strong>Verdicts</strong>{verdict_line}</div>
      <div class="signal"><strong>Harm areas</strong>{esc(harm_str)}</div>
      <div class="signal"><strong>Track all conferences</strong><a href="{esc(tracker_url)}">View the cumulative conference tracker ↗</a></div>
    </div>
  </section>
  {''.join(spreads)}
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# RENDERER 2 — Email digest (email-safe, table-based)
# ──────────────────────────────────────────────────────────────────────────────

def render_email_digest(issue_date, conferences, mag_url):
    n = len(conferences[:10])
    rows = []
    for i, c in enumerate(conferences[:10], start=1):
        rows.append(f"""
        <tr>
          <td style="padding:20px 28px 20px;border-bottom:1px solid #ede8dc;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="width:36px;vertical-align:top;padding-right:14px;">
                  <div style="font-family:Georgia,serif;font-size:32px;line-height:1;font-weight:900;color:#c8b89a;">{i:02d}</div>
                </td>
                <td style="vertical-align:top;">
                  <div style="margin-bottom:7px;">
                    {verdict_badge(c['applies'])}
                    <span style="display:inline-block;background:#f0ece2;color:#555;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:999px;margin-left:5px;font-family:Arial,Helvetica,sans-serif;">{esc(c['tag'])}</span>
                  </div>
                  <div style="font-family:Georgia,serif;font-size:17px;font-weight:bold;line-height:1.25;color:#111;margin-bottom:5px;">{esc(c['title'])}</div>
                  <div style="font-size:12px;color:#888;margin-bottom:10px;font-family:Arial,Helvetica,sans-serif;">{esc(c['date'])} &nbsp;·&nbsp; {esc(c['location'])} &nbsp;·&nbsp; {esc(c['host'])}</div>
                  <div style="font-size:14px;color:#333;line-height:1.55;margin-bottom:10px;font-family:Arial,Helvetica,sans-serif;">{esc(c['why'])}</div>
                  <div style="font-size:13px;background:#f5f0e6;border-left:3px solid #c8a96e;padding:10px 14px;color:#555;line-height:1.5;margin-bottom:10px;font-family:Arial,Helvetica,sans-serif;"><strong style="color:#333;">Watch:</strong> {esc(c['watch'])}</div>
                  <a href="{esc(c['source'])}" target="_blank" rel="noopener" style="font-size:13px;font-weight:700;color:#8b4513;text-decoration:none;font-family:Arial,Helvetica,sans-serif;">Open source ↗</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>""")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Morning Edition · {issue_date}</title>
</head>
<body style="margin:0;padding:0;background:#f0ece2;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f0ece2;">
  <tr><td align="center" style="padding:28px 12px;">

    <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;border:1px solid #ddd8cc;">

      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(150deg,#1a1a1a 0%,#2e2416 100%);padding:32px 28px 28px;">
          <div style="font-size:10px;font-weight:900;letter-spacing:.18em;text-transform:uppercase;color:#9a8060;margin-bottom:10px;font-family:Arial,Helvetica,sans-serif;">AI HARM · SAFETY · SECURITY · POLICY</div>
          <div style="font-family:Georgia,serif;font-size:42px;line-height:.9;letter-spacing:-.04em;color:#f5efe4;margin-bottom:10px;">Morning Edition</div>
          <div style="font-size:13px;color:#9a8060;margin-bottom:20px;font-family:Arial,Helvetica,sans-serif;">{issue_date} &nbsp;·&nbsp; {n} conference{'' if n == 1 else 's'} worth your attention</div>
          <a href="{esc(mag_url)}" target="_blank" rel="noopener"
             style="display:inline-block;background:#c8a96e;color:#111;font-size:12px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;padding:10px 18px;border-radius:3px;text-decoration:none;font-family:Arial,Helvetica,sans-serif;">
            Read the full magazine ↗
          </a>
        </td>
      </tr>

      <!-- Divider label -->
      <tr>
        <td style="background:#f5f0e6;padding:10px 28px;border-bottom:1px solid #ede8dc;">
          <span style="font-size:10px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#888;font-family:Arial,Helvetica,sans-serif;">This issue</span>
        </td>
      </tr>

      <!-- Conference rows -->
      {''.join(rows)}

      <!-- Footer -->
      <tr>
        <td style="background:#1a1a1a;padding:24px 28px;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td>
                <div style="font-family:Georgia,serif;font-size:16px;color:#c8b89a;margin-bottom:6px;">Morning Edition</div>
                <div style="font-size:12px;color:#666;font-family:Arial,Helvetica,sans-serif;">AI harm · safety · security · policy</div>
              </td>
              <td align="right" style="vertical-align:middle;">
                <a href="{esc(mag_url)}" target="_blank" rel="noopener"
                   style="font-size:12px;font-weight:700;color:#c8a96e;text-decoration:none;font-family:Arial,Helvetica,sans-serif;">
                  Full magazine ↗
                </a>
              </td>
            </tr>
          </table>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# RENDERER 3 — Cumulative conference tracker
# ──────────────────────────────────────────────────────────────────────────────

def render_tracker(tracker_rows):
    verdict_colors = {
        "Attend":  ("#1a4d2e", "#c6f0d5"),
        "Monitor": ("#6b4000", "#ffeaa0"),
        "Ignore":  ("#3a3a3a", "#e8e8e8"),
    }

    def badge(applies):
        bg, fg = verdict_colors.get(applies, ("#555", "#eee"))
        return (
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'font-size:11px;font-weight:700;letter-spacing:.05em;'
            f'text-transform:uppercase;padding:3px 9px;border-radius:3px;'
            f'white-space:nowrap;">{esc(applies)}</span>'
        )

    rows_html = ""
    for row in tracker_rows:
        region  = row.get("region")  or infer_region(row.get("location", ""))
        month   = row.get("month")   or extract_month(row.get("date", ""), row.get("issue_date", ""))
        applies = row.get("applies", "")
        tag     = row.get("tag", "")
        rows_html += f"""
        <tr data-verdict="{esc(applies)}" data-harm="{esc(tag)}" data-region="{esc(region)}" data-month="{esc(month)}">
          <td style="white-space:nowrap;font-variant-numeric:tabular-nums;">{esc(row.get('issue_date',''))}</td>
          <td style="text-align:center;color:#999;font-variant-numeric:tabular-nums;">{row.get('issue_index','')}</td>
          <td>{badge(applies)}</td>
          <td><strong>{esc(row.get('title',''))}</strong></td>
          <td><span style="background:#ede8db;color:#5a5040;font-size:11px;font-weight:600;padding:2px 8px;border-radius:3px;white-space:nowrap;">{esc(tag)}</span></td>
          <td style="white-space:nowrap;">{esc(row.get('date',''))}</td>
          <td style="white-space:nowrap;">{esc(region)}</td>
          <td>{esc(row.get('location',''))}</td>
          <td>{esc(row.get('host',''))}</td>
          <td style="font-size:13px;max-width:260px;">{esc(row.get('why',''))}</td>
          <td><a href="{esc(row.get('source','#'))}" target="_blank" rel="noopener"
               style="color:#7a3c0f;font-weight:600;white-space:nowrap;text-decoration:none;">Source ↗</a></td>
        </tr>"""

    harm_areas = sorted({row.get("tag","") for row in tracker_rows if row.get("tag")})
    months     = sorted({
        row.get("month") or extract_month(row.get("date",""), row.get("issue_date",""))
        for row in tracker_rows
    } - {""})

    harm_options  = ''.join(f'<option value="{esc(h)}">{esc(h)}</option>' for h in harm_areas)
    month_options = ''.join(f'<option value="{esc(m)}">{esc(format_month(m))}</option>' for m in months)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Morning Edition · Conference Tracker</title>
  <style>
    *, *::before, *::after {{ box-sizing:border-box; }}
    body {{ margin:0; padding:0; font-family:Arial,Helvetica,sans-serif; font-size:14px; background:#f5f2ec; color:#1a1a1a; line-height:1.4; }}
    .sr-only {{ position:absolute; width:1px; height:1px; padding:0; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }}

    /* Header — subdued, functional */
    header {{ background:#2a2218; padding:20px 28px; display:flex; align-items:baseline; gap:16px; }}
    header h1 {{ font-family:Georgia,serif; font-size:22px; color:#e8e0d0; margin:0; font-weight:normal; letter-spacing:-.02em; }}
    header p {{ font-size:11px; color:#7a6d56; margin:0; letter-spacing:.1em; text-transform:uppercase; }}

    /* Filter toolbar */
    .toolbar {{ display:flex; flex-wrap:wrap; gap:10px 20px; align-items:flex-end; padding:14px 28px; background:#edeae2; border-bottom:1px solid #d8d3c8; }}
    .filter-group {{ display:flex; flex-direction:column; gap:4px; }}
    .filter-group label {{ font-size:11px; font-weight:700; color:#6a6050; letter-spacing:.08em; text-transform:uppercase; }}
    .filter-group select,
    .filter-group input {{ font-size:13px; padding:5px 9px; border:1px solid #c4bfb2; border-radius:3px; background:#fff; color:#1a1a1a; min-width:130px; }}
    .filter-group input {{ min-width:200px; }}
    .filter-group select:focus,
    .filter-group input:focus {{ outline:2px solid #7a5c30; outline-offset:1px; border-color:#7a5c30; }}
    .count {{ font-size:12px; color:#7a7060; align-self:flex-end; padding-bottom:6px; margin-left:auto; }}

    /* Table */
    .wrap {{ overflow-x:auto; padding:16px 28px 48px; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #ddd8ce; border-radius:3px; overflow:hidden; }}
    caption {{ caption-side:bottom; font-size:11px; color:#999; padding:8px 0 0; text-align:left; }}
    thead tr {{ background:#2a2218; }}
    thead th {{ padding:10px 13px; text-align:left; font-size:11px; letter-spacing:.09em; text-transform:uppercase; font-weight:700; color:#c8b89a; white-space:nowrap; cursor:pointer; user-select:none; border:none; }}
    thead th:focus {{ outline:2px solid #c8a96e; outline-offset:-2px; }}
    thead th[aria-sort="ascending"]::after  {{ content:" ↑"; opacity:.6; }}
    thead th[aria-sort="descending"]::after {{ content:" ↓"; opacity:.6; }}
    thead th:not([aria-sort]):hover::after  {{ content:" ↕"; opacity:.3; }}
    tbody tr {{ border-bottom:1px solid #edebe5; }}
    tbody tr:nth-child(even) {{ background:#faf8f4; }}
    tbody tr:hover {{ background:#f2ede3; }}
    tbody td {{ padding:10px 13px; font-size:13px; vertical-align:top; }}
    .hidden {{ display:none !important; }}
  </style>
</head>
<body>
  <header>
    <h1>Morning Edition</h1>
    <p>Conference tracker &nbsp;·&nbsp; AI harm · safety · security · policy</p>
  </header>

  <div class="toolbar" role="search" aria-label="Filter conferences">
    <div class="filter-group">
      <label for="f-verdict">Verdict</label>
      <select id="f-verdict" onchange="applyFilters()">
        <option value="">All verdicts</option>
        <option>Attend</option>
        <option>Monitor</option>
        <option>Ignore</option>
      </select>
    </div>
    <div class="filter-group">
      <label for="f-harm">Harm area</label>
      <select id="f-harm" onchange="applyFilters()">
        <option value="">All harm areas</option>
        {harm_options}
      </select>
    </div>
    <div class="filter-group">
      <label for="f-region">Region</label>
      <select id="f-region" onchange="applyFilters()">
        <option value="">All regions</option>
        <option>Africa</option>
        <option>Asia</option>
        <option>Central America</option>
        <option>Europe</option>
        <option>Latin America</option>
        <option>Middle East</option>
        <option>North America</option>
        <option>Oceania</option>
        <option>Online / Virtual</option>
        <option>Other</option>
      </select>
    </div>
    <div class="filter-group">
      <label for="f-month">Month</label>
      <select id="f-month" onchange="applyFilters()">
        <option value="">All months</option>
        {month_options}
      </select>
    </div>
    <div class="filter-group">
      <label for="f-search">Search</label>
      <input id="f-search" type="search" placeholder="Title, host, location…" oninput="applyFilters()">
    </div>
    <span class="count" id="row-count" role="status" aria-live="polite"></span>
  </div>

  <div class="wrap">
    <table id="tracker-table" aria-label="Conference tracker">
      <thead>
        <tr>
          <th scope="col" tabindex="0" onclick="sortBy(0)" onkeydown="if(event.key==='Enter')sortBy(0)">Issue</th>
          <th scope="col" tabindex="0" onclick="sortBy(1)" onkeydown="if(event.key==='Enter')sortBy(1)">#</th>
          <th scope="col" tabindex="0" onclick="sortBy(2)" onkeydown="if(event.key==='Enter')sortBy(2)">Verdict</th>
          <th scope="col" tabindex="0" onclick="sortBy(3)" onkeydown="if(event.key==='Enter')sortBy(3)">Conference</th>
          <th scope="col" tabindex="0" onclick="sortBy(4)" onkeydown="if(event.key==='Enter')sortBy(4)">Harm area</th>
          <th scope="col" tabindex="0" onclick="sortBy(5)" onkeydown="if(event.key==='Enter')sortBy(5)">When</th>
          <th scope="col" tabindex="0" onclick="sortBy(6)" onkeydown="if(event.key==='Enter')sortBy(6)">Region</th>
          <th scope="col" tabindex="0" onclick="sortBy(7)" onkeydown="if(event.key==='Enter')sortBy(7)">Location</th>
          <th scope="col" tabindex="0" onclick="sortBy(8)" onkeydown="if(event.key==='Enter')sortBy(8)">Host</th>
          <th scope="col" tabindex="0" onclick="sortBy(9)" onkeydown="if(event.key==='Enter')sortBy(9)">Why it matters</th>
          <th scope="col">Source</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
      <caption>Click any column header to sort. Use filters above to narrow results.</caption>
    </table>
  </div>

  <script>
    function applyFilters() {{
      const verdict = document.getElementById('f-verdict').value;
      const harm    = document.getElementById('f-harm').value;
      const region  = document.getElementById('f-region').value;
      const month   = document.getElementById('f-month').value;
      const search  = document.getElementById('f-search').value.toLowerCase();
      let visible = 0;
      document.querySelectorAll('#tracker-table tbody tr').forEach(row => {{
        const d = row.dataset;
        const show = (!verdict || d.verdict === verdict)
                  && (!harm    || d.harm    === harm)
                  && (!region  || d.region  === region)
                  && (!month   || d.month   === month)
                  && (!search  || row.textContent.toLowerCase().includes(search));
        row.classList.toggle('hidden', !show);
        if (show) visible++;
      }});
      document.getElementById('row-count').textContent =
        visible + ' conference' + (visible !== 1 ? 's' : '');
    }}

    let sortCol = -1, sortDir = 1;
    function sortBy(col) {{
      const table   = document.getElementById('tracker-table');
      const headers = table.querySelectorAll('thead th');
      headers.forEach(h => h.removeAttribute('aria-sort'));
      if (sortCol === col) {{ sortDir *= -1; }} else {{ sortDir = 1; sortCol = col; }}
      headers[col].setAttribute('aria-sort', sortDir === 1 ? 'ascending' : 'descending');
      const tbody = table.querySelector('tbody');
      const rows  = [...tbody.querySelectorAll('tr')];
      rows.sort((a, b) => {{
        const at = a.querySelectorAll('td')[col].textContent.trim();
        const bt = b.querySelectorAll('td')[col].textContent.trim();
        return at.localeCompare(bt, undefined, {{numeric:true}}) * sortDir;
      }});
      rows.forEach(r => tbody.appendChild(r));
      applyFilters();
    }}

    applyFilters();
  </script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# REDIRECT INDEX
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    events = load_events()
    issue_date = datetime.now().strftime("%Y-%m-%d")
    mag_url = magazine_url(issue_date)
    t_url   = tracker_page_url()

    # 1. Full magazine
    issue_file = ISSUES_DIR / f"{issue_date}.html"
    issue_file.write_text(render_issue(issue_date, events, t_url), encoding="utf-8")
    print(f"Magazine  → {issue_file}")

    # 2. Email digest
    digest_file = ISSUES_DIR / f"{issue_date}-digest.html"
    digest_file.write_text(render_email_digest(issue_date, events, mag_url), encoding="utf-8")
    print(f"Digest    → {digest_file}")

    # 3. Cumulative tracker
    tracker_rows = update_tracker(issue_date, events)
    TRACKER_HTML.write_text(render_tracker(tracker_rows), encoding="utf-8")
    print(f"Tracker   → {TRACKER_HTML}")

    # 4. Root redirect
    INDEX_FILE.write_text(render_latest_index(issue_date), encoding="utf-8")
    print(f"Index     → {INDEX_FILE}")


if __name__ == "__main__":
    main()
