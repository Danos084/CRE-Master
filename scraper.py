"""
Bayside Commercial Listings Scraper
Scrapes realcommercial.com.au and commercialrealestate.com.au
for lease listings across the Bayside / Logan corridor.
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

# ── Target suburbs ────────────────────────────────────────────────────────────
SUBURBS = [
    # Eastern Bayside corridor
    "Morningside", "Murarrie", "Tingalpa", "Wynnum", "Manly",
    "Birkdale", "Wellington Point", "Ormiston", "Cleveland",
    "Alexandra Hills", "Capalaba", "Redland Bay", "Victoria Point",
    # Southern Logan corridor
    "Loganholme", "Shailer Park", "Tanah Merah", "Springwood",
    "Daisy Hill", "Slacks Creek", "Woodridge", "Logan Central",
    "Underwood", "Rochedale South", "Rochedale",
    # Browns Plains pocket
    "Browns Plains", "Berrinba", "Parkinson",
    # Logan central precinct additions
    "Meadowbrook", "Kingston",
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


# ── realcommercial.com.au scraper ─────────────────────────────────────────────

def scrape_realcommercial(page, suburb: str) -> list:
    results = []
    slug = suburb.lower().replace(" ", "-")
    url = f"https://www.realcommercial.com.au/lease/{slug}-{STATE.lower()}-4000/"

    # realcommercial uses different URL patterns – we try a search fallback too
    search_url = (
        f"https://www.realcommercial.com.au/search?suburb={suburb.replace(' ', '+')}"
        f"&state={STATE}&channel=lease"
    )

    for attempt_url in [url, search_url]:
        try:
            log.info(f"  RC → {attempt_url}")
            page.goto(attempt_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(2000, 3500))

            # Accept cookie banner if present
            try:
                page.click("button:has-text('Accept')", timeout=3000)
            except Exception:
                pass

            # Wait for listing cards
            page.wait_for_selector("[data-testid='listing-card'], .listing-card, article.listing", timeout=15000)

            cards = page.query_selector_all(
                "[data-testid='listing-card'], .listing-card, article.listing, div[class*='ListingCard']"
            )
            log.info(f"    Found {len(cards)} cards")

            for card in cards[:50]:
                try:
                    listing = _parse_rc_card(card, suburb)
                    if listing:
                        results.append(listing)
                except Exception as e:
                    log.debug(f"    Card parse error: {e}")

            if results:
                break  # got data from first URL, skip fallback

        except PWTimeout:
            log.warning(f"    Timeout on {attempt_url}")
        except Exception as e:
            log.warning(f"    Error on {attempt_url}: {e}")

    return results


def _parse_rc_card(card, suburb: str) -> dict | None:
    def txt(sel):
        el = card.query_selector(sel)
        return el.inner_text().strip() if el else ""

    # Address
    address = (
        txt("[data-testid='listing-card-address']")
        or txt(".listing-address")
        or txt("[class*='address']")
    )
    if not address:
        return None

    # Size
    size = (
        txt("[data-testid='listing-card-property-features'] span:has-text('m²')")
        or txt("[class*='floorArea']")
        or txt("[class*='size']")
        or ""
    )

    # Type / category
    prop_type = (
        txt("[data-testid='listing-card-type']")
        or txt("[class*='propertyType']")
        or txt("[class*='type']")
        or ""
    )

    # Price / rent
    price = (
        txt("[data-testid='listing-card-price']")
        or txt("[class*='price']")
        or txt("[class*='rent']")
        or "POA"
    )

    # Agent
    agent = (
        txt("[data-testid='listing-card-agent-name']")
        or txt("[class*='agentName']")
        or txt("[class*='agent']")
        or ""
    )

    # Link
    link_el = card.query_selector("a[href]")
    link = ""
    if link_el:
        href = link_el.get_attribute("href") or ""
        link = href if href.startswith("http") else f"https://www.realcommercial.com.au{href}"

    return {
        "address": address,
        "suburb": suburb,
        "size": size,
        "type": prop_type,
        "asking_rental": price,
        "listing_agent": agent,
        "link": link,
        "source": "realcommercial.com.au",
        "first_seen": datetime.today().strftime("%Y-%m-%d"),
        "last_updated": datetime.today().strftime("%Y-%m-%d"),
    }


# ── commercialrealestate.com.au scraper ───────────────────────────────────────

def scrape_cre(page, suburb: str) -> list:
    results = []
    slug = suburb.lower().replace(" ", "-")
    url = (
        f"https://www.commercialrealestate.com.au/lease/"
        f"{slug}-{STATE.lower()}-4000/"
    )
    search_url = (
        f"https://www.commercialrealestate.com.au/search?q={suburb.replace(' ', '+')}"
        f"+{STATE}&channel=lease"
    )

    for attempt_url in [url, search_url]:
        try:
            log.info(f"  CRE → {attempt_url}")
            page.goto(attempt_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(random.randint(2000, 3500))

            try:
                page.click("button:has-text('Accept'), button:has-text('OK')", timeout=3000)
            except Exception:
                pass

            page.wait_for_selector(
                "[data-testid='listing-card'], .listing-result, article, div[class*='ListingCard']",
                timeout=15000
            )

            cards = page.query_selector_all(
                "[data-testid='listing-card'], .listing-result, "
                "div[class*='ListingCard'], div[class*='listing-card']"
            )
            log.info(f"    Found {len(cards)} cards")

            for card in cards[:50]:
                try:
                    listing = _parse_cre_card(card, suburb)
                    if listing:
                        results.append(listing)
                except Exception as e:
                    log.debug(f"    Card parse error: {e}")

            if results:
                break

        except PWTimeout:
            log.warning(f"    Timeout on {attempt_url}")
        except Exception as e:
            log.warning(f"    Error on {attempt_url}: {e}")

    return results


def _parse_cre_card(card, suburb: str) -> dict | None:
    def txt(sel):
        el = card.query_selector(sel)
        return el.inner_text().strip() if el else ""

    address = (
        txt("[class*='address']")
        or txt("h2")
        or txt("h3")
    )
    if not address:
        return None

    size = txt("[class*='area'], [class*='size'], span:has-text('m²')")
    prop_type = txt("[class*='type'], [class*='category']")
    price = txt("[class*='price'], [class*='rent']") or "POA"
    agent = txt("[class*='agent'], [class*='Agent']")

    link_el = card.query_selector("a[href]")
    link = ""
    if link_el:
        href = link_el.get_attribute("href") or ""
        link = href if href.startswith("http") else f"https://www.commercialrealestate.com.au{href}"

    return {
        "address": address,
        "suburb": suburb,
        "size": size,
        "type": prop_type,
        "asking_rental": price,
        "listing_agent": agent,
        "link": link,
        "source": "commercialrealestate.com.au",
        "first_seen": datetime.today().strftime("%Y-%m-%d"),
        "last_updated": datetime.today().strftime("%Y-%m-%d"),
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

        for suburb in SUBURBS:
            log.info(f"Scraping suburb: {suburb}")
            all_found = []

            all_found.extend(scrape_realcommercial(page, suburb))
            time.sleep(random.uniform(1.5, 3.0))
            all_found.extend(scrape_cre(page, suburb))
            time.sleep(random.uniform(1.5, 3.0))

            for listing in all_found:
                key = dedupe_key(listing)
                if key not in existing:
                    existing[key] = listing
                    new_count += 1
                else:
                    existing[key]["last_updated"] = today
                    # Refresh mutable fields
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
