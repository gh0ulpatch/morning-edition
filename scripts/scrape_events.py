#!/usr/bin/env python3
"""
scrape_events.py — Morning Edition data scraper.

Casts a wide net across three source types looking for any event where AI
intersects with harm, misuse, or exploitation — even if AI isn't in the title.

Sources:
  - WikiCFP     (~30 search queries + targeted topic RSS feeds)
  - RSS feeds   (~20 authoritative feeds)
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
    # AI safety & governance
    "ai safety", "ai governance", "adversarial machine learning",
    "ai ethics", "trustworthy ai", "responsible ai",
    "ai accountability", "algorithmic accountability", "ai regulation", "ai law",
    "ai risk", "ai alignment", "frontier ai",
    # Policy & digital rights
    "digital policy", "tech policy", "data governance", "platform governance",
    "digital rights", "human rights technology", "digital governance",
    "online safety", "internet governance",
    # Security
    "counter terrorism", "counterterrorism", "information warfare",
    "cybersecurity policy", "cyber governance",
    "nuclear security", "arms control",
    "election security", "election integrity", "disinformation", "misinformation",
    # Crime & harm
    "financial crime", "anti-money laundering", "fraud detection",
    "organised crime", "child protection", "child safety online",
    # Health & bio
    "biosecurity", "biological security", "pandemic preparedness",
    # Surveillance & privacy
    "surveillance", "privacy law",
    # Trust & content
    "trust and safety", "content moderation", "platform safety",
    "online harms", "harmful content", "hate speech",
]

RSS_FEEDS: list[str] = [
    # UK government
    "https://www.ncsc.gov.uk/api/1/services/v1/report-rss-feed.xml",
    "https://www.gov.uk/search/news-and-communications.atom?keywords=artificial+intelligence&order=updated-newest",
    "https://www.gov.uk/search/news-and-communications.atom?keywords=AI+safety&order=updated-newest",
    "https://www.gov.uk/search/news-and-communications.atom?keywords=AI+regulation&order=updated-newest",
    # US government
    "https://www.nist.gov/news-events/news/rss.xml",
    "https://www.ftc.gov/feeds/press-release.xml",
    # EU institutions
    "https://digital-strategy.ec.europa.eu/en/rss",
    "https://www.europarl.europa.eu/rss/doc/top-stories/en.xml",
    # Law enforcement / international bodies
    "https://www.europol.europa.eu/rss.xml",
    "https://www.interpol.int/rss/News-and-Events",
    # Multilateral
    "https://oecd.ai/en/feed",
    "https://news.itu.int/feed/",
    "https://www.un.org/en/rss.xml",
    # Civil society / rights
    "https://www.eff.org/rss/updates.xml",
    "https://privacyinternational.org/rss.xml",
    "https://cdt.org/feed/",
    # Safety / policy research
    "https://sipri.org/rss.xml",
    "https://futureoflife.org/feed/",
    "https://partnershiponai.org/feed/",
    # Academic / preprint
    "http://export.arxiv.org/rss/cs.AI",
    "http://export.arxiv.org/rss/cs.CY",
    "http://export.arxiv.org/rss/cs.CR",
    # Think tanks / institutes
    "https://ainowinstitute.org/feed",
    "https://cset.georgetown.edu/feed/",
    "https://www.governance.ai/feed",
    "https://www.centerforaisafety.org/feed",
    "https://hai.stanford.edu/news/feed",
    "https://lcfi.ac.uk/feed/",
    # Child safety
    "https://www.iwf.org.uk/feed/",
    # Trust & safety
    "https://www.tspa.org/feed/",
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
    {
        "name": "TrustCon / TSPA",
        "url": "https://www.tspa.org/programs/trustcon/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Stanford HAI",
        "url": "https://hai.stanford.edu/events",
        "event_selector": ".event-card",
        "title_selector": "h3",
        "date_selector": ".date",
        "desc_selector": "p",
    },
    {
        "name": "Oxford Internet Institute",
        "url": "https://www.oii.ox.ac.uk/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Future of Life Institute",
        "url": "https://futureoflife.org/programs/events/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Partnership on AI",
        "url": "https://partnershiponai.org/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Council of Europe AI",
        "url": "https://www.coe.int/en/web/artificial-intelligence/events-and-activities",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "ITU AI for Good",
        "url": "https://aiforgood.itu.int/events/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "NIST AI",
        "url": "https://www.nist.gov/artificial-intelligence",
        "event_selector": ".views-row",
        "title_selector": "h3",
        "date_selector": ".date-display-single",
        "desc_selector": "p",
    },
    {
        "name": "Leverhulme CFI",
        "url": "https://lcfi.ac.uk/events/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "UK AI Safety Institute",
        "url": "https://www.gov.uk/government/organisations/ai-safety-institute/about",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Global Partnership on AI",
        "url": "https://gpai.ai/events/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "FAccT Conference",
        "url": "https://facctconference.org/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    # ── Multilateral / intergovernmental event pages ─────────────────────────
    {
        "name": "NATO Events",
        "url": "https://www.nato.int/cps/en/natohq/events.htm",
        "event_selector": ".events-listing li",
        "title_selector": "a",
        "date_selector": ".date",
        "desc_selector": "p",
    },
    {
        "name": "OECD Events",
        "url": "https://www.oecd.org/en/about/events.html",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "WEF Events",
        "url": "https://www.weforum.org/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "OSCE Events",
        "url": "https://www.osce.org/calendar",
        "event_selector": ".event-item",
        "title_selector": "h3",
        "date_selector": ".date",
        "desc_selector": "p",
    },
    {
        "name": "World Bank Events",
        "url": "https://www.worldbank.org/en/events",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "IMF Seminars",
        "url": "https://www.imf.org/en/News/Seminars",
        "event_selector": ".news-item",
        "title_selector": "h3",
        "date_selector": ".date",
        "desc_selector": "p",
    },
    {
        "name": "UN Events",
        "url": "https://www.un.org/en/events",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "GPAI Summit",
        "url": "https://gpai.ai/projects/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    # ── AI company event pages ───────────────────────────────────────────────
    {
        "name": "OpenAI Events",
        "url": "https://openai.com/events",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Anthropic Events",
        "url": "https://www.anthropic.com/events",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Google DeepMind Events",
        "url": "https://deepmind.google/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Microsoft AI Events",
        "url": "https://www.microsoft.com/en-us/ai/events",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Meta AI Research",
        "url": "https://ai.meta.com/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    # ── UK conference venues ─────────────────────────────────────────────────
    {
        "name": "ExCeL London",
        "url": "https://www.excel.london/organiser/events",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "QEII Centre",
        "url": "https://qeiicentre.london/events/",
        "event_selector": "article",
        "title_selector": "h2",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "ICC Birmingham",
        "url": "https://www.theicc.co.uk/whats-on/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Edinburgh ICC",
        "url": "https://www.eicc.co.uk/events/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
    },
    {
        "name": "Manchester Central",
        "url": "https://manchestercentral.co.uk/whats-on/",
        "event_selector": "article",
        "title_selector": "h3",
        "date_selector": "time",
        "desc_selector": "p",
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
            "trust and safety", "content moderation", "platform safety",
            "online harms", "harmful content", "integrity",
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
    "Trust & Safety": ["trust and safety", "content moderation", "platform safety", "online harms", "harmful content", "tspa", "trustcon"],
}

# Minimum combined score to include a result
SCORE_THRESHOLD = 0.15

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
    if score >= 0.30:
        return "Attend"
    if score >= 0.15:
        return "Monitor"
    return "Ignore"


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
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            summary = (item.findtext("description") or item.findtext("summary") or "").strip()
            # Strip HTML tags from summary
            summary = re.sub(r"<[^>]+>", " ", summary)
            published = (item.findtext("pubDate") or item.findtext("published") or "TBC").strip()
            if title:
                # Strip arXiv boilerplate prefix before storing
                summary = re.sub(
                    r'^arXiv:\S+\s+Announce\s+Type:\s+\w+\s+Abstract:\s*',
                    '', summary, flags=re.IGNORECASE).strip()
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


# ──────────────────────────────────────────────────────────────────────────────
# TRUSTED SOURCE ALLOWLIST
# Events from these domains bypass the score threshold but still pass through
# _is_event_like() — so news articles are still filtered out.
# ──────────────────────────────────────────────────────────────────────────────

_TRUSTED_DOMAINS: set[str] = {
    # Major AI companies
    "openai.com", "anthropic.com", "deepmind.com", "ai.google", "google.com",
    "microsoft.com", "meta.com", "meta.ai", "mistral.ai", "cohere.com", "xai.com",
    "inflection.ai", "stability.ai", "huggingface.co",
    # UK government
    "gov.uk", "ncsc.gov.uk", "ico.org.uk",
    # US government
    "nist.gov", "whitehouse.gov", "ftc.gov", "dhs.gov", "cisa.gov", "state.gov",
    # EU institutions
    "europa.eu", "europarl.europa.eu",
    # Multilateral & intergovernmental
    "un.org", "itu.int", "oecd.org", "nato.int", "weforum.org",
    "unesco.org", "coe.int", "gpai.ai", "osce.org",
    "worldbank.org", "imf.org", "interpol.int",
    # Leading AI safety & policy orgs
    "aisi.gov.uk", "futureoflife.org", "safe.ai",
    "partnershiponai.org", "hai.stanford.edu",
    "alignmentforum.org", "lesswrong.com",
    # UK conference venues — scrape all events, score filters relevance
    "excel.london", "qeiicentre.london", "theicc.co.uk",
    "eicc.co.uk", "manchestercentral.co.uk",
}


def _is_trusted(url: str, host: str = "") -> bool:
    """Return True if the source is a major AI player, government body, or multilateral org."""
    combined = f"{url} {host}".lower()
    return any(domain in combined for domain in _TRUSTED_DOMAINS)


# Keywords that suggest an item is actually a conference/event rather than a news article.
# ALL items pass through this gate — trusted sources are not exempt.
_EVENT_TERMS = {
    "conference", "summit", "workshop", "forum", "symposium", "congress",
    "roundtable", "convening", "seminar", "webinar", "colloquium",
    "call for papers", "cfp", "call for submissions", "call for abstracts",
    "annual meeting", "convention", "expo", "conclave", "dialogue",
    "side event", "high-level meeting", "ministerial", "assembly",
    "trustcon",
    # Multilateral / policy terms
    "expert meeting", "expert group", "policy dialogue", "high-level event",
    "intergovernmental", "plenary", "working group", "technical meeting",
    "ministerial meeting", "general assembly", "special session",
    # Venue / event signals
    "register now", "registration open", "register here", "sign up",
    "save the date", "call for participation", "open to", "join us",
    "hosted by", "co-hosted", "taking place", "will be held",
}

# Feeds that are already conference-specific — bypass the event gate
_CONFERENCE_FEEDS = {
    "http://www.wikicfp.com",
    "https://www.usenix.org",
}

def _is_event_like(title: str, summary: str, feed_url: str) -> bool:
    """Return True if the item looks like a genuine event/conference listing."""
    if any(feed_url.startswith(prefix) for prefix in _CONFERENCE_FEEDS):
        return True
    text = f"{title} {summary}".lower()
    return any(term in text for term in _EVENT_TERMS)


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

                trusted = _is_trusted(url, source_name)

                if not _is_event_like(title, summary, feed_url):
                    continue

                full_text = f"{title} {summary}"
                score, breakdown = score_text(full_text)
                if not trusted and score < SCORE_THRESHOLD:
                    continue

                applies = classify_verdict(score)
                if trusted and applies == "Ignore":
                    applies = "Monitor"

                tag = tag_event(full_text)
                results.append({
                    "title": truncate(title, 120),
                    "date": published,
                    "location": "TBC",
                    "host": source_name,
                    "applies": applies,
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
                trusted = _is_trusted(href or site["url"], site["name"])
                if not trusted and score < SCORE_THRESHOLD:
                    continue

                applies = classify_verdict(score)
                if trusted and applies == "Ignore":
                    applies = "Monitor"

                tag = tag_event(full_text)
                results.append({
                    "title": truncate(title, 120),
                    "date": date_text,
                    "location": "TBC",
                    "host": site["name"],
                    "applies": applies,
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
# AI ENRICHMENT
# ──────────────────────────────────────────────────────────────────────────────

_BOILERPLATE_WHY = re.compile(
    r'^(arXiv:|Sourced (via|from)\s)',
    re.IGNORECASE,
)
_BOILERPLATE_WATCH = re.compile(
    r'^Sourced (via|from)\s+.*?—\s*(verify dates|check agenda)',
    re.IGNORECASE,
)


def _needs_enrichment(ev: dict) -> bool:
    return bool(
        _BOILERPLATE_WHY.match(ev.get("why", ""))
        or _BOILERPLATE_WATCH.match(ev.get("watch", ""))
    )


def _enrich_with_ai(events: list[dict]) -> list[dict]:
    """Replace boilerplate why/watch fields with AI editorial summaries."""
    import os
    try:
        import anthropic
    except ImportError:
        print("[enrich] skipped — anthropic package not installed")
        return events

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[enrich] skipped — ANTHROPIC_API_KEY not set")
        return events

    to_enrich = [(i, ev) for i, ev in enumerate(events) if _needs_enrichment(ev)]
    if not to_enrich:
        print("[enrich] no events need enrichment")
        return events

    print(f"[enrich] enriching {len(to_enrich)} events with AI summaries…")

    items_text = "\n\n".join(
        f"EVENT {idx + 1}:\nTitle: {ev['title']}\nRaw summary: {ev['why']}\n"
        f"Source: {ev['source']}\nTag: {ev['tag']}"
        for idx, (_, ev) in enumerate(to_enrich)
    )

    system_prompt = (
        "You are an editorial analyst for Morning Edition, a daily briefing on AI harm, "
        "safety, security, and governance read by senior UK government officials and policy "
        "analysts. For each event, write:\n"
        "1. \"why\": 1-2 sentences explaining why this matters for AI harm/safety/governance "
        "professionals. Be concrete about the risk or policy angle. No jargon.\n"
        "2. \"watch\": 1 sentence with a specific action or caveat — what to verify, monitor, "
        "or follow up on. Start with an action verb.\n\n"
        "Respond with a JSON array ONLY — no prose, no markdown fences. "
        "Each element: {\"why\": \"...\", \"watch\": \"...\"}. "
        "Array length must equal the number of EVENT blocks."
    )

    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": items_text}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        enriched = json.loads(raw)

        result = list(events)
        for idx, (orig_i, _) in enumerate(to_enrich):
            if idx < len(enriched):
                result[orig_i] = dict(result[orig_i])
                result[orig_i]["why"] = enriched[idx].get("why", result[orig_i]["why"])
                result[orig_i]["watch"] = enriched[idx].get("watch", result[orig_i]["watch"])

        print(f"[enrich] enriched {len(enriched)} events")
        return result

    except Exception as exc:
        print(f"[enrich] AI enrichment failed — keeping originals: {exc}")
        return events


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Morning Edition scraper starting…\n")

    all_events: list[dict] = []
    all_events.extend(scrape_wikicfp())
    all_events.extend(scrape_rss_feeds())
    all_events.extend(scrape_custom_sites())

    print(f"\nRaw results before dedup: {len(all_events)}")
    all_events = deduplicate(all_events)
    print(f"After dedup:               {len(all_events)}")

    all_events.sort(key=lambda e: e.get("_score", 0), reverse=True)

    for ev in all_events:
        ev.pop("_score", None)

    all_events = _enrich_with_ai(all_events)

    if not all_events:
        print(f"Scraper returned 0 results — keeping existing {DATA_FILE} unchanged.")
        return

    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(all_events, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(all_events)} events → {DATA_FILE}")


if __name__ == "__main__":
    main()
