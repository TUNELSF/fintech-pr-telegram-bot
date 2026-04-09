import os
import json
import html
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "seen_ids.json"

SOURCE_URL = "https://rss.globenewswire.com/news/banks-financial-services"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinNewsDailyBot/1.0)"
}

def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f)

def item_id(title, link):
    return hashlib.md5(f"{title}|{link}".encode("utf-8")).hexdigest()

def fetch_items():
    print(f"Fetching page: {SOURCE_URL}")
    resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = []

    # GlobeNewswire article links on this page are the headline anchors in the main list.
    for a in soup.find_all("a", href=True):
        title = html.unescape(a.get_text(" ", strip=True))
        href = a["href"].strip()

        if not title:
            continue

        if href.startswith("/"):
            link = "https://www.globenewswire.com" + href
        elif href.startswith("http"):
            link = href
        else:
            continue

        # Skip nav/UI links and keep likely article links
        if len(title) < 25:
            continue
        if "news" in title.lower() and title.lower().endswith("news"):
            continue
        if "Read News" in title or "View All" in title or "Next Page" in title:
            continue

        items.append({
            "id": item_id(title, link),
            "title": title,
            "link": link
        })

    # de-duplicate while preserving order
    deduped = []
    seen_local = set()
    for item in items:
        if item["id"] not in seen_local:
            deduped.append(item)
            seen_local.add(item["id"])

    print(f"Items scraped: {len(deduped)}")
    return deduped[:15]

def format_message(items):
    today = datetime.now().strftime("%b %d, %Y")
    if not items:
        return f"Daily Fintech PR Scan — {today}\n\nNo new announcements found."

    lines = [f"Daily Fintech PR Scan — {today}", ""]
    for i, item in enumerate(items[:10], 1):
        lines.append(f"{i}) {item['title']}")
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
    new_items = [i for i in items if i["id"] not in seen]
    print(f"New unseen items: {len(new_items)}")

    send(format_message(new_items))

    for item in new_items:
        seen.add(item["id"])
    save_seen(seen)

if __name__ == "__main__":
    main()
