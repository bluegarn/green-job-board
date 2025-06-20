# config.py

# === Target site ===
TARGET_URL = "https://www.foundit.in/job"

# === CSS Selectors ===
TITLE_SELECTOR = "div.text-content-primary.md\\!text-2xl"
COMPANY_SELECTOR = "div.text-content-secondary.md\\!text-content-primary span"
LOCATION_SELECTOR = "div.text-content-primary.flex.gap-4 a"
DESCRIPTION_SELECTOR = "#jobDescription"

# === HTTP Headers (user agent pool) ===
HEADERS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Edge/109.0.1518.78",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:108.0) Gecko/20100101 Firefox/108.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
]

# === Scraper Behaviour ===
MAX_JOBS = 3  # limit jobs for testing; set to None to scrape all
