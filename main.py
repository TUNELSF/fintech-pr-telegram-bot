import os
import re
import json
import html
import hashlib
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "seen_ids.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (FintechIntelBot)"
}

MAX_ITEMS = 50
TELEGRAM_LIMIT = 3500

# -------------------------
# SOURCES
# -------------------------

RSS_SOURCES = [
    ("TechCrunch Fintech", "https://techcrunch.com/tag/fintech/feed/"),
    ("Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("The Paypers", "https://thepaypers.com/feed"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]

HTML_SOURCES = [
    ("GlobeNewswire", "https://rss.globenewswire.com/news/banks-financial-services", "https://www.globenewswire.com"),
    ("PR Newswire", "https://www.prnewswire.com/news-releases/financial-services-latest-news/financial-services-latest-news-list/", "https://www.prnewswire.com"),
]

COMPANY_BLOGS = [
    ("Stripe", "https://stripe.com/blog"),
    ("Plaid", "https://plaid.com/blog/"),
    ("PayPal", "https://newsroom.paypal-corp.com/"),
    ("Coinbase", "https://www.coinbase.com/blog"),
    ("Visa", "https://usa.visa.com/about-visa/newsroom.html"),
    ("Mastercard", "https://www.mastercard.com/news/"),
    ("Block", "https://block.xyz/newsroom"),
    ("Robinhood", "https://blog.robinhood.com/"),
    ("Brex", "https://www.brex.com/blog"),
    ("Ramp", "https://ramp.com/blog"),
    ("Mercury", "https://mercury.com/blog"),
    ("Adyen", "https://www.adyen.com/blog"),
]

# -------------------------
# UTIL
# -------------------------

def load_seen():
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)

def make_id(title, link):
    return hashlib.md5((title + link).encode()).hexdigest()

def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()

# -------------------------
# FETCH FUNCTIONS
# -------------------------

def fetch_rss():
    items = []
    for name, url in RSS_SOURCES:
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = clean(e.get("title"))
            link = e.get("link")
            if title and link:
                items.append({
                    "title": title,
                    "link": link,
                    "source": name
                })
    return items

def fetch_html_sources():
    items = []
    for name, url, base in HTML_SOURCES:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=True):
            title = clean(a.get_text())
            href = a.get("href")

            if len(title) < 25:
                continue

            if href.startswith("/"):
                link = base + href
            elif href.startswith("http"):
                link = href
            else:
                continue

            items.append({
                "title": title,
                "link": link,
                "source": name
            })

    return items

def fetch_company_blogs():
    items = []
    for name, url in COMPANY_BLOGS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                title = clean(a.get_text())
                link = a.get("href")

                if len(title) < 25:
                    continue

                if link.startswith("/"):
                    link = url + link

                if "http" not in link:
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "source": f"{name} Blog"
                })
        except:
            continue

    return items

# -------------------------
# CATEGORY
# -------------------------

def categorize(title):
    t = title.lower()
    if "crypto" in t or "blockchain" in t:
        return "Crypto"
    if "payment" in t or "card" in t:
        return "Payments"
    if "bank" in t:
        return "Banking"
    if "loan" in t or "lending" in t:
        return "Lending"
    if "wealth" in t or "asset" in t:
        return "Wealth"
    return "General"

# -------------------------
# MAIN FETCH
# -------------------------

def fetch_all():
    items = []
    items += fetch_rss()
    items += fetch_html_sources()
    items += fetch_company_blogs()

    dedup = {}
    for i in items:
        id_ = make_id(i["title"], i["link"])
        dedup[id_] = i

    print(f"Total items collected: {len(dedup)}")
    return list(dedup.values())

# -------------------------
# FORMAT
# -------------------------

def format_messages(items):
    today = datetime.now().strftime("%b %d, %Y")
    header = f"Daily Fintech Intelligence — {today}\n\n"

    messages = []
    current = header

    for i, item in enumerate(items[:MAX_ITEMS], 1):
        block = f"{i}) [{categorize(item['title'])}] {item['title']}\nSource: {item['source']}\n{item['link']}\n\n"

        if len(current) + len(block) > TELEGRAM_LIMIT:
            messages.append(current)
            current = header + block
        else:
            current += block

    messages.append(current)
    return messages

def send(messages):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for msg in messages:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "disable_web_page_preview": True
        })
        r.raise_for_status()

# -------------------------
# MAIN
# -------------------------

def main():
    seen = load_seen()
    items = fetch_all()

    new_items = []
    for item in items:
        id_ = make_id(item["title"], item["link"])
        if id_ not in seen:
            new_items.append(item)
            seen.add(id_)

    print(f"New items: {len(new_items)}")

    messages = format_messages(new_items)
    send(messages)

    save_seen(seen)

if __name__ == "__main__":
    main()
