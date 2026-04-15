"""
Bayside Commercial Listings Scraper
Scrapes commercialrealestate.com.au for lease listings
across the Bayside / Logan corridor in Queensland.

URL format confirmed: https://www.commercialrealestate.com.au/for-lease/{stringId}/
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

# ── Suburbs with confirmed CRE stringIds ─────────────────────────────────────
# stringIds sourced from the /bf/api/suggestions endpoint
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

BASE_URL = "https://www.commercialrealestate.com.au/for-lease"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
LISTINGS_FILE = DATA_DIR / "listings.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_existing() -> dict:
    if LISTINGS_FILE.exists():
        with open(LISTINGS_FILE) as f:
            return json.load(f)
    return {}


def save_listings(data: dict):
    with open(LISTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def dedupe_key(listing: dict) -> str:
    return f"{listing.get('address','').lower().strip()}|{listing.get('source','')}"


# ── Scraper ───────────────────────────────────────────────────────────────────

def scrape_suburb(page, suburb: str, string_id: str) -> list:
    """
    Scrape all lease listings for one suburb from commercialrealestate.com.au.

    URL format: https://www.commercialrealestate.com.au/for-lease/{stringId}/
    Confirmed selectors (stable data-testid attributes):
      Cards:   [data-testid^="search-card-"]
      Address: [data-testid="address"]  (innerText = address, href = link)
      Price:   [data-testid="price"]
      Size:    [data-testid="area-size"]
      Type:    [data-testid="main-category"]
      Agent:   [data-testid="agent-names"]
    """
    results = []
    url = f"{BASE_URL}/{string_id}/"
    today = datetime.today().strftime("%Y-%m-%d")

    try:
        log.info(f"  → {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(random.randint(2000, 3500))

        # Dismiss any cookie / consent banners
        for btn_text in ["Accept all", "Accept", "OK", "I agree"]:
            try:
                page.click(f"button:has-text('{btn_text}')", timeout=1500)
                page.wait_for_timeout(300)
                break
            except Exception:
                pass

        # Wait for listing cards to appear
        try:
            page.wait_for_selector('[data-testid^="search-card-"]', timeout=15000)
        except PWTimeout:
            log.warning(f"    No listing cards found for {suburb}")
            return []

        # Collect all pages of results
        page_num = 1
        while True:
            cards = page.query_selector_all('[data-testid^="search-card-"]')
            log.info(f"    Page {page_num}: {len(cards)} cards")

            for card in cards:
                listing = _parse_card(card, suburb, today)
                if listing:
                    results.append(listing)

            # Check for next page
            try:
                next_btn = page.query_selector('[data-testid="paginator-navigation-button-next"]:not([disabled])')
                if next_btn and page_num < 5:  # Cap at 5 pages per suburb
                    next_btn.click()
                    page.wait_for_timeout(random.randint(2000, 3000))
                    page.wait_for_selector('[data-testid^="search-card-"]', timeout=10000)
                    page_num += 1
                else:
                    break
            except Exception:
                break

        log.info(f"    Total for {suburb}: {len(results)} listings")

    except PWTimeout:
        log.warning(f"    Timeout loading {url}")
    except Exception as e:
        log.warning(f"    Error scraping {suburb}: {e}")

    return results


def _parse_card(card, suburb: str, today: str) -> dict | None:
    def get(testid):
        try:
            el = card.query_selector(f'[data-testid="{testid}"]')
            return el.inner_text().strip() if el else ""
        except Exception:
            return ""

    address = get("address")
    if not address:
        return None

    # Link comes from the href on the address element
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
        "address":       address,
        "suburb":        suburb,
        "size":          get("area-size"),
        "type":          get("main-category"),
        "asking_rental": get("price") or "Contact Agent",
        "listing_agent": get("agent-names"),
        "link":          link,
        "source":        "commercialrealestate.com.au",
        "first_seen":    today,
        "last_updated":  today,
    }


# ── Main run ──────────────────────────────────────────────────────────────────

def run_scrape(headless: bool = True) -> dict:
    existing = load_existing()
    today = datetime.today().strftime("%Y-%m-%d")
    new_count = updated_count = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()

        for suburb, string_id in SUBURBS:
            log.info(f"Scraping: {suburb} ({string_id})")
            found = scrape_suburb(page, suburb, string_id)
            time.sleep(random.uniform(2.0, 4.0))

            for listing in found:
                key = dedupe_key(listing)
                if key not in existing:
                    existing[key] = listing
                    new_count += 1
                else:
                    existing[key]["last_updated"] = today
                    for field in ("asking_rental", "listing_agent", "size", "type"):
                        if listing.get(field):
                            existing[key][field] = listing[field]
                    updated_count += 1

        browser.close()

    save_listings(existing)
    log.info(f"Done. New: {new_count} | Updated: {updated_count} | Total: {len(existing)}")
    return existing


if __name__ == "__main__":
    run_scrape(headless=True)
