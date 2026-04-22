import os
import re
import json
import html
import time
import hashlib
import traceback
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "seen_ids.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (FintechIntelBot)"
}

TOP_N = 100
TELEGRAM_LIMIT = 3500

# -------------------------
# RSS SOURCES
# -------------------------

RSS_SOURCES = [
    ("TechCrunch Fintech", "https://techcrunch.com/tag/fintech/feed/"),
    ("Finextra", "https://www.finextra.com/rss/headlines.aspx"),
    ("The Paypers", "https://thepaypers.com/feed"),
    ("PYMNTS", "https://www.pymnts.com/feed/"),
    ("Bank Automation News", "https://bankautomationnews.com/feed/"),
    ("Finovate", "https://finovate.com/feed/"),
    ("IBS Intelligence", "https://ibsintelligence.com/ibsi-news/feed/"),
    ("Crowdfund Insider Fintech", "https://www.crowdfundinsider.com/category/fintech/feed/"),
    ("PaymentsJournal", "https://www.paymentsjournal.com/feed/"),
    ("American Banker", "https://www.americanbanker.com/feeds/rss"),
    ("ETF.com", "https://www.etf.com/sections/news/feed"),
    ("ETF Stream", "https://www.etfstream.com/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("DL News", "https://www.dlnews.com/rss/"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("GlobeNewswire", "https://rss.globenewswire.com/news/banks-financial-services"),
    ("PR Newswire Financial Services", "https://www.prnewswire.com/rss/financial-services-latest-news.xml"),
]

# -------------------------
# HTML SOURCES
# -------------------------

HTML_SOURCES = []

# -------------------------
# COMPANY BLOGS + INSTITUTIONS + ECOSYSTEM BLOGS
# -------------------------

COMPANY_BLOGS = [
    ("Alchemy", "https://www.alchemy.com/blog"),
    ("Amberdata", "https://blog.amberdata.io/"),
    ("Anchorage Digital", "https://www.anchorage.com/blog"),
    ("Binance US", "https://blog.binance.us/"),
    ("BitGo", "https://www.bitgo.com/blog/"),
    ("Blockdaemon", "https://www.blockdaemon.com/blog"),
    ("Chainalysis", "https://www.chainalysis.com/blog/"),
    ("Chainlink Labs", "https://blog.chain.link/"),
    ("Circle", "https://www.circle.com/blog"),
    ("Coin Metrics", "https://coinmetrics.io/insights/"),
    ("Coinbase", "https://www.coinbase.com/blog"),
    ("Consensys", "https://consensys.io/blog"),
    ("Copper", "https://www.copper.co/insights"),
    ("Elliptic", "https://www.elliptic.co/blog"),
    ("FalconX", "https://www.falconx.io/insights"),
    ("Figure", "https://figure.com/blog/"),
    ("Galaxy Digital", "https://www.galaxy.com/insights/"),
    ("Gemini", "https://www.gemini.com/blog"),
    ("Glassnode", "https://insights.glassnode.com/"),
    ("Grayscale", "https://grayscale.com/insights/"),
    ("Hashdex", "https://hashdex.com/en-US/insights"),
    ("Kaiko", "https://research.kaiko.com/"),
    ("Kraken", "https://blog.kraken.com/"),
    ("Ledger Enterprise", "https://www.ledger.com/blog"),
    ("Mesh", "https://www.meshconnect.com/blog"),
    ("MoonPay", "https://www.moonpay.com/blog"),
    ("Nansen", "https://www.nansen.ai/research"),
    ("OKX", "https://www.okx.com/learn"),
    ("Paxos", "https://paxos.com/blog/"),
    ("Ramp Network", "https://ramp.network/blog"),
    ("TRM Labs", "https://www.trmlabs.com/post"),
    ("Talos", "https://www.talos.com/insights"),
    ("Zero Hash", "https://www.zerohash.com/blog"),
    ("Fireblocks", "https://www.fireblocks.com/blog/"),
    ("Securitize", "https://www.securitize.io/blog"),
    ("Taurus", "https://www.taurushq.com/blog"),
    ("Ripple", "https://ripple.com/insights/"),

    ("Bitcoin Magazine", "https://bitcoinmagazine.com/"),
    ("Ethereum", "https://blog.ethereum.org/"),
    ("Solana", "https://solana.com/news"),
    ("BNB Chain", "https://www.bnbchain.org/en/blog"),
    ("Avalanche", "https://www.avax.network/blog"),
    ("Aptos", "https://aptosfoundation.org/currents"),
    ("Sui", "https://blog.sui.io/"),
    ("Tron", "https://tron.network/news"),
    ("TON", "https://blog.ton.org/"),

    ("Arbitrum", "https://arbitrum.io/blog/"),
    ("Base", "https://www.base.org/blog"),
    ("Optimism", "https://www.optimism.io/blog"),
    ("zkSync", "https://blog.zksync.io/"),
    ("Starknet", "https://www.starknet.io/blog/"),
    ("Mantle", "https://www.mantle.xyz/blog"),
    ("Polygon", "https://polygon.technology/blog"),

    ("AlphaSense", "https://www.alpha-sense.com/resources/"),
    ("Axioma", "https://www.axioma.com/insights"),
    ("Bloomberg", "https://www.bloomberg.com/professional/blog/"),
    ("Cboe Global Markets", "https://www.cboe.com/insights/posts/"),
    ("FactSet", "https://insight.factset.com/"),
    ("LSEG", "https://www.lseg.com/en/news"),
    ("MSCI", "https://www.msci.com/www/news-and-announcements"),
    ("Morningstar", "https://www.morningstar.com/lp/articles"),
    ("Nasdaq", "https://www.nasdaq.com/news-and-insights"),
    ("Numerix", "https://www.numerix.com/resources"),
    ("S&P Global", "https://www.spglobal.com/en/research-insights/latest-news"),

    ("Plaid", "https://plaid.com/blog/"),
    ("Yodlee", "https://www.yodlee.com/blog"),
    ("Adyen", "https://www.adyen.com/blog"),
    ("Airwallex", "https://www.airwallex.com/blog"),
    ("Brex", "https://www.brex.com/blog"),
    ("Checkout.com", "https://www.checkout.com/blog"),
    ("Chime", "https://www.chime.com/blog/"),
    ("Galileo", "https://www.galileo-ft.com/blog/"),
    ("Mambu", "https://mambu.com/en/insights"),
    ("Marqeta", "https://www.marqeta.com/blog"),
    ("Mastercard", "https://www.mastercard.com/news/perspectives/"),
    ("Mercury", "https://mercury.com/blog"),
    ("Nium", "https://www.nium.com/blog"),
    ("Payoneer", "https://blog.payoneer.com/"),
    ("Ramp", "https://ramp.com/blog"),
    ("Revolut", "https://www.revolut.com/news/"),
    ("SoFi", "https://www.sofi.com/blog/"),
    ("Solaris", "https://www.solarisgroup.com/newsroom/"),
    ("Stripe", "https://stripe.com/blog"),
    ("Temenos", "https://www.temenos.com/news/"),
    ("Thought Machine", "https://www.thoughtmachine.net/blog"),
    ("Treasury Prime", "https://www.treasuryprime.com/blog"),
    ("Unit", "https://www.unit.co/blog"),
    ("Visa", "https://usa.visa.com/visa-everywhere/blog.html"),
    ("Wise", "https://wise.com/us/blog"),

    ("GLG", "https://glginsights.com/articles/"),
    ("Alpaca", "https://alpaca.markets/blog/"),
    ("Apex Clearing", "https://www.apexfintechsolutions.com/newsroom/"),
    ("Broadridge", "https://www.broadridge.com/insights"),
    ("Calypso Technology", "https://www.adenza.com/insights"),
    ("Carta", "https://carta.com/blog/"),
    ("DriveWealth", "https://www.drivewealth.com/blog/"),
    ("FIS", "https://www.fisglobal.com/en/insights"),
    ("Fiserv", "https://www.fiserv.com/en/about-fiserv/resource-center.html"),
    ("Forge Global", "https://forgeglobal.com/insights/"),
    ("Interactive Brokers", "https://www.interactivebrokers.com/en/general/education/blog.php"),
    ("Public.com", "https://public.com/learn"),
    ("Robinhood", "https://blog.robinhood.com/"),
    ("SS&C Technologies", "https://www.ssctech.com/insights"),
    ("SimCorp", "https://www.simcorp.com/en/insights"),

    ("Yieldstreet", "https://www.yieldstreet.com/resources/"),
    ("Addepar", "https://addepar.com/blog"),
    ("Betterment", "https://www.betterment.com/resources"),
    ("CAIS", "https://www.caisgroup.com/articles"),
    ("Envestnet", "https://www.envestnet.com/newsroom"),
    ("Orion Advisor Solutions", "https://orion.com/blog/"),
    ("Riskalyze (Nitrogen)", "https://nitrogenwealth.com/blog/"),
    ("Wealthfront", "https://www.wealthfront.com/blog"),
    ("iCapital", "https://icapital.com/insights/"),

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
# QUALITY / CATEGORY RULES
# -------------------------

SOURCE_QUALITY = {
    "globenewswire": 5,
    "pr newswire": 5,

    "techcrunch fintech": 4,
    "finextra": 4,
    "american banker": 4,
    "the block": 4,
    "coindesk": 4,

    "the paypers": 3,
    "pymnts": 3,
    "paymentsjournal": 3,
    "decrypt": 3,
    "cointelegraph": 3,
    "bank automation news": 3,
    "etf.com": 3,
    "etf stream": 3,
    "finovate": 3,
    "ibs intelligence": 3,

    "blog": 5,
}

STRONG_POSITIVE_KEYWORDS = [
    "launch", "launches", "launched",
    "introduce", "introduces", "introduced",
    "announce", "announces", "announced",
    "unveil", "unveils", "unveiled",
    "debut", "debuts", "debuted",
    "partnership", "partners", "partner",
    "integration", "integrates", "integrated",
    "rollout", "roll out",
    "new product", "new platform", "new solution",
    "whitepaper", "research", "webinar",
    "api", "platform", "solution", "index", "etf", "fund"
]

WEAK_NEGATIVE_KEYWORDS = [
    "price prediction", "market wrap", "price analysis", "trading setup",
    "op-ed", "opinion", "podcast", "transcript", "lawsuit",
    "investigation", "enforcement", "macro outlook"
]

US_RELEVANCE_KEYWORDS = [
    "u.s.", "united states", "us market", "sec", "finra",
    "nyse", "nasdaq", "american", "u.s.-based"
]

AGENTIC_KEYWORDS = [
    "agentic", "ai agent", "ai agents", "copilot", "assistant",
    "autonomous", "workflow automation", "agent-based",
    "agentic payment", "payment copilot", "investment copilot",
    "agentic finance", "ai advisor", "ai portfolio", "robo-advisor",
    "robo advisor", "automated investing", "autonomous payment",
    "ai treasury", "ai invoice", "ai payable", "ai underwriting"
]

CRYPTO_KEYWORDS = [
    "crypto", "bitcoin", "ethereum", "stablecoin", "token",
    "tokenization", "digital asset", "blockchain", "defi", "web3",
    "staking", "onchain", "on-chain", "wallet", "custody",
    "exchange", "spot bitcoin", "spot ether", "solana", "arbitrum",
    "base", "optimism", "zksync", "starknet", "polygon",
    "aptos", "sui", "avalanche", "bnb", "tron", "ton"
]

SPECIFICITY_KEYWORDS = [
    "index", "etf", "fund", "api", "sdk", "wallet", "custody",
    "platform", "stablecoin", "tokenization", "settlement", "payments",
    "card", "treasury", "lending", "advisor", "portfolio"
]

# -------------------------
# UTIL
# -------------------------

def load_seen():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f)


def make_id(title, link):
    return hashlib.md5((title + link).encode("utf-8")).hexdigest()


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def normalize_link(base_url, href):
    if not href:
        return ""

    href = href.strip()

    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return base_url.rstrip("/") + href
    if href.startswith("#") or href.startswith("javascript:"):
        return ""

    return ""


def source_priority(source_name):
    s = source_name.lower()
    if "globenewswire" in s or "pr newswire" in s:
        return 1
    if "blog" in s:
        return 2
    return 3


def infer_source_quality(source_name):
    s = source_name.lower()

    for key, score in SOURCE_QUALITY.items():
        if key in s:
            return score

    return 2


def categorize(title, source=""):
    t = (title + " " + source).lower()

    if any(keyword in t for keyword in AGENTIC_KEYWORDS):
        return "Agentic Finance"

    if any(keyword in t for keyword in CRYPTO_KEYWORDS):
        return "Crypto"

    return "Traditional Finance"


def is_productish(title):
    t = title.lower()

    if any(x in t for x in WEAK_NEGATIVE_KEYWORDS):
        return False

    broad_positive = STRONG_POSITIVE_KEYWORDS + [
        "new", "product", "feature", "features", "capability", "capabilities",
        "report", "paper", "index", "fund", "etf", "tooling", "tool",
        "launchpad", "infrastructure", "payments", "banking", "custody"
    ]

    return any(x in t for x in broad_positive)


def quality_score(title, source=""):
    t = (title + " " + source).lower()
    score = 0

    # 1. Source quality (0-5)
    score += infer_source_quality(source)

    # 2. Product-development intent (0-5)
    intent_hits = sum(1 for kw in STRONG_POSITIVE_KEYWORDS if kw in t)
    score += min(intent_hits, 5)

    # 3. Specificity / named product-like signals (0-3)
    specificity_hits = sum(1 for kw in SPECIFICITY_KEYWORDS if kw in t)
    score += min(specificity_hits, 3)

    # 4. U.S. relevance (0-2)
    us_hits = sum(1 for kw in US_RELEVANCE_KEYWORDS if kw in t)
    score += min(us_hits, 2)

    # 5. Category relevance bonus (0-2)
    if categorize(title, source) == "Agentic Finance":
        score += 2
    elif categorize(title, source) == "Crypto":
        score += 1

    # Negative adjustments
    if any(x in t for x in WEAK_NEGATIVE_KEYWORDS):
        score -= 3

    # Reward title richness
    if len(title) > 60:
        score += 1

    return score


def generate_summary(title, source=""):
    t = (title + " " + source).lower()

    if "partnership" in t or "partners" in t or "partner" in t:
        action = "New partnership or go-to-market collaboration."
    elif "launch" in t or "introduce" in t or "unveil" in t or "debut" in t:
        action = "New product or platform launch."
    elif "integration" in t:
        action = "New product integration or workflow expansion."
    elif "whitepaper" in t or "research" in t or "report" in t:
        action = "New research or product-related market analysis."
    elif "webinar" in t:
        action = "Webinar tied to new capabilities or product strategy."
    elif "index" in t or "etf" in t or "fund" in t:
        action = "New investment product, index, or fund-related announcement."
    else:
        action = "New development relevant to the sector."

    category = categorize(title, source)
    if category == "Agentic Finance":
        prefix = "Agentic-finance signal."
    elif category == "Crypto":
        prefix = "Crypto / digital-asset signal."
    else:
        prefix = "Traditional-finance signal."

    return f"{prefix} {action}"

# -------------------------
# FETCH FUNCTIONS
# -------------------------

def fetch_rss():
    items = []

    for name, url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)

            for e in feed.entries:
                title = clean(e.get("title"))
                link = e.get("link")

                if not title or not link:
                    continue
                if len(title) < 20:
                    continue
                if not is_productish(title):
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "source": name
                })

        except Exception as e:
            print(f"RSS fetch failed for {name}: {e}")

    return items


