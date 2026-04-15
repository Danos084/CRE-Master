# Bayside Commercial Listings Agent

Automated scraper, report builder, and emailer for commercial lease listings
across the **Bayside & Logan Corridor** in Queensland.

**Coverage:** Morningside → Wynnum → Wellington Point → Cleveland → Redland Bay  
→ Loganholme → Browns Plains → Woodridge → Slacks Creek → Morningside

**Sources:** realcommercial.com.au · commercialrealestate.com.au  
**Output:** Excel workbook + PowerPoint report → emailed to daniel.fahey@precisionprop.com.au  
**Schedule:** Weekly full scrape (Monday) + daily refresh (7 AM AEST)

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator – call this to run |
| `scraper.py` | Playwright-based web scraper |
| `excel_builder.py` | Builds the .xlsx workbook |
| `pptx_builder.py` | Builds the branded .pptx report |
| `emailer.py` | Gmail SMTP dispatcher |
| `requirements.txt` | Python dependencies |
| `.github/workflows/agent.yml` | GitHub Actions schedule |

---

## Quick Start (Local)

```bash
# 1. Clone / copy this folder
cd bayside_commercial_agent

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Set Gmail App Password
cp .env.example .env
# Edit .env → paste your App Password

# 4. Full weekly run
python main.py --mode weekly

# 5. Daily refresh (uses cached data)
python main.py --mode daily
```

---

## Deploy to GitHub Actions (Recommended)

1. Push this folder to a GitHub repo
2. Go to **Settings → Secrets → Actions**
3. Add secret: `GMAIL_APP_PASSWORD` = your 16-char App Password
4. The workflow runs automatically:
   - **Monday 6 AM AEST** → full scrape + email
   - **Daily 7 AM AEST** → refresh + email

---

## Gmail App Password Setup

propsolagent@gmail.com must have 2-Step Verification enabled.

1. Visit [myaccount.google.com](https://myaccount.google.com) → Security
2. Enable **2-Step Verification** (if not already on)
3. Search for **"App passwords"**
4. Create one: App = Mail, Device = your choice
5. Copy the 16-character password → paste into `.env` or GitHub Secret

---

## Data

Listings are stored in `data/listings.json` as a flat key→value dict.  
Each key is `"address|source"`. Fields:

- `address`, `suburb`, `type`, `size`
- `asking_rental`, `listing_agent`
- `link`, `source`
- `first_seen` (YYYY-MM-DD), `last_updated` (YYYY-MM-DD)

The Excel workbook has three sheets:
- **Summary** – key stats
- **All Listings** – full dataset, filterable
- **New This Week** – listings first seen in last 7 days

---

## Notes on Scraping

Both sites use React/dynamic rendering. The scraper uses Playwright (Chromium)
with realistic delays and user-agent strings. If a site updates its HTML
structure, update the CSS selectors in `scraper.py` (`_parse_rc_card` /
`_parse_cre_card`). The scraper is designed to degrade gracefully — missing
fields are left blank rather than crashing.

---

*Precision Property | precisionprop.com.au | 0432 203 354*
