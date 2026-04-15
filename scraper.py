"""
Bayside Commercial Listings Scraper
Scrapes commercialrealestate.com.au for lease listings
across the Bayside / Logan corridor in Queensland.
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

# ── Target suburbs with correct postcodes ─────────────────────────────────────
SUBURBS = [
    # Eastern Bayside corridor
    ("Morningside",     "4170"),
    ("Murarrie",        "4172"),
    ("Tingalpa",        "4173"),
    ("Wynnum",          "4178"),
    ("Manly",           "4179"),
    ("Birkdale",        "4159"),
    ("Wellington Point","4160"),
    ("Ormiston",        "4160"),
    ("Cleveland",       "4163"),
    ("Alexandra Hills", "4161"),
    ("Capalaba",        "4157"),
    ("Redland Bay",     "4165"),
    ("Victoria Point",  "4165"),
    # Southern Logan corridor
    ("Loganholme",      "4129"),
    ("Shailer Park",    "4128"),
    ("Tanah Merah",     "4128"),
    ("Springwood",      "4127"),
    ("Daisy Hill",      "4127"),
    ("Slacks Creek",    "4127"),
    ("Woodridge",       "4114"),
    ("Logan Central",   "4114"),
    ("Underwood",       "4119"),
    ("Rochedale South", "4123"),
    ("Rochedale",       "4123"),
    # Browns Plains pocket
    ("Browns Plains",   "4118"),
    ("Berrinba",        "4117"),
    ("Parkinson",       "4115"),
    # Logan central precinct
    ("Meadowbrook",     "4131"),
    ("Kingston",        "4114"),
]

STATE = "QLD"
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


# ── commercialrealestate.com.au scraper ───────────────────────────────────────

def scrape_cre(page, suburb: str, postcode: str) -> list:
    results = []
    slug = suburb.lower().replace(" ", "-")

    # Try direct suburb/postcode URL first, then search fallback
    urls = [
        f"https://www.commercialrealestate.com.au/lease/{slug}-{STATE.lower()}-{postcode}/",
        f"https://www.commercialrealestate.com.au/lease/?q={suburb.replace(' ', '+')}+{postcode}+{STATE}&channel=lease",
        f"https://www.commercialrealestate.com.au/lease/?suburb={suburb.replace(' ', '+')}&state={STATE}",
    ]

    for attempt_url in urls:
        try:
            log.info(f"  CRE → {attempt_url}")
            page.goto(attempt_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(2500, 4000))

            # Dismiss cookie / consent banners
            for btn_text in ["Accept", "Accept all", "OK", "Close", "I agree"]:
                try:
                    page.click(f"button:has-text('{btn_text}')", timeout=2000)
                    page.wait_for_timeout(500)
                    break
                except Exception:
                    pass

            # Wait for any listing content to appear
            try:
                page.wait_for_selector(
                    "[data-testid='listing-card'], "
                    "div[class*='ListingCard'], "
                    "div[class*='listing-card'], "
                    "div[class*='propertyList'] > div, "
                    "ul[class*='results'] li, "
                    "article",
                    timeout=12000
                )
            except PWTimeout:
                log.warning(f"    No listing cards found on {attempt_url}")
                continue

            # Grab all candidate card elements
            card_selectors = [
                "[data-testid='listing-card']",
                "div[class*='ListingCard']",
                "div[class*='listing-card']",
                "article[class*='listing']",
                "div[class*='property-card']",
                "div[class*='PropertyCard']",
            ]
            cards = []
            for sel in card_selectors:
                cards = page.query_selector_all(sel)
                if cards:
                    log.info(f"    Selector '{sel}' matched {len(cards)} cards")
                    break

            if not cards:
                log.warning(f"    0 cards matched any selector on {attempt_url}")
                continue

            for card in cards[:50]:
                try:
                    listing = _parse_cre_card(card, suburb)
                    if listing:
                        results.append(listing)
                except Exception as e:
                    log.debug(f"    Card parse error: {e}")

            log.info(f"    Parsed {len(results)} listings for {suburb}")

            if results:
                break  # Got data — skip remaining URL attempts

        except PWTimeout:
            log.warning(f"    Timeout on {attempt_url}")
        except Exception as e:
            log.warning(f"    Error on {attempt_url}: {e}")

    return results


def _parse_cre_card(card, suburb: str) -> dict | None:
    def txt(*selectors):
        for sel in selectors:
            try:
                el = card.query_selector(sel)
                if el:
                    val = el.inner_text().strip()
                    if val:
                        return val
            except Exception:
                pass
        return ""

    # Address — try many likely selectors
    address = txt(
        "[data-testid='listing-card-address']",
        "[class*='address']",
        "[class*='Address']",
        "h2", "h3", "h4",
        "[class*='title']",
        "[class*='Title']",
    )
    if not address:
        return None

    size = txt(
        "[class*='area']", "[class*='Area']",
        "[class*='size']", "[class*='Size']",
        "[class*='floor']", "[class*='Floor']",
        "span:has-text('m²')",
    )

    prop_type = txt(
        "[class*='type']", "[class*='Type']",
        "[class*='category']", "[class*='Category']",
        "[class*='propertyType']",
    )

    price = txt(
        "[class*='price']", "[class*='Price']",
        "[class*='rent']",  "[class*='Rent']",
        "[data-testid='listing-card-price']",
    ) or "POA"

    agent = txt(
        "[class*='agent']",  "[class*='Agent']",
        "[class*='agency']", "[class*='Agency']",
        "[class*='contact']",
    )

    # Link
    link = ""
    try:
        link_el = card.query_selector("a[href]")
        if link_el:
            href = link_el.get_attribute("href") or ""
            link = href if href.startswith("http") else f"https://www.commercialrealestate.com.au{href}"
    except Exception:
        pass

    return {
        "address":        address,
        "suburb":         suburb,
        "size":           size,
        "type":           prop_type,
        "asking_rental":  price,
        "listing_agent":  agent,
        "link":           link,
        "source":         "commercialrealestate.com.au",
        "first_seen":     datetime.today().strftime("%Y-%m-%d"),
        "last_updated":   datetime.today().strftime("%Y-%m-%d"),
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

        for suburb, postcode in SUBURBS:
            log.info(f"Scraping suburb: {suburb} ({postcode})")
            found = scrape_cre(page, suburb, postcode)
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
