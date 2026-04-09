import os
import re
import json
import html
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "seen_ids.json"

SOURCES = [
    {
        "name": "GlobeNewswire",
        "type": "html",
        "url": "https://rss.globenewswire.com/news/banks-financial-services",
    },
    {
        "name": "PR Newswire",
        "type": "html",
        "url": "https://www.prnewswire.com/news-releases/financial-services-latest-news/financial-services-latest-news-list/",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinNewsDailyBot/1.0)"
}

POSITIVE_KEYWORDS = [
    "bank", "banking", "financial", "finance", "fintech", "payments",
    "lending", "credit", "debit", "wealth", "asset management",
    "brokerage", "insurtech", "digital banking", "embedded finance",
    "capital markets", "treasury", "merchant", "acquiring",
    "card", "cards", "mortgage", "loan", "loans", "insurance",
    "investment bank", "investment banking", "private equity",
    "asset servicing", "custody", "risk management"
]

NEGATIVE_KEYWORDS = [
    "webcast", "conference call", "conference-call", "investor call",
    "earnings call", "quarterly results", "annual results", "dividend",
    "dividends", "distribution declaration", "record date", "ex-dividend",
    "net asset value", "nav per share", "conference", "summit",
    "forum", "expo", "award", "awards", "final deadline", "reminder",
    "class action", "lawsuit", "securities litigation", "investigation",
    "shareholder alert", "crypto", "token", "presale", "meme coin",
    "coin", "blockchain gaming", "nft"
]

US_HINTS = [
    "u.s.", "united states", "america", "american", "nyse", "nasdaq",
    "new york", "san francisco", "chicago", "miami", "dallas", "boston",
    "atlanta", "charlotte", "washington", "los angeles", "seattle"
]

MAX_ITEMS = 10


def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, indent=2)


def make_id(title, link):
    return hashlib.md5(f"{title}|{link}".encode("utf-8")).hexdigest()


def clean_text(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def score_item(title, source_name):
    t = title.lower()
    score = 0

    for kw in POSITIVE_KEYWORDS:
        if kw in t:
            score += 2

    for kw in US_HINTS:
        if kw in t:
            score += 1

    for kw in NEGATIVE_KEYWORDS:
        if kw in t:
            score -= 4

    if "announces" in t or "launches" in t or "expands" in t or "partners" in t:
        score += 1

    if source_name == "PR Newswire":
        score += 0.2

    return score


def is_junk(title):
    t = title.lower()

    hard_reject_patterns = [
        r"\bcrypto\b",
        r"\btoken\b",
        r"\bmeme coin\b",
        r"\bnft\b",
        r"\bconference call\b",
        r"\bwebcast\b",
        r"\bdividend\b",
        r"\bclass action\b",
        r"\blawsuit\b",
        r"\binvestigation\b",
        r"\baward\b",
    ]

    return any(re.search(pattern, t) for pattern in hard_reject_patterns)


def normalize_link(link, base):
    link = (link or "").strip()
    if not link:
        return ""
    if link.startswith("http://") or link.startswith("https://"):
        return link
    if link.startswith("/"):
        return base.rstrip("/") + link
    return ""


def scrape_globenewswire():
    url = "https://rss.globenewswire.com/news/banks-financial-services"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" ", strip=True))
        link = normalize_link(a["href"], "https://www.globenewswire.com")

        if not title or not link:
            continue
        if len(title) < 25:
            continue
        if "globenewswire" not in link:
            continue
        if is_junk(title):
            continue

        items.append({
            "source": "GlobeNewswire",
            "title": title,
            "link": link,
        })

    return dedupe_items(items)


def scrape_prnewswire():
    url = "https://www.prnewswire.com/news-releases/financial-services-latest-news/financial-services-latest-news-list/"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" ", strip=True))
        href = a.get("href", "")
        link = normalize_link(href, "https://www.prnewswire.com")

        if not title or not link:
            continue
        if len(title) < 25:
            continue
        if "/news-releases/" not in link:
            continue
        if is_junk(title):
            continue

        items.append({
            "source": "PR Newswire",
            "title": title,
            "link": link,
        })

    return dedupe_items(items)


def dedupe_items(items):
    seen = set()
    deduped = []

    for item in items:
        iid = make_id(item["title"], item["link"])
        if iid in seen:
            continue
        item["id"] = iid
        seen.add(iid)
        deduped.append(item)

    return deduped


def fetch_items():
    all_items = []

    globe_items = scrape_globenewswire()
    prn_items = scrape_prnewswire()

    print(f"GlobeNewswire items scraped: {len(globe_items)}")
    print(f"PR Newswire items scraped: {len(prn_items)}")

    all_items.extend(globe_items)
    all_items.extend(prn_items)

    all_items = dedupe_items(all_items)

    scored = []
    for item in all_items:
        item["score"] = score_item(item["title"], item["source"])
        if item["score"] >= 1:
            scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)

    print(f"Filtered items kept: {len(scored)}")
    return scored[:20]


def format_message(items):
    today = datetime.now().strftime("%b %d, %Y")

    if not items:
        return f"Daily Fintech PR Scan — {today}\n\nNo new announcements found."

    lines = [f"Daily Fintech PR Scan — {today}", ""]

    for i, item in enumerate(items[:MAX_ITEMS], 1):
        lines.append(f"{i}) {item['title']}")
        lines.append(f"Source: {item['source']}")
        lines.append(item["link"])
        lines.append("")

    return "\n".join(lines).strip()


def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "disable_web_page_preview": True
        },
        timeout=30
    )
    response.raise_for_status()


def main():
    seen = load_seen()
    items = fetch_items()
    new_items = [item for item in items if item["id"] not in seen]

    print(f"New unseen items: {len(new_items)}")

    send(format_message(new_items))

    for item in new_items:
        seen.add(item["id"])

    save_seen(seen)


if __name__ == "__main__":
    main()