def fetch_html_sources():
    items = []

    for name, url, base in HTML_SOURCES:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                title = clean(a.get_text())
                href = a.get("href")
                link = normalize_link(base, href)

                if not title or not link:
                    continue
                if len(title) < 25:
                    continue
                if not is_productish(title):
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "source": name
                })

        except Exception as e:
            print(f"HTML fetch failed for {name}: {e}")

    return items


def fetch_company_blogs():
    items = []

    for name, url in COMPANY_BLOGS:
        try:
            time.sleep(0.25)
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                title = clean(a.get_text())
                href = a.get("href")
                link = normalize_link(url, href)

                if not title or not link:
                    continue
                if len(title) < 25:
                    continue
                if not is_productish(title):
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "source": f"{name} Blog"
                })

        except Exception as e:
            print(f"Blog fetch failed for {name}: {e}")
            continue

    return items

# -------------------------
# MAIN FETCH
# -------------------------

def fetch_all():
    items = []
    items += fetch_rss()
    items += fetch_html_sources()
    items += fetch_company_blogs()

    dedup = {}
    for item in items:
        id_ = make_id(item["title"], item["link"])

        item["category"] = categorize(item["title"], item["source"])
        item["quality"] = quality_score(item["title"], item["source"])
        item["summary"] = generate_summary(item["title"], item["source"])

        if id_ not in dedup:
            dedup[id_] = item
        else:
            existing = dedup[id_]

            # Prefer higher-quality item; tie-break to source priority
            if item["quality"] > existing["quality"]:
                dedup[id_] = item
            elif item["quality"] == existing["quality"]:
                if source_priority(item["source"]) < source_priority(existing["source"]):
                    dedup[id_] = item

    results = list(dedup.values())
    results.sort(key=lambda x: (-x["quality"], x["category"], x["source"], x["title"]))

    print(f"Total items collected after dedup: {len(results)}")
    return results

