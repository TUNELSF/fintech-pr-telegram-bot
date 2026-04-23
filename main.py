"""
Fintech Product Launch Scanner
------------------------------
Scans fintech/finance RSS feeds daily, filters for genuine product
launches, partnerships and integrations, and posts a clean briefing
to Telegram — with US and EU digests sent as separate messages.

Run via GitHub Actions or cron.
Requires env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import os
import re
import json
import html
import time
import logging
import hashlib
import calendar
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse

import requests
import feedparser

# ---------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "seen_ids.json"
HEALTH_FILE = "source_health.json"

TOP_N_PER_REGION = 20
MAX_AGE_HOURS = 48
TELEGRAM_LIMIT = 4000  # actual limit is 4096, leaving headroom
MAX_SEEN_ENTRIES = 5000  # cap to keep state file bounded

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FintechRadar/1.0; "
        "+https://github.com/yourname/fintech-scanner)"
    )
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("fintech-radar")


# ---------------------------------------------------------------
# SOURCES
# Each: (name, url, region, tier)
#   region: "US", "EU", or "GLOBAL" (GLOBAL items get region-detected)
#   tier:   1 = wires/regulators, 2 = trade press, 3 = general tech
#
# URLs marked with VERIFY in a comment should be sanity-checked on first
# run — feed paths change occasionally. Watch the logs on the first few
# runs and drop any source that consistently fails to parse.
# ---------------------------------------------------------------

SOURCES = [
    # Wires — global, tier 1
    ("GlobeNewswire FS",  "https://www.globenewswire.com/RssFeed/subjectcode/9-Banking%20and%20Financial%20Services/feedTitle/GlobeNewswire%20-%20Banking%20and%20Financial%20Services", "GLOBAL", 1),
    ("PR Newswire FS",    "https://www.prnewswire.com/rss/financial-services-latest-news.xml", "GLOBAL", 1),
    ("Business Wire FS",  "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeGVtRVA==", "GLOBAL", 1),  # VERIFY

    # US regulators — tier 1
    ("SEC Press",         "https://www.sec.gov/news/pressreleases.rss", "US", 1),
    ("Federal Reserve",   "https://www.federalreserve.gov/feeds/press_all.xml", "US", 1),
    ("OCC",               "https://www.occ.gov/rss/occ_nr.xml", "US", 1),  # VERIFY
    ("FDIC",              "https://www.fdic.gov/news/press-releases/rss.xml", "US", 1),  # VERIFY
    ("CFPB",              "https://www.consumerfinance.gov/about-us/newsroom/feed/", "US", 1),

    # US trade press — tier 2
    ("American Banker",   "https://www.americanbanker.com/feeds/rss", "US", 2),
    ("Banking Dive",      "https://www.bankingdive.com/feeds/news/", "US", 2),
    ("PYMNTS",            "https://www.pymnts.com/feed/", "US", 2),

    # UK/EU regulators — tier 1
    ("FCA News",          "https://www.fca.org.uk/news/rss.xml", "EU", 1),
    ("Bank of England",   "https://www.bankofengland.co.uk/rss/news", "EU", 1),
    ("ECB Press",         "https://www.ecb.europa.eu/press/pr/html/index.en.rss", "EU", 1),  # VERIFY

    # EU trade press — tier 2
    ("Finextra",          "https://www.finextra.com/rss/headlines.aspx", "EU", 2),
    ("AltFi",             "https://www.altfi.com/rss", "EU", 2),  # VERIFY
    ("Sifted",            "https://sifted.eu/feed", "EU", 2),  # VERIFY
    ("Fintech Futures",   "https://www.fintechfutures.com/feed/", "EU", 2),
    ("The Fintech Times", "https://thefintechtimes.com/feed/", "EU", 2),  # VERIFY

    # Google News RSS — free, synthesizes thousands of publishers
    # Tagged GLOBAL so the region detector classifies each hit individually.
    ("Google News (wires)",  "https://news.google.com/rss/search?q=%22launches%22+(fintech+OR+%22digital+bank%22+OR+payments+OR+stablecoin)+(site%3Aprnewswire.com+OR+site%3Abusinesswire.com+OR+site%3Aglobenewswire.com)&hl=en-US&gl=US&ceid=US:en", "GLOBAL", 2),
    ("Google News (US)",     "https://news.google.com/rss/search?q=(%22launches%22+OR+%22unveils%22+OR+%22introduces%22)+(fintech+OR+bank+OR+wallet+OR+payments+OR+stablecoin)+%22U.S.%22&hl=en-US&gl=US&ceid=US:en", "GLOBAL", 2),
    ("Google News (Europe)", "https://news.google.com/rss/search?q=(%22launches%22+OR+%22unveils%22+OR+%22introduces%22)+(fintech+OR+bank+OR+wallet+OR+payments)+(UK+OR+Europe+OR+European)&hl=en-GB&gl=GB&ceid=GB:en", "GLOBAL", 2),

    # Tech / crypto — tier 3, filtered strictly
    ("TechCrunch Fintech","https://techcrunch.com/category/fintech/feed/", "GLOBAL", 3),
    ("The Block",         "https://www.theblock.co/rss.xml", "GLOBAL", 3),
    ("CoinDesk",          "https://www.coindesk.com/arc/outboundfeeds/rss/", "GLOBAL", 3),
]


# ---------------------------------------------------------------
# KEYWORDS & PATTERNS
# ---------------------------------------------------------------

LAUNCH_VERB_RE = re.compile(
    r"\b(launch(?:es|ed|ing)?|introduc(?:es|ed|ing)|unveil(?:s|ed|ing)?|"
    r"debut(?:s|ed|ing)?|roll(?:s|ed)?\s+out|go(?:es)?\s+live|"
    r"releas(?:es|ed|ing))\b",
    re.I,
)

PRODUCT_NOUN_RE = re.compile(
    r"\b(platform|product|service|app|feature|tool|api|sdk|integration|"
    r"partnership|fund|etf|index|stablecoin|card|account|loan|wallet|"
    r"stack|suite|neobank|bank|exchange|marketplace|portal|solution)\b",
    re.I,
)

PARTNERSHIP_RE = re.compile(
    r"\b(partner(?:s|ed|ship)?\s+with|teams?\s+up\s+with|"
    r"integrat(?:es|ed|ion)\s+with|joins?\s+forces\s+with|"
    r"collaborat(?:es|ed|ion)\s+with)\b",
    re.I,
)

NEGATIVE_RE = re.compile(
    r"\b(earnings|quarterly|fiscal\s+(?:year|quarter)|q[1-4]\s+\d|"
    r"price\s+(?:prediction|target|analysis)|opinion|podcast|interview|"
    r"lawsuit|sues|sued|settlement|fined|penalty|violation|"
    r"hack(?:ed|ing)?|breach(?:ed)?|exploit|stolen|scam|fraud|"
    r"layoff|resigns?|fires?\s+|cut\s+jobs|"
    r"market\s+(?:wrap|report|recap)|weekly\s+recap|daily\s+brief|"
    r"upgrade\s+(?:to|from)|downgrade|rating\s+(?:cut|lowered))\b",
    re.I,
)


# ---------------------------------------------------------------
# REGION DETECTION (for GLOBAL sources)
# ---------------------------------------------------------------

US_SIGNALS = re.compile(
    r"\b(U\.?S\.?|USA|united\s+states|america(?:n)?|"
    r"SEC|FDIC|OCC|CFPB|FinCEN|"
    r"federal\s+reserve|the\s+fed\b|treasury|IRS|"
    r"nasdaq|nyse|cboe|wall\s+street|"
    r"(?:new\s+york|california|texas|delaware)|"
    r"jpmorgan|wells\s+fargo|bank\s+of\s+america|citigroup|"
    r"goldman\s+sachs|morgan\s+stanley|chime|plaid|stripe|"
    r"coinbase|robinhood|sofi|fidelity|charles\s+schwab)\b",
    re.I,
)

EU_SIGNALS = re.compile(
    r"\b(U\.?K\.?|britain|british|england|scotland|ireland|"
    r"E\.?U\.?|europe(?:an)?|eurozone|"
    r"london|berlin|paris|madrid|amsterdam|dublin|stockholm|frankfurt|"
    r"germany|france|spain|italy|netherlands|sweden|poland|portugal|"
    r"FCA|PRA|bank\s+of\s+england|ECB|EBA|ESMA|BaFin|AMF\b|"
    r"HSBC|barclays|lloyds|natwest|deutsche\s+bank|BNP\s+paribas|"
    r"santander|ING\s+group|UBS|revolut|monzo|starling|N26|klarna|"
    r"wise|adyen|checkout\.com|truelayer|qonto|bunq)\b",
    re.I,
)


# ---------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------

def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def normalize_url(url):
    """Strip query strings and fragments so UTM-tagged duplicates collapse."""
    try:
        p = urlparse(url)
        normalized = urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))
        return normalized.lower()
    except Exception:
        return url


def make_id(url):
    return hashlib.md5(normalize_url(url).encode()).hexdigest()


def entry_datetime(entry):
    """Return timezone-aware UTC datetime for a feed entry, or None."""
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
            except Exception:
                continue
    return None


# ---------------------------------------------------------------
# SOURCE HEALTH
# ---------------------------------------------------------------

def update_health(health, source, success):
    h = health.setdefault(source, {"fail": 0, "success": 0})
    if success:
        h["success"] += 1
        h["fail"] = 0
    else:
        h["fail"] += 1
    return health


def is_source_blocked(health, source):
    return health.get(source, {}).get("fail", 0) >= 5


# ---------------------------------------------------------------
# FILTERS
# ---------------------------------------------------------------

def is_real_launch(title, summary=""):
    """
    Stricter filter: must match one of:
      - launch verb + product noun
      - partnership / integration pattern
    AND must not match a negative pattern.
    """
    text = f"{title} {summary}"

    if NEGATIVE_RE.search(text):
        return False

    if PARTNERSHIP_RE.search(text):
        return True

    if LAUNCH_VERB_RE.search(text) and PRODUCT_NOUN_RE.search(text):
        return True

    return False


def detect_region(title, summary, link, source_region):
    """
    Returns a set of regions the item belongs to: {"US"}, {"EU"}, or both.
    For explicit-region sources, trust the tag.
    For GLOBAL sources, scan text for signals.
    """
    if source_region in ("US", "EU"):
        return {source_region}

    text = f"{title} {summary} {link}"
    regions = set()
    if US_SIGNALS.search(text):
        regions.add("US")
    if EU_SIGNALS.search(text):
        regions.add("EU")
    return regions


# ---------------------------------------------------------------
# CATEGORIZATION
# ---------------------------------------------------------------

def categorize(title, summary=""):
    t = f"{title} {summary}".lower()
    if any(x in t for x in ["agentic", "ai agent", "copilot", "autonomous agent"]):
        return "Agentic Finance"
    if any(x in t for x in ["crypto", "bitcoin", "ethereum", "token", "blockchain",
                            "stablecoin", "defi", "web3"]):
        return "Crypto"
    return "Traditional Finance"


def event_type(title):
    t = title.lower()
    if PARTNERSHIP_RE.search(title):
        return "🤝 Partnership"
    if "integrat" in t or "api" in t or "sdk" in t:
        return "🔌 Integration"
    if any(x in t for x in ["etf", "fund", "index"]):
        return "🏦 Fund / ETF"
    if any(x in t for x in ["ai ", "agent", "copilot", "llm"]):
        return "🧠 AI"
    return "🚀 Product Launch"


# ---------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------

def score(item):
    s = 0
    s += {1: 5, 2: 3, 3: 1}.get(item["tier"], 0)

    text = f"{item['title']} {item.get('summary', '')}".lower()
    s += len(LAUNCH_VERB_RE.findall(text))
    if PARTNERSHIP_RE.search(text):
        s += 2

    # Recency decay: newer = better
    if item.get("published"):
        age_hours = (datetime.now(timezone.utc) - item["published"]).total_seconds() / 3600
        s -= age_hours * 0.05  # gentle decay

    return s


# ---------------------------------------------------------------
# LINK VALIDATION (HEAD with GET fallback)
# ---------------------------------------------------------------

def is_valid_link(url):
    for method in ("head", "get"):
        try:
            r = requests.request(
                method, url,
                timeout=8,
                allow_redirects=True,
                headers=HEADERS,
                stream=True,
            )
            if r.status_code < 400:
                return True
        except requests.RequestException:
            continue
    return False


# ---------------------------------------------------------------
# FETCH
# ---------------------------------------------------------------

def fetch_all():
    health = load_json(HEALTH_FILE, {})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    items = []

    for name, url, region, tier in SOURCES:
        if is_source_blocked(health, name):
            log.info("Skipping %s (consecutive failures)", name)
            continue

        try:
            feed = feedparser.parse(url, request_headers=HEADERS)
            if feed.bozo and not feed.entries:
                raise RuntimeError(f"feedparser error: {feed.bozo_exception}")

            fetched = 0
            for e in feed.entries:
                title = clean(e.get("title"))
                link = e.get("link")
                summary = clean(BeautifulSoup_like_strip(e.get("summary", "")))

                if not title or not link:
                    continue

                published = entry_datetime(e)
                if published and published < cutoff:
                    continue

                if not is_real_launch(title, summary):
                    continue

                regions = detect_region(title, summary, link, region)
                if not regions:
                    # GLOBAL source, no US or EU signal — skip
                    continue

                items.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "source": name,
                    "tier": tier,
                    "regions": regions,
                    "published": published,
                })
                fetched += 1

            log.info("✓ %s — %d matching items", name, fetched)
            update_health(health, name, True)

        except Exception as exc:
            log.warning("✗ %s failed: %s", name, exc)
            update_health(health, name, False)

    save_json(HEALTH_FILE, health)
    return items


def BeautifulSoup_like_strip(html_text):
    """Small HTML-strip without requiring BeautifulSoup."""
    return re.sub(r"<[^>]+>", "", html_text or "")


# ---------------------------------------------------------------
# MESSAGE BUILDING (HTML format for Telegram)
# ---------------------------------------------------------------

def esc(s):
    return html.escape(s or "", quote=False)


def build_item_block(idx, item):
    summary = item.get("summary", "").strip()
    # Trim to ~220 chars for Telegram readability
    if len(summary) > 220:
        summary = summary[:220].rsplit(" ", 1)[0] + "…"
    why = summary or "New product or market development."

    return (
        f"{idx}. {event_type(item['title'])}\n"
        f"<a href=\"{esc(item['link'])}\">{esc(item['title'])}</a>\n"
        f"<i>Why it matters:</i> {esc(why)}\n"
        f"<i>Source:</i> {esc(item['source'])}\n\n"
    )


def build_messages(region_name, items):
    """Build one or more Telegram messages for a region, splitting on item boundaries."""
    if not items:
        return []

    today = datetime.now().strftime("%b %d")
    header = f"<b>Daily Fintech Radar — {region_name} — {today}</b>\n\n"

    grouped = {"Traditional Finance": [], "Crypto": [], "Agentic Finance": []}
    for i in items:
        grouped[categorize(i["title"], i.get("summary", ""))].append(i)

    messages = []
    current = header
    idx = 1

    for cat, arr in grouped.items():
        if not arr:
            continue
        section_header = f"<b>{cat}</b>\n\n"
        if len(current) + len(section_header) > TELEGRAM_LIMIT:
            messages.append(current)
            current = header + section_header
        else:
            current += section_header

        for item in arr:
            block = build_item_block(idx, item)
            if len(current) + len(block) > TELEGRAM_LIMIT:
                messages.append(current)
                current = header + f"<b>{cat} (cont.)</b>\n\n" + block
            else:
                current += block
            idx += 1

    if current.strip() and current != header:
        messages.append(current)

    return messages


# ---------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------

def send(messages):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Telegram credentials not set; skipping send")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for msg in messages:
        try:
            r = requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            if r.status_code != 200:
                log.warning("Telegram responded %d: %s", r.status_code, r.text[:200])
            time.sleep(1)  # stay polite with Telegram's rate limit
        except requests.RequestException as exc:
            log.error("Telegram send failed: %s", exc)


# ---------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------

def main():
    seen = set(load_json(STATE_FILE, []))
    log.info("Loaded %d seen IDs", len(seen))

    items = fetch_all()
    log.info("Fetched %d candidate items", len(items))

    # filter already-seen
    items = [i for i in items if make_id(i["link"]) not in seen]
    log.info("%d items after dedup vs. seen", len(items))

    # dedupe within this run (by normalized URL)
    unique = {}
    for i in items:
        unique.setdefault(make_id(i["link"]), i)
    items = list(unique.values())

    # score & sort
    for i in items:
        i["score"] = score(i)
    items.sort(key=lambda x: -x["score"])

    # split by region, take top N each, validate links
    per_region = {"US": [], "EU": []}
    for i in items:
        for r in i["regions"]:
            if r in per_region and len(per_region[r]) < TOP_N_PER_REGION * 2:
                per_region[r].append(i)

    final = {}
    for region, arr in per_region.items():
        validated = []
        for item in arr:
            if len(validated) >= TOP_N_PER_REGION:
                break
            if is_valid_link(item["link"]):
                validated.append(item)
        final[region] = validated
        log.info("%s: %d items after link validation", region, len(validated))

    # send, one region at a time
    for region_name, label in (("US", "🇺🇸 US"), ("EU", "🇪🇺 Europe")):
        msgs = build_messages(label, final[region_name])
        if msgs:
            log.info("Sending %d message(s) for %s", len(msgs), region_name)
            send(msgs)

    # update seen and trim
    for region_items in final.values():
        for i in region_items:
            seen.add(make_id(i["link"]))
    if len(seen) > MAX_SEEN_ENTRIES:
        # arbitrary trim — keep most recent half
        seen = set(list(seen)[-MAX_SEEN_ENTRIES // 2:])
    save_json(STATE_FILE, list(seen))
    log.info("Saved %d seen IDs", len(seen))


if __name__ == "__main__":
    main()
