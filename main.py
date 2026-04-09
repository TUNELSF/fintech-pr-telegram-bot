import os
import json
import html
import hashlib
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "seen_ids.json"

FEEDS = [
    "https://rss.globenewswire.com/news/banks-financial-services",
    "https://www.prnewswire.com/rss/financial-services-latest-news.xml"
]

KEYWORDS = [
    "fintech", "bank", "banking", "payments", "lending", "credit",
    "wealth", "asset management", "insurtech", "digital banking",
    "embedded finance", "capital markets", "exchange"
]

def load_seen():
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def item_id(entry):
    base = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.md5(base.encode()).hexdigest()

def parse_date(entry):
    try:
        return parsedate_to_datetime(entry.published)
    except:
        return datetime.now(timezone.utc)

def is_recent(entry):
    dt = parse_date(entry)
    return dt >= datetime.now(timezone.utc) - timedelta(hours=24)

def is_relevant(text):
    text = text.lower()

    score = 0

    for k in KEYWORDS:
        if k in text:
            score += 1

    # broader financial catch
    if "financial" in text or "finance" in text:
        score += 1

    return score >= 1

def fetch_items():
    items = []
    for url in FEEDS:
        feed = feedparser.parse(url)
        for e in feed.entries:
            text = (e.get("title","") + e.get("summary","")).lower()
            if is_recent(e) and is_relevant(text):
                items.append({
                    "id": item_id(e),
                    "title": html.unescape(e.title),
                    "link": e.link,
                    "date": parse_date(e)
                })
    return items

def format_message(items):
    today = datetime.now().strftime("%b %d, %Y")

    if not items:
        return f"Daily Fintech PR Scan — {today}\n\nNo new relevant announcements."

    msg = f"Daily Fintech PR Scan — {today}\n\n"

    for i, item in enumerate(items[:10], 1):
        msg += f"{i}) {item['title']}\n{item['link']}\n\n"

    return msg.strip()

def send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True
    })

def main():
    seen = load_seen()
    items = fetch_items()

    new_items = [i for i in items if i["id"] not in seen]

    if not new_items:
        send("No new fintech PR today.")
        return

    msg = format_message(new_items)
    send(msg)

    for i in new_items:
        seen.add(i["id"])

    save_seen(seen)

if __name__ == "__main__":
    main()
