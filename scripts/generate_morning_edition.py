from pathlib import Path
from datetime import datetime
import html
import json
import os

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

    # Events already featured in any previous issue are excluded so the
    # same conference never repeats across issues.
    already_featured: set[str] = set()
    if TRACKER_FILE.exists():
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            tracker = json.load(f)
        already_featured = {row["source"] for row in tracker}

    cleaned = []
    skipped = 0
    for i, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {i} in sample_events.json is not an object")
        source = str(item.get("source", "#"))
        if source in already_featured:
            skipped += 1
            continue
        cleaned.append({
            "title":    str(item.get("title",    "Untitled conference")),
            "date":     str(item.get("date",     "TBC")),
            "location": str(item.get("location", "TBC")),
            "host":     str(item.get("host",     "TBC")),
            "applies":  str(item.get("applies",  "APPLIES")),
            "tag":      str(item.get("tag",      "policy")),
            "angle":    str(item.get("angle",    "AI conference")),
            "why":      str(item.get("why",      "")),
            "watch":    str(item.get("watch",    "")),
            "source":   source,
        })

    if skipped:
        print(f"Dedup: skipped {skipped} event(s) already featured in a previous issue")
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
            tracker.append({"issue_date": issue_date, "issue_index": i, **c})
            existing_sources.add(c["source"])
            added += 1

    # Most-recent issues first
    tracker.sort(key=lambda r: (r["issue_date"], r["issue_index"]), reverse=True)

    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)

    print(f"Tracker: +{added} new, {len(tracker)} total → {TRACKER_FILE}")
    return tracker


def magazine_url(issue_date):
    """Construct the absolute GitHub Pages URL for this issue, or fall back to relative."""
    base = os.environ.get("MORNING_EDITION_PAGES_URL", "").rstrip("/")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        if repo:
            owner, name = repo.split("/", 1)
            base = f"https://{owner}.github.io/{name}"
    if base:
        return f"{base}/issues/{issue_date}.html"
    return f"./issues/{issue_date}.html"


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def esc(value):
    return html.escape(str(value), quote=True)


VERDICT_STYLE = {
    "DIRECTLY APPLIES": "background:#1a3d1a;color:#d4f5d4;",
    "APPLIES":          "background:#5c3800;color:#ffe8a0;",
    "MONITOR":          "background:#2e2e2e;color:#d8d8d8;",
}

