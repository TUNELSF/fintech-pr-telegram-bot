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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinNewsDailyBot/1.0)"
}

SOURCES = [
    {
        "name": "GlobeNewswire",
        "url": "https://rss.globenewswire.com/news/banks-financial-services",
        "base": "https://www.globenewswire.com",
        "article_must_include": ["globenewswire.com"],
    },
    {
        "name": "PR Newswire Financial Services",
        "url": "https://www.prnewswire.com/news-releases/financial-services-latest-news/financial-services-latest-news-list/",
        "base": "https://www.prnewswire.com",
        "article_must_include": ["/news-releases/"],
    },
    {
        "name": "PR Newswire Financial Technology",
        "url": "https://www.prnewswire.com/news-releases/business-technology-latest-news/financial-technology-list/",
        "base": "https://www.prnewswire.com",
        "article_must_include": ["/news-releases/"],
    },
]

SECTOR_KEYWORDS = [
    "fintech", "financial services", "financial", "finance", "bank", "banking",
    "payments", "payment", "lending", "loan", "loans", "credit", "debit",
    "wealth", "asset management", "brokerage", "insurtech", "insurance",
    "digital banking", "embedded finance", "capital markets", "treasury",
    "merchant", "acquiring", "cards", "mortgage", "bnpl", "stablecoin",
    "crypto", "digital asset", "exchange", "custody", "trading platform"
]

DEVELOPMENT_KEYWORDS = [
    "launch", "launches", "launched",
    "introduce", "introduces", "introduced",
    "unveil", "unveils", "unveiled",
    "expand", "expands", "expanded", "expansion",
    "partner", "partners", "partnership",
    "integrate", "integrates", "integration",
    "rollout", "rolls out",
    "debut", "debuts",
    "new product", "new platform", "new solution",
    "powered by", "collaboration", "alliance"
]

US_HINTS = [
    "u.s.", "united states", "us market", "american",
    "nyse", "nasdaq", "new york", "san francisco", "chicago",
    "miami", "dallas", "boston", "charlotte", "atlanta",
    "los angeles", "seattle", "washington"
]

NEGATIVE_KEYWORDS = [
    "conference call", "webcast", "earnings call", "quarterly results",
    "annual results", "dividend", "dividends", "record date",
    "annual meeting", "investor day", "reminder", "award", "awards",
    "class action", "lawsuit", "investigation", "securities litigation",
    "meme coin", "presale", "airdrop", "nft collection"
]

MAX_ITEMS = 25
TELEGRAM_SAFE_LIMIT = 3500


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


def normalize_link(link, base):
    link = (link or "").strip()
    if not link:
        return ""
    if link.startswith("http://") or link.startswith("https://"):
        return link
    if link.startswith("/"):
        return base.rstrip("/") + link
    return ""


def looks_like_article(link, must_include_parts):
    return any(part in link for part in must_include_parts)


def is_hard_reject(title):
    t = title.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw in t:
            return True
    return False


def score_item(title, source_name):
    t = title.lower()
    score = 0

    for kw in SECTOR_KEYWORDS:
        if kw in t:
            score += 2

    for kw in DEVELOPMENT_KEYWORDS:
        if kw in t:
            score += 3

    for kw in US_HINTS:
        if kw in t:
            score += 1

    for kw in NEGATIVE_KEYWORDS:
        if kw in t:
            score -= 5

    if ("launch" in t or "partner" in t or "integration" in t or "expands" in t):
        score += 2

    if "Financial Technology" in source_name:
        score += 0.5

    return score


def categorize(title):
    t = title.lower()

    if any(x in t for x in ["payment", "payments", "card", "merchant", "acquiring"]):
        return "Payments"
    if any(x in t for x in ["bank", "banking", "digital banking"]):
        return "Banking"
    if any(x in t for x in ["loan", "lending", "credit", "bnpl", "mortgage"]):
        return "Lending"
    if any(x in t for x in ["wealth", "asset management", "brokerage", "trading platform"]):
        return "Wealth"
    if any(x in t for x in ["crypto", "stablecoin", "digital asset", "exchange", "custody"]):
        return "Crypto"
    if any(x in t for x in ["insurance", "insurtech"]):
        return "Insurance"
    return "General"


def scrape_source(source):
    print(f"Fetching source: {source['name']} -> {source['url']}")
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" ", strip=True))
        link = normalize_link(a.get("href", ""), source["base"])

        if not title or not link:
            continue
        if len(title) < 25:
            continue
        if not looks_like_article(link, source["article_must_include"]):
            continue
        if is_hard_reject(title):
            continue

        item = {
            "source": source["name"],
            "title": title,
            "link": link,
        }
        item["id"] = make_id(item["title"], item["link"])
        item["score"] = score_item(item["title"], item["source"])
        item["category"] = categorize(item["title"])
        items.append(item)

    deduped = []
    seen_local = set()
    for item in items:
        if item["id"] in seen_local:
            continue
        seen_local.add(item["id"])
        deduped.append(item)

    print(f"{source['name']} scraped: {len(deduped)}")
    return deduped


def fetch_items():
    all_items = []
    for source in SOURCES:
        try:
            all_items.extend(scrape_source(source))
        except Exception as e:
            print(f"Error scraping {source['name']}: {e}")

    deduped = []
    seen_global = set()
    for item in all_items:
        if item["id"] in seen_global:
            continue
        seen_global.add(item["id"])
        deduped.append(item)

    kept = [item for item in deduped if item["score"] >= 3]
    kept.sort(key=lambda x: x["score"], reverse=True)

    print(f"Total deduped items: {len(deduped)}")
    print(f"Filtered items kept: {len(kept)}")
    return kept[:25]


def format_messages(items):
    today = datetime.now().strftime("%b %d, %Y")

    if not items:
        return [f"Daily Fintech / Financial Services Product Scan — {today}\n\nNo new announcements found."]

    selected_items = items[:MAX_ITEMS]
    header = f"Daily Fintech / Financial Services Product Scan — {today}\n\n"

    chunks = []
    current = header

    for i, item in enumerate(selected_items, 1):
        block = (
            f"{i}) [{item['category']}] {item['title']}\n"
            f"Source: {item['source']}\n"
            f"{item['link']}\n\n"
        )

        if len(current) + len(block) > TELEGRAM_SAFE_LIMIT:
            chunks.append(current.strip())
            current = header + block
        else:
            current += block

    if current.strip():
        chunks.append(current.strip())

    return chunks


def send(messages):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for msg in messages:
        response = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "disable_web_page_preview": True
            },
            timeout=30
        )
        print(response.text)
        response.raise_for_status()


def main():
    seen = load_seen()
    items = fetch_items()
    new_items = [item for item in items if item["id"] not in seen][:MAX_ITEMS]

    print(f"New unseen items: {len(new_items)}")

    messages = format_messages(new_items)
    send(messages)

    for item in new_items:
        seen.add(item["id"])

    save_seen(seen)


if __name__ == "__main__":
    main()
