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

MAX_ITEMS = 100
TELEGRAM_LIMIT = 3500

# -------------------------
# RSS SOURCES
# -------------------------

RSS_SOURCES = [
    ("TechCrunch Fintech", "https://techcrunch.com/tag/fintech/feed/"),
    ("Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("The Paypers", "https://thepaypers.com/feed"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]

# -------------------------
# HTML SOURCES
# -------------------------

HTML_SOURCES = [
    ("GlobeNewswire", "https://rss.globenewswire.com/news/banks-financial-services", "https://www.globenewswire.com"),
    ("PR Newswire", "https://www.prnewswire.com/news-releases/financial-services-latest-news/financial-services-latest-news-list/", "https://www.prnewswire.com"),
]

# -------------------------
# COMPANY BLOGS + INSTITUTIONS
# -------------------------

COMPANY_BLOGS = [

# Fintech / Infra
("Stripe", "https://stripe.com/blog"),
("Plaid", "https://plaid.com/blog/"),
("Adyen", "https://www.adyen.com/blog"),
("Checkout.com", "https://www.checkout.com/blog"),

# Crypto / Digital Assets
("Coinbase", "https://www.coinbase.com/blog"),
("Bitwise", "https://bitwiseinvestments.com/insights"),
("Grayscale", "https://grayscale.com/insights/"),
("Galaxy Digital", "https://www.galaxy.com/insights/"),
("VanEck", "https://www.vaneck.com/us/en/blogs/"),
("WisdomTree", "https://www.wisdomtree.com/investments/blog"),

# Banks
("JPMorgan", "https://www.jpmorgan.com/news"),
("Goldman Sachs", "https://www.goldmansachs.com/media-relations/press-releases/"),
("Morgan Stanley", "https://www.morganstanley.com/press-releases"),
("Bank of America", "https://newsroom.bankofamerica.com/"),
("Citi", "https://www.citigroup.com/global/news"),
("Wells Fargo", "https://newsroom.wf.com/"),
("HSBC", "https://www.hsbc.com/news-and-insights"),
("Barclays", "https://home.barclays/news/"),
("Deutsche Bank", "https://www.db.com/news/"),

# Asset Managers
("BlackRock", "https://www.blackrock.com/corporate/newsroom"),
("Vanguard", "https://corporate.vanguard.com/content/corporatesite/us/en/corp/news.html"),
("Fidelity", "https://www.fidelity.com/about-fidelity/our-company/news"),
("State Street", "https://www.statestreet.com/us/en/institutional/about-us/newsroom"),
("Invesco", "https://www.invesco.com/corporate/en/news-and-insights.html"),
("Franklin Templeton", "https://www.franklintempleton.com/about-us/press-room"),
("T Rowe Price", "https://www.troweprice.com/corporate/us/en/press.html"),
("PIMCO", "https://www.pimco.com/en-us/insights"),
("Schroders", "https://www.schroders.com/en/global/insights/"),
("Amundi", "https://www.amundi.com/institutional/Local-Content/News"),
("AllianceBernstein", "https://www.alliancebernstein.com/corporate/en/news.html"),

# Custodians
("BNY Mellon", "https://www.bnymellon.com/us/en/newsroom.html"),
("Northern Trust", "https://www.northerntrust.com/united-states/newsroom"),

# Wealth / RIA
("Charles Schwab", "https://pressroom.aboutschwab.com/"),
("LPL Financial", "https://www.lpl.com/newsroom.html"),
("Envestnet", "https://www.envestnet.com/newsroom"),

# Index Providers
("MSCI", "https://www.msci.com/www/news-and-announcements"),
("S&P Dow Jones", "https://www.spglobal.com/spdji/en/newsroom/"),
("FTSE Russell", "https://www.lseg.com/en/ftse-russell/news"),
("Bloomberg Indexes", "https://www.bloomberg.com/professional/blog/category/indices/"),
("Morningstar Indexes", "https://indexes.morningstar.com/our-indexes"),
("Solactive", "https://www.solactive.com/news/"),
("STOXX", "https://www.stoxx.com/news"),
("Nasdaq Indexes", "https://www.nasdaq.com/news-and-insights"),
("MarketVector", "https://www.marketvector.com/insights"),
("ICE Data", "https://www.theice.com/insights"),
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
                items.append({"title": title, "link": link, "source": name})
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

            items.append({"title": title, "link": link, "source": name})

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