def verdict_badge(applies):
    style = VERDICT_STYLE.get(applies, "background:#444;color:#fff;")
    return (
        f'<span style="display:inline-block;{style}'
        f'font-size:10px;font-weight:900;letter-spacing:.1em;'
        f'text-transform:uppercase;padding:3px 8px;border-radius:999px;'
        f'font-family:Arial,Helvetica,sans-serif;">{esc(applies)}</span>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# RENDERER 1 — Full magazine (existing)
# ──────────────────────────────────────────────────────────────────────────────

def render_issue(issue_date, conferences):
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

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Morning Edition · {issue_date}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ margin:0; font-family:Arial,sans-serif; background:#f7f3ea; color:#111111; }}
    .cover {{ min-height:100vh; display:grid; grid-template-columns:1.15fr .85fr; gap:26px; padding:48px 32px 34px; background:linear-gradient(160deg,#f7f1e7 0%,#efe4c9 55%,#e5d5b6 100%); }}
    .cover h1 {{ font-family:Georgia,serif; font-size:110px; line-height:.9; letter-spacing:-.07em; margin:0; max-width:8ch; }}
    .kicker {{ font-size:20px; font-weight:900; letter-spacing:.12em; text-transform:uppercase; margin-bottom:16px; }}
    .deck {{ margin-top:22px; font-size:28px; line-height:1.2; max-width:18ch; }}
    .index {{ margin-top:26px; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .index-item {{ border-top:2px solid #111111; padding-top:10px; font-size:20px; line-height:1.2; }}
    .signal-col {{ display:grid; gap:14px; align-content:start; }}
    .signal {{ border:1px solid rgba(17,17,17,.16); border-radius:24px; background:rgba(255,255,255,.38); padding:18px; font-size:20px; line-height:1.3; }}
    .signal strong {{ display:block; font-size:21px; margin-bottom:8px; }}
    @media (max-width:1050px) {{ .cover {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <section class="cover">
    <div>
      <div class="kicker">AI harm · safety · security · policy</div>
      <h1>Ten conferences worth your attention now.</h1>
      <div class="deck">A policy-leaning morning magazine focused on conferences that matter for AI safety, security, governance, law, and multilateral signal.</div>
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
# RENDERER 3 — Cumulative tracker (SharePoint-embeddable)
# ──────────────────────────────────────────────────────────────────────────────

def render_tracker(tracker_rows):
    verdict_colors = {
        "DIRECTLY APPLIES": ("#1a3d1a", "#d4f5d4"),
        "APPLIES":          ("#5c3800", "#ffe8a0"),
        "MONITOR":          ("#2e2e2e", "#d8d8d8"),
    }

    def badge(applies):
        bg, fg = verdict_colors.get(applies, ("#444", "#fff"))
        return (
            f'<span style="background:{bg};color:{fg};'
            f'font-size:10px;font-weight:900;letter-spacing:.08em;'
            f'text-transform:uppercase;padding:2px 7px;border-radius:999px;'
            f'white-space:nowrap;">{esc(applies)}</span>'
        )

    rows_html = ""
    for row in tracker_rows:
        rows_html += f"""
        <tr>
          <td style="white-space:nowrap;">{esc(row.get('issue_date',''))}</td>
          <td style="text-align:center;color:#aaa;">{row.get('issue_index','')}</td>
          <td>{badge(row.get('applies',''))}</td>
          <td><strong>{esc(row.get('title',''))}</strong></td>
          <td><span style="background:#f0ece2;color:#666;font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;white-space:nowrap;">{esc(row.get('tag',''))}</span></td>
          <td style="white-space:nowrap;">{esc(row.get('date',''))}</td>
          <td>{esc(row.get('location',''))}</td>
          <td>{esc(row.get('host',''))}</td>
          <td style="font-size:13px;max-width:260px;">{esc(row.get('why',''))}</td>
          <td><a href="{esc(row.get('source','#'))}" target="_blank" rel="noopener" style="color:#8b4513;font-weight:700;white-space:nowrap;">Source ↗</a></td>
        </tr>"""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Morning Edition · Conference Tracker</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin:0; padding:0; font-family:Arial,Helvetica,sans-serif; background:#f0ece2; color:#111; }}
    header {{ background:linear-gradient(150deg,#1a1a1a 0%,#2e2416 100%); padding:28px 32px; }}
    header h1 {{ font-family:Georgia,serif; font-size:32px; color:#f5efe4; margin:0 0 4px; letter-spacing:-.03em; }}
    header p {{ font-size:12px; color:#9a8060; margin:0; letter-spacing:.1em; text-transform:uppercase; }}
    .toolbar {{ padding:14px 32px; background:#e8e2d4; border-bottom:1px solid #d4cfc0; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
    .toolbar label {{ font-size:12px; font-weight:700; color:#666; letter-spacing:.08em; text-transform:uppercase; }}
    .toolbar select {{ font-size:13px; padding:5px 10px; border:1px solid #c8c0a8; border-radius:3px; background:#fff; color:#333; }}
    .toolbar input {{ font-size:13px; padding:5px 10px; border:1px solid #c8c0a8; border-radius:3px; background:#fff; color:#333; width:220px; }}
    .count {{ margin-left:auto; font-size:12px; color:#888; }}
    .wrap {{ overflow-x:auto; padding:0 32px 40px; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; background:#fff; border-radius:4px; overflow:hidden; border:1px solid #ddd8cc; }}
    thead tr {{ background:#1a1a1a; color:#c8b89a; }}
    thead th {{ padding:11px 14px; text-align:left; font-size:11px; letter-spacing:.1em; text-transform:uppercase; font-weight:700; white-space:nowrap; cursor:pointer; user-select:none; }}
    thead th:hover {{ background:#2e2416; }}
    thead th.sort-asc::after {{ content:" ↑"; opacity:.7; }}
    thead th.sort-desc::after {{ content:" ↓"; opacity:.7; }}
    tbody tr {{ border-bottom:1px solid #f0ece2; }}
    tbody tr:hover {{ background:#faf8f3; }}
    tbody td {{ padding:11px 14px; font-size:13px; vertical-align:top; line-height:1.4; }}
    .hidden {{ display:none !important; }}
  </style>
</head>
<body>
  <header>
    <h1>Morning Edition</h1>
    <p>Conference tracker &nbsp;·&nbsp; AI harm · safety · security · policy</p>
  </header>

  <div class="toolbar">
    <label for="f-verdict">Verdict</label>
    <select id="f-verdict" onchange="applyFilters()">
      <option value="">All</option>
      <option>DIRECTLY APPLIES</option>
      <option>APPLIES</option>
      <option>MONITOR</option>
    </select>

    <label for="f-tag">Domain</label>
    <select id="f-tag" onchange="applyFilters()">
      <option value="">All</option>
    </select>

    <input id="f-search" type="search" placeholder="Search title, host, location…" oninput="applyFilters()">

    <span class="count" id="row-count"></span>
  </div>

  <div class="wrap">
    <table id="tracker-table">
      <thead>
        <tr>
          <th onclick="sortBy(0)">Issue</th>
          <th onclick="sortBy(1)">#</th>
          <th onclick="sortBy(2)">Verdict</th>
          <th onclick="sortBy(3)">Conference</th>
          <th onclick="sortBy(4)">Domain</th>
          <th onclick="sortBy(5)">When</th>
          <th onclick="sortBy(6)">Where</th>
          <th onclick="sortBy(7)">Host</th>
          <th onclick="sortBy(8)">Why it matters</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <script>
    // Populate domain filter from live table data
    (function() {{
      const tags = new Set();
      document.querySelectorAll('#tracker-table tbody tr td:nth-child(5) span').forEach(el => tags.add(el.textContent.trim()));
      const sel = document.getElementById('f-tag');
      [...tags].sort().forEach(t => {{ const o = document.createElement('option'); o.textContent = t; sel.appendChild(o); }});
    }})();

    function applyFilters() {{
      const verdict = document.getElementById('f-verdict').value.toLowerCase();
      const tag     = document.getElementById('f-tag').value.toLowerCase();
      const search  = document.getElementById('f-search').value.toLowerCase();
      let visible = 0;
      document.querySelectorAll('#tracker-table tbody tr').forEach(row => {{
        const cells = row.querySelectorAll('td');
        const rowVerdict  = cells[2].textContent.trim().toLowerCase();
        const rowTag      = cells[4].textContent.trim().toLowerCase();
        const rowText     = row.textContent.toLowerCase();
        const show = (!verdict || rowVerdict.includes(verdict))
                  && (!tag     || rowTag === tag)
                  && (!search  || rowText.includes(search));
        row.classList.toggle('hidden', !show);
        if (show) visible++;
      }});
      document.getElementById('row-count').textContent = visible + ' conference' + (visible !== 1 ? 's' : '');
    }}

    // Simple column sort
    let sortCol = 0, sortDir = 1;
    function sortBy(col) {{
      const table = document.getElementById('tracker-table');
      const headers = table.querySelectorAll('thead th');
      headers.forEach((h, i) => {{ h.classList.remove('sort-asc','sort-desc'); }});
      if (sortCol === col) {{ sortDir *= -1; }} else {{ sortDir = 1; sortCol = col; }}
      headers[col].classList.add(sortDir === 1 ? 'sort-asc' : 'sort-desc');
      const tbody = table.querySelector('tbody');
      const rows = [...tbody.querySelectorAll('tr')];
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

    # 1. Full magazine
    issue_file = ISSUES_DIR / f"{issue_date}.html"
    issue_file.write_text(render_issue(issue_date, events), encoding="utf-8")
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
