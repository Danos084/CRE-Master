"""
Bayside Commercial Listings Scraper
Scrapes commercialrealestate.com.au for both lease AND sale listings
across the Bayside / Logan corridor in Queensland.

URL format: https://www.commercialrealestate.com.au/for-lease/{stringId}/
            https://www.commercialrealestate.com.au/for-sale/{stringId}/
Selectors confirmed via live DOM inspection.
"""

import json
import time
import random
import logging
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUBURBS = [
    ("Morningside",     "morningside-qld-4170"),
    ("Murarrie",        "murarrie-qld-4172"),
    ("Tingalpa",        "tingalpa-qld-4173"),
    ("Wynnum",          "wynnum-qld-4178"),
    ("Manly",           "manly-qld-4179"),
    ("Birkdale",        "birkdale-qld-4159"),
    ("Wellington Point","wellington-point-qld-4160"),
    ("Ormiston",        "ormiston-qld-4160"),
    ("Cleveland",       "cleveland-qld-4163"),
    ("Alexandra Hills", "alexandra-hills-qld-4161"),
    ("Capalaba",        "capalaba-qld-4157"),
    ("Redland Bay",     "redland-bay-qld-4165"),
    ("Victoria Point",  "victoria-point-qld-4165"),
    ("Loganholme",      "loganholme-qld-4129"),
    ("Shailer Park",    "shailer-park-qld-4128"),
    ("Tanah Merah",     "tanah-merah-qld-4128"),
    ("Springwood",      "springwood-qld-4127"),
    ("Daisy Hill",      "daisy-hill-qld-4127"),
    ("Slacks Creek",    "slacks-creek-qld-4127"),
    ("Woodridge",       "woodridge-qld-4114"),
    ("Logan Central",   "logan-central-qld-4114"),
    ("Underwood",       "underwood-qld-4119"),
    ("Rochedale South", "rochedale-south-qld-4123"),
    ("Rochedale",       "rochedale-qld-4123"),
    ("Browns Plains",   "browns-plains-qld-4118"),
    ("Berrinba",        "berrinba-qld-4117"),
    ("Parkinson",       "parkinson-qld-4115"),
    ("Meadowbrook",     "meadowbrook-qld-4131"),
    ("Kingston",        "kingston-qld-4114"),
]

LISTING_TYPES = [
    ("for-lease", "Lease"),
    ("for-sale",  "Sale"),
]

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LISTINGS_FILE   = DATA_DIR / "listings.json"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


def load_existing() -> dict:
    if LISTINGS_FILE.exists():
        with open(LISTINGS_FILE) as f:
            return json.load(f)
    return {}