# -------------------------
# FORMAT
# -------------------------

def top_items(items):
    return items[:TOP_N]


def group_by_top_category(items):
    grouped = {
        "Traditional Finance": [],
        "Crypto": [],
        "Agentic Finance": [],
    }

    for item in items:
        grouped[item["category"]].append(item)

    return grouped


def format_messages(items):
    today = datetime.now().strftime("%b %d, %Y")
    grouped = group_by_top_category(items)
    messages = []

    for bucket in ["Traditional Finance", "Crypto", "Agentic Finance"]:
        bucket_items = grouped[bucket]
        if not bucket_items:
            continue

        header = (
            f"Daily Fintech Intelligence — {today}\n\n"
            f"{bucket}\n"
            f"Top curated items by quality\n\n"
        )

        current = header

        for i, item in enumerate(bucket_items, 1):
            block = (
                f"{i}) {item['title']}\n"
                f"Summary: {item['summary']}\n"
                f"Quality: {item['quality']}\n"
                f"Source: {item['source']}\n"
                f"{item['link']}\n\n"
            )

            if len(current) + len(block) > TELEGRAM_LIMIT:
                messages.append(current.strip())
                current = header + block
            else:
                current += block

        if current.strip():
            messages.append(current.strip())

    if not messages:
        messages = [f"Daily Fintech Intelligence — {today}\n\nNo new items found today."]

    return messages


def send(messages):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for msg in messages:
        r = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "disable_web_page_preview": True
            },
            timeout=20
        )

        if r.status_code != 200:
            raise RuntimeError(f"Telegram API error {r.status_code}: {r.text}")

        r.raise_for_status()

# -------------------------
# MAIN
# -------------------------

def main():
    try:
        seen = load_seen()
        items = fetch_all()

        new_items = []
        for item in items:
            id_ = make_id(item["title"], item["link"])
            if id_ not in seen:
                new_items.append(item)

        print(f"New items before quality curation: {len(new_items)}")

        curated = top_items(new_items)
        print(f"Curated top items sent: {len(curated)}")

        messages = format_messages(curated)
        send(messages)

        for item in curated:
            seen.add(make_id(item["title"], item["link"]))

        save_seen(seen)

    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
