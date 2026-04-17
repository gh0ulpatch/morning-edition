#!/usr/bin/env python3
"""
scrape_events.py — Morning Edition data scraper.

Casts a wide net across four source types looking for any event where AI
intersects with harm, misuse, or exploitation — even if AI isn't in the title.

Sources:
  - WikiCFP     (~30 search queries)
  - RSS feeds   (~25 authoritative feeds)
  - Reddit      (~11 subreddits via public JSON API)
  - Custom sites (~7 think tanks / policy institutions)

Each candidate is scored against four weighted criteria:
  Policy 30% · Technical 25% · Governance 25% · Cross-Sector 20%

Results are tagged, verdict-classified, deduplicated, sorted by score,
and written to data/sample_events.json for generate_morning_edition.py.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    print("[warn] beautifulsoup4 not installed — WikiCFP and custom-site scraping disabled")

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "sample_events.json"

# ──────────────────────────────────────────────────────────────────────────────
# SOURCE CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

WIKICFP_QUERIES: list[str] = [
    "ai safety", "ai governance", "adversarial machine learning",
    "ai ethics", "trustworthy ai", "responsible ai",
    "counter terrorism", "counterterrorism",
    "financial crime", "anti-money laundering", "fraud detection",
    "biosecurity", "biological security", "pandemic preparedness",
    "human rights technology", "digital rights",
    "child protection", "child safety online",
    "election security", "election integrity", "disinformation",
    "nuclear security", "arms control",
    "cybersecurity policy", "cyber governance",
    "surveillance", "privacy law",
    "ai regulation", "ai law",
    "organised crime", "information warfare",
]

RSS_FEEDS: list[str] = [
    # Government / CERT
    "https://www.ncsc.gov.uk/api/1/services/v1/report-rss-feed.xml",
    "https://www.gov.uk/search/news-and-communications.atom?keywords=artificial+intelligence&order=updated-newest",
    "https://www.gov.uk/search/news-and-communications.atom?keywords=AI+safety&order=updated-newest",
    # Law enforcement / international bodies
    "https://www.europol.europa.eu/rss.xml",
    "https://www.interpol.int/rss/News-and-Events",
    # Civil society / rights
    "https://www.eff.org/rss/updates.xml",
    "https://privacyinternational.org/rss.xml",
    # Safety / policy research
    "https://sipri.org/rss.xml",
    "https://oecd.ai/en/feed",
    "https://digital-strategy.ec.europa.eu/en/rss",
    # Academic / preprint
    "http://export.arxiv.org/rss/cs.AI",
    "http://export.arxiv.org/rss/cs.CY",
    "http://export.arxiv.org/rss/cs.CR",
    # Think tanks / institutes
    "https://ainowinstitute.org/feed",
    "https://cset.georgetown.edu/feed/",
    "https://www.governance.ai/feed",
    "https://www.centerforaisafety.org/feed",
    # Child safety
    "https://www.iwf.org.uk/feed/",
]

# (subreddit, keyword_filter_or_None)
# None = include all posts; list = must contain at least one term
SUBREDDITS: list[tuple[str, list[str] | None]] = [
    ("aisafety", None),
    ("AIethics", None),
    ("AIPolicy", None),
    ("MachineLearning", ["conference", "workshop", "summit", "call for papers", "cfp"]),
    ("netsec", ["ai", "machine learning", "conference", "summit"]),
    ("cybersecurity", ["ai", "artificial intelligence", "conference", "summit"]),
    ("privacy", ["ai", "conference", "law", "regulation", "policy"]),
    ("bioinformatics", ["ai", "conference", "summit", "workshop"]),
    ("LegalTech", ["ai", "conference", "regulation"]),
    ("technology", ["ai safety", "ai governance", "ai harm", "ai regulation", "ai policy"]),
    ("artificial", ["safety", "governance", "harm", "policy", "regulation", "crime"]),
]

CUSTOM_SITES: list[dict[str, str]] = [
    {
        "name": "Chatham House",
        "url": "https://www.chathamhouse.org/events",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "RUSI",
        "url": "https://rusi.org/events",
        "event_selector": ".views-row",
        "title_selector": "h3",
        "date_selector": ".field-date",
        "desc_selector": ".field-body",
    },
    {
        "name": "Alan Turing Institute",
        "url": "https://www.turing.ac.uk/events",
        "event_selector": ".event-listing__item",
        "title_selector": "h3",
        "date_selector": ".event-listing__date",
        "desc_selector": ".event-listing__description",
    },
    {
        "name": "Ada Lovelace Institute",
        "url": "https://www.adalovelaceinstitute.org/events/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "CSIS",
        "url": "https://www.csis.org/events",
        "event_selector": ".views-row",
        "title_selector": "h3",
        "date_selector": ".event-date",
        "desc_selector": "p",
    },
    {
        "name": "Brookings",
        "url": "https://www.brookings.edu/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Carnegie Endowment",
        "url": "https://carnegieendowment.org/events",
        "event_selector": ".event-item",
        "title_selector": "h3",
        "date_selector": ".event-date",
        "desc_selector": ".event-summary",
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# SCORING CRITERIA  (Policy 30% · Technical 25% · Governance 25% · Cross-Sector 20%)
# ──────────────────────────────────────────────────────────────────────────────

SCORING_CRITERIA: dict[str, dict[str, Any]] = {
    "policy": {
        "weight": 0.30,
        "keywords": [
            "policy", "legislation", "regulation", "law", "legal", "compliance",
            "directive", "act", "bill", "treaty", "framework", "oversight",
            "enforcement", "regulatory", "rule", "sanction", "statute",
            "parliament", "congress", "senate", "minister",
        ],
    },
    "technical": {
        "weight": 0.25,
        "keywords": [
            "machine learning", "neural", "model", "algorithm", "adversarial",
            "robustness", "vulnerability", "exploit", "attack", "defense",
            "ai system", "deep learning", "llm", "generative", "autonomous",
            "artificial intelligence", "computer vision", "natural language",
            "classifier", "detection", "automation",
        ],
    },
    "governance": {
        "weight": 0.25,
        "keywords": [
            "governance", "accountability", "transparency", "audit", "standards",
            "compliance", "multilateral", "international", "institution",
            " un ", "nato", " eu ", "oecd", "g7", "g20", "council",
            "intergovernmental", "convention", "summit", "dialogue",
        ],
    },
    "cross_sector": {
        "weight": 0.20,
        "keywords": [
            "crime", "trafficking", "terrorism", "exploitation", "disinformation",
            "fraud", "laundering", "nuclear", "biosecurity", "election",
            "surveillance", "military", "weapon", "extremism", "radicaliz",
            "child protection", "csam", "drug", "organised crime", "organized crime",
            "cybercrime", "ransomware", "darknet", "dark web",
        ],
    },
}

# Domain crosswalk — maps broad themes to surface-level keyword signals
DOMAIN_TAGS: dict[str, list[str]] = {
    "Multilateral": [" un ", " itu", "nato", "oecd", "g7", "g20", "multilateral", "treaty", "convention", "intergovernmental"],
    "EU Governance": [" eu ", "european", "gdpr", "ai act", "brussels", "european commission", "eu parliament", "dsa", "dma"],
    "Cybersecurity": ["cyber", " hack", "vulnerability", "malware", "ransomware", "infosec", "cve", "exploit", "intrusion"],
    "Biosecurity": ["biosecurity", "biological", "pandemic", "pathogen", "biorisk", "dual-use research", "gain of function"],
    "Counter-Terrorism": ["terrorism", "extremism", "radicaliz", "counter-terror", "violent extremism", "jihadist", "far-right"],
    "Financial Crime": ["financial crime", "money laundering", "fraud", "aml", "sanctions evasion", "fintech crime", "crypto crime"],
    "Child Safety": ["child", "csam", "minor", "safeguarding", "iwf", "online safety", "grooming", "exploitation"],
    "Election Integrity": ["election", "voting", "democratic", "disinformation", "electoral", "influence operation"],
    "Nuclear & WMD": ["nuclear", " weapon", "arms control", "non-proliferation", "wmd", "cbrn", "chemical weapon", "biological weapon"],
    "AI Safety": ["ai safety", "alignment", "existential risk", "x-risk", "catastrophic risk", "frontier model"],
    "Privacy & Surveillance": ["privacy", "surveillance", "data protection", "biometric", "mass monitoring", "facial recognition"],
    "Drug Trafficking": ["drug traffick", "narcotics", "fentanyl", "darknet market", "organised crime", "cartel"],
}

# Minimum combined score to include a result
SCORE_THRESHOLD = 0.15
# How many events to write to the data file (generator uses top 10)
MAX_EVENTS = 20

# ──────────────────────────────────────────────────────────────────────────────
# SCORING, TAGGING & CLASSIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def score_text(text: str) -> tuple[float, dict[str, float]]:
    """Score text against the four weighted criteria. Returns (total, breakdown)."""
    lower = text.lower()
    breakdown: dict[str, float] = {}
    for name, cfg in SCORING_CRITERIA.items():
        hits = sum(1 for kw in cfg["keywords"] if kw in lower)
        # 5+ keyword hits = full score for that criterion
        raw = min(hits / 5.0, 1.0)
        breakdown[name] = raw * cfg["weight"]
    return sum(breakdown.values()), breakdown


def tag_event(text: str) -> str:
    """Return the best-matching domain tag."""
    lower = text.lower()
    best_tag, best_count = "AI Governance", 0
    for tag, keywords in DOMAIN_TAGS.items():
        count = sum(1 for kw in keywords if kw in lower)
        if count > best_count:
            best_count, best_tag = count, tag
    return best_tag


def classify_verdict(score: float) -> str:
    if score >= 0.55:
        return "DIRECTLY APPLIES"
    if score >= 0.30:
        return "APPLIES"
    return "MONITOR"


def build_angle(tag: str, breakdown: dict[str, float]) -> str:
    """Derive a one-line editorial angle from domain tag and top criterion."""
    top = max(breakdown, key=lambda k: breakdown[k])
    label = {
        "policy": "policy & regulation",
        "technical": "technical AI",
        "governance": "governance & institutions",
        "cross_sector": "cross-sector harm",
    }.get(top, "AI governance")
    return f"{tag} / {label}"


def truncate(text: str, max_chars: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    return text[: cut if cut > 0 else max_chars] + "…"


# ──────────────────────────────────────────────────────────────────────────────
# HTTP HELPER
# ──────────────────────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "MorningEditionBot/1.0 "
        "(automated newsletter scraper; "
        "+https://github.com/gh0ulpatch/morning-edition)"
    )
}


def fetch(url: str, timeout: int = 15) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:
        print(f"  [warn] fetch failed {url}: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE: WikiCFP
# ──────────────────────────────────────────────────────────────────────────────

def scrape_wikicfp() -> list[dict]:
    if not HAS_BS4:
        print("[wikicfp] skipped — beautifulsoup4 not installed")
        return []

    results: list[dict] = []
    seen_urls: set[str] = set()

    for query in WIKICFP_QUERIES:
        time.sleep(1.5)
        encoded = urllib.parse.quote_plus(query)
        url = f"http://www.wikicfp.com/cfp/call?conference={encoded}"
        raw = fetch(url)
        if not raw:
            continue

        try:
            soup = BeautifulSoup(raw, "html.parser")
            # WikiCFP results live in a table; conference rows have a link in col 0
            for row in soup.select("table.contsec tr, table tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                link = cells[0].find("a", href=True)
                if not link:
                    continue

                href = link["href"]
                if not href.startswith("/cfp/"):
                    continue
                conf_url = "http://www.wikicfp.com" + href
                if conf_url in seen_urls:
                    continue
                seen_urls.add(conf_url)

                title = link.get_text(strip=True)
                date_text = cells[1].get_text(strip=True) if len(cells) > 1 else "TBC"
                location = cells[3].get_text(strip=True) if len(cells) > 3 else "TBC"
                full_text = f"{title} {row.get_text(' ')} {query}"

                score, breakdown = score_text(full_text)
                if score < SCORE_THRESHOLD:
                    continue

                tag = tag_event(full_text)
                results.append({
                    "title": title,
                    "date": date_text,
                    "location": location,
                    "host": "TBC",
                    "applies": classify_verdict(score),
                    "tag": tag,
                    "angle": build_angle(tag, breakdown),
                    "why": truncate(title, 180),
                    "watch": "Sourced via WikiCFP — check agenda for AI harm/misuse sessions.",
                    "source": conf_url,
                    "_score": score,
                })
        except Exception as exc:
            print(f"  [wikicfp] parse error (query='{query}'): {exc}")

    print(f"[wikicfp] {len(results)} events from {len(WIKICFP_QUERIES)} queries")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE: RSS feeds
# ──────────────────────────────────────────────────────────────────────────────

def _parse_feed(raw: bytes, feed_url: str) -> list[tuple[str, str, str, str]]:
    """
    Minimal RSS/Atom parser using stdlib xml.etree.ElementTree.
    Returns list of (title, link, summary, published) tuples.
    """
    ATOM = "http://www.w3.org/2005/Atom"
    entries: list[tuple[str, str, str, str]] = []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return entries

    tag = root.tag.lower()

    if "atom" in tag or root.tag == f"{{{ATOM}}}feed":
        # Atom feed
        ns = {"a": ATOM}
        for entry in root.findall("a:entry", ns) or root.findall("{%s}entry" % ATOM):
            title = (entry.findtext("a:title", "", ns) or entry.findtext("{%s}title" % ATOM, "")).strip()
            link_el = entry.find("a:link", ns) or entry.find("{%s}link" % ATOM)
            link = (link_el.get("href", "") if link_el is not None else "").strip()
            summary = (entry.findtext("a:summary", "", ns) or entry.findtext("{%s}summary" % ATOM, "") or
                       entry.findtext("a:content", "", ns) or entry.findtext("{%s}content" % ATOM, "")).strip()
            published = (entry.findtext("a:published", "", ns) or entry.findtext("{%s}published" % ATOM, "") or
                         entry.findtext("a:updated", "", ns) or "TBC").strip()
            if title:
                entries.append((title, link, summary, published[:16]))
    else:
        # RSS 2.0 / RSS 1.0
        items = root.findall(".//item")
        channel = root.find(".//channel")
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            summary = (item.findtext("description") or item.findtext("summary") or "").strip()
            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", " ", summary)
            published = (item.findtext("pubDate") or item.findtext("published") or "TBC").strip()
            if title:
                entries.append((title, link, summary, published[:16]))

    return entries[:30]


def _feed_title(raw: bytes) -> str:
    """Extract channel/feed title from raw XML."""
    ATOM = "http://www.w3.org/2005/Atom"
    try:
        root = ET.fromstring(raw)
        for path in [
            "channel/title",
            f"{{{ATOM}}}title",
            ".//title",
        ]:
            t = root.findtext(path)
            if t:
                return t.strip()
    except ET.ParseError:
        pass
    return ""


def scrape_rss_feeds() -> list[dict]:
    results: list[dict] = []
    seen_urls: set[str] = set()

    for feed_url in RSS_FEEDS:
        time.sleep(0.5)
        raw = fetch(feed_url)
        if not raw:
            continue
        try:
            source_name = _feed_title(raw) or feed_url
            for title, url, summary, published in _parse_feed(raw, feed_url):
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                full_text = f"{title} {summary}"
                score, breakdown = score_text(full_text)
                if score < SCORE_THRESHOLD:
                    continue

                tag = tag_event(full_text)
                results.append({
                    "title": truncate(title, 120),
                    "date": published,
                    "location": "TBC",
                    "host": source_name,
                    "applies": classify_verdict(score),
                    "tag": tag,
                    "angle": build_angle(tag, breakdown),
                    "why": truncate(summary, 200),
                    "watch": f"Sourced from {source_name} — verify dates and AI relevance.",
                    "source": url or feed_url,
                    "_score": score,
                })
        except Exception as exc:
            print(f"  [rss] error parsing {feed_url}: {exc}")

    print(f"[rss] {len(results)} items from {len(RSS_FEEDS)} feeds")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE: Reddit (public JSON API, no auth required)
# ──────────────────────────────────────────────────────────────────────────────

def scrape_reddit() -> list[dict]:
    results: list[dict] = []
    seen_urls: set[str] = set()

    for subreddit, filter_terms in SUBREDDITS:
        time.sleep(2.0)  # Reddit enforces a strict rate limit
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=25"
        raw = fetch(url)
        if not raw:
            continue

        try:
            data = json.loads(raw)
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                p = post.get("data", {})
                title = p.get("title", "")
                selftext = p.get("selftext", "")
                post_url = p.get("url", "")
                permalink = "https://reddit.com" + p.get("permalink", "")

                if post_url in seen_urls:
                    continue
                seen_urls.add(post_url)

                full_text = f"{title} {selftext}".lower()

                # Subreddit-specific keyword gate
                if filter_terms and not any(t in full_text for t in filter_terms):
                    continue

                score, breakdown = score_text(full_text)
                if score < SCORE_THRESHOLD:
                    continue

                tag = tag_event(full_text)
                results.append({
                    "title": truncate(title, 120),
                    "date": "TBC",
                    "location": "TBC",
                    "host": f"r/{subreddit}",
                    "applies": classify_verdict(score),
                    "tag": tag,
                    "angle": build_angle(tag, breakdown),
                    "why": truncate(selftext or title, 200),
                    "watch": f"Surfaced via r/{subreddit} — validate date, location, and event type.",
                    "source": post_url if post_url.startswith("http") else permalink,
                    "_score": score,
                })
        except Exception as exc:
            print(f"  [reddit] error for r/{subreddit}: {exc}")

    print(f"[reddit] {len(results)} posts from {len(SUBREDDITS)} subreddits")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# SOURCE: Custom site scraping (think tanks / policy institutions)
# ──────────────────────────────────────────────────────────────────────────────

def scrape_custom_sites() -> list[dict]:
    if not HAS_BS4:
        print("[custom] skipped — beautifulsoup4 not installed")
        return []

    results: list[dict] = []
    seen_titles: set[str] = set()

    for site in CUSTOM_SITES:
        time.sleep(2.0)
        raw = fetch(site["url"])
        if not raw:
            continue

        try:
            soup = BeautifulSoup(raw, "html.parser")

            # Try the configured selector first, then fall back to generic patterns
            events = soup.select(site["event_selector"])
            if not events:
                events = soup.find_all(
                    ["article", "li"],
                    class_=re.compile(r"event|item|card|listing", re.I),
                )

            for event in events[:20]:
                title_el = event.select_one(site["title_selector"]) or event.find(["h2", "h3", "h4"])
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                date_el = event.select_one(site["date_selector"]) or event.find("time")
                date_text = date_el.get_text(strip=True) if date_el else "TBC"

                desc_el = event.select_one(site["desc_selector"]) or event.find("p")
                desc_text = desc_el.get_text(strip=True) if desc_el else ""

                link_el = event.find("a", href=True)
                href = link_el["href"] if link_el else ""
                if href and not href.startswith("http"):
                    base = urllib.parse.urlparse(site["url"])
                    href = f"{base.scheme}://{base.netloc}{href}"

                full_text = f"{title} {desc_text}"
                score, breakdown = score_text(full_text)
                if score < SCORE_THRESHOLD:
                    continue

                tag = tag_event(full_text)
                results.append({
                    "title": truncate(title, 120),
                    "date": date_text,
                    "location": "TBC",
                    "host": site["name"],
                    "applies": classify_verdict(score),
                    "tag": tag,
                    "angle": build_angle(tag, breakdown),
                    "why": truncate(desc_text or title, 200),
                    "watch": f"Event from {site['name']} — check agenda for AI harm content.",
                    "source": href or site["url"],
                    "_score": score,
                })
        except Exception as exc:
            print(f"  [custom] error scraping {site['name']}: {exc}")

    print(f"[custom] {len(results)} events from {len(CUSTOM_SITES)} sites")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION
# ──────────────────────────────────────────────────────────────────────────────

def _normalise(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:40]


def deduplicate(events: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for ev in events:
        key = _normalise(ev["title"])
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Morning Edition scraper starting…\n")

    all_events: list[dict] = []
    all_events.extend(scrape_wikicfp())
    all_events.extend(scrape_rss_feeds())
    all_events.extend(scrape_reddit())
    all_events.extend(scrape_custom_sites())

    print(f"\nRaw results before dedup: {len(all_events)}")
    all_events = deduplicate(all_events)
    print(f"After dedup:               {len(all_events)}")

    all_events.sort(key=lambda e: e.get("_score", 0), reverse=True)
    all_events = all_events[:MAX_EVENTS]

    for ev in all_events:
        ev.pop("_score", None)

    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(all_events, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(all_events)} events → {DATA_FILE}")


if __name__ == "__main__":
    main()