def save_listings(data: dict):
    with open(LISTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def dedupe_key(listing: dict) -> str:
    return (
        f"{listing.get('address','').lower().strip()}"
        f"|{listing.get('listing_type','')}"
        f"|{listing.get('source','')}"
    )


STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-AU', 'en-US', 'en'] });
window.chrome = { runtime: {} };
const _origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : _origQuery(p)
);
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
"""


def scrape_suburb(page, suburb, string_id, url_type, listing_type, take_screenshot=False):
    results = []
    url = f"https://www.commercialrealestate.com.au/{url_type}/{string_id}/"
    today = datetime.today().strftime("%Y-%m-%d")
    try:
        log.info(f"  [{listing_type}] -> {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(random.randint(3000, 5000))
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            log.info(f"    networkidle timed out for {suburb} ({listing_type}), continuing")
        for btn_text in ["Accept all", "Accept", "OK", "I agree", "Got it"]:
            try:
                page.click(f"button:has-text('{btn_text}')", timeout=2000)
                page.wait_for_timeout(500)
                break
            except Exception:
                pass
        if take_screenshot:
            try:
                shot_path = SCREENSHOTS_DIR / f"{url_type}-{string_id}.png"
                page.screenshot(path=str(shot_path), full_page=False)
                log.info(f"    Screenshot: {shot_path}")
            except Exception as e:
                log.warning(f"    Screenshot failed: {e}")
        try:
            log.info(f"    Page title: {page.title()}")
        except Exception:
            pass
        try:
            page.wait_for_selector('[data-testid^="search-card-"]', timeout=20000)
        except PWTimeout:
            try:
                page.wait_for_selector('[class*="searchCard"]', timeout=5000)
                log.info(f"    Found cards via class selector fallback")
            except PWTimeout:
                log.warning(f"    No cards for {suburb} ({listing_type}) - may be blocked/empty")
                try:
                    log.info(f"    Page snippet: {page.inner_text('body')[:500]!r}")
                except Exception:
                    pass
                return []
        page_num = 1
        while True:
            cards = page.query_selector_all('[data-testid^="search-card-"]')
            log.info(f"    Page {page_num}: {len(cards)} cards")
            for card in cards:
                listing = _parse_card(card, suburb, listing_type, today)
                if listing:
                    results.append(listing)
            try:
                next_btn = page.query_selector('[data-testid="paginator-navigation-button-next"]:not([disabled])')
                if next_btn and page_num < 5:
                    next_btn.click()
                    page.wait_for_timeout(random.randint(2500, 4000))
                    page.wait_for_selector('[data-testid^="search-card-"]', timeout=15000)
                    page_num += 1
                else:
                    break
            except Exception:
                break
        log.info(f"    Total for {suburb} ({listing_type}): {len(results)}")
    except PWTimeout:
        log.warning(f"    Timeout loading {url}")
    except Exception as e:
        log.warning(f"    Error scraping {suburb} ({listing_type}): {e}")
    return results


def _parse_card(card, suburb, listing_type, today):
    def get(testid):
        try:
            el = card.query_selector(f'[data-testid="{testid}"]')
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""
    address = get("address")
    if not address:
        return None
    link = ""
    try:
        link_el = card.query_selector('[data-testid="address"]')
        if link_el:
            link = link_el.get_attribute("href") or ""
            if link and not link.startswith("http"):
                link = f"https://www.commercialrealestate.com.au{link}"
    except Exception:
        pass
    return {
        "address":         address,
        "suburb":          suburb,
        "listing_type":    listing_type,
        "size":            get("area-size"),
        "type":            get("main-category"),
        "price_or_rental": get("price") or "Contact Agent",
        "listing_agent":   get("agent-names"),
        "link":            link,
        "source":          "commercialrealestate.com.au",
        "first_seen":      today,
        "last_updated":    today,
    }


def run_scrape(headless=True):
    existing = load_existing()
    today = datetime.today().strftime("%Y-%m-%d")
    new_count = updated_count = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-accelerated-2d-canvas",
                "--no-first-run", "--no-zygote", "--disable-gpu",
            ]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-AU",
            timezone_id="Australia/Brisbane",
            java_script_enabled=True,
            accept_downloads=False,
            extra_http_headers={
                "Accept-Language": "en-AU,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()
        try:
            log.info("Visiting homepage to establish session...")
            page.goto("https://www.commercialrealestate.com.au/",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(2000, 3500))
            log.info(f"  Homepage title: {page.title()}")
        except Exception as e:
            log.warning(f"  Homepage visit failed: {e}")
        for url_type, listing_type in LISTING_TYPES:
            log.info(f"\n{'='*60}")
            log.info(f"Starting {listing_type.upper()} listings scrape")
            log.info(f"{'='*60}")
            first_suburb = True
            for suburb, string_id in SUBURBS:
                log.info(f"Scraping [{listing_type}]: {suburb} ({string_id})")
                found = scrape_suburb(
                    page, suburb, string_id, url_type, listing_type,
                    take_screenshot=first_suburb,
                )
                first_suburb = False
                time.sleep(random.uniform(3.0, 6.0))
                for listing in found:
                    key = dedupe_key(listing)
                    if key not in existing:
                        existing[key] = listing
                        new_count += 1
                    else:
                        existing[key]["last_updated"] = today
                        for field in ("price_or_rental", "listing_agent", "size", "type"):
                            if listing.get(field):
                                existing[key][field] = listing[field]
                        updated_count += 1
        browser.close()
    save_listings(existing)
    lease_total = sum(1 for v in existing.values() if v.get("listing_type") == "Lease")
    sale_total  = sum(1 for v in existing.values() if v.get("listing_type") == "Sale")
    log.info(
        f"Done. New: {new_count} | Updated: {updated_count} | "
        f"Total: {len(existing)} (Lease: {lease_total}, Sale: {sale_total})"
    )
    return existing


if __name__ == "__main__":
    run_scrape(headless=True)
