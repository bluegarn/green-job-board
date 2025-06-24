# foundit_scraper.py

# Import necessary libraries
import config
import re
import json
import time
import random
import logging
# requests and urllib.robotparser are still imported but less used for primary fetching
import requests
import urllib.robotparser
from urllib.parse import urlparse, urljoin # Removed urlencode, parse_qs
from bs4 import BeautifulSoup
# Removed requests.adapters.HTTPAdapter, requests.exceptions.RequestException
from typing import List, Optional, Dict, Any

# NEW: Import Selenium modules
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.common.exceptions import WebDriverException, TimeoutException

from database_manager import SupabaseManager

# --- Configuration (loaded from config.py) ---
TARGET_URL = config.TARGET_URL
HEADERS = config.HEADERS
COMPANY_SELECTOR = config.COMPANY_SELECTOR
LOCATION_SELECTOR = config.LOCATION_SELECTOR
DESCRIPTION_SELECTOR = config.DESCRIPTION_SELECTOR
MAX_JOBS = config.MAX_JOBS
MAX_PAGES = config.MAX_PAGES
PAGINATION_BASE_PATH = config.PAGINATION_BASE_PATH
PAGINATION_START_PAGE = config.PAGINATION_START_PAGE
MAX_RETRIES = config.MAX_RETRIES

# A regular expression to find a specific JSON-LD 'ItemList' structure embedded in script tags.
_ITEMLIST_RE = re.compile(r'\[1,"(\{.*?\"itemListElement\".*?\})"\]\)', re.DOTALL)

# REMOVED: _SEARCH_IDS_SCRIPT_RE as it's no longer needed for pagination URLs

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def get_random_headers() -> Dict[str, str]:
    # This function is mostly for cosmetic use with Selenium options now.
    return {
        "User-Agent": random.choice(HEADERS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": TARGET_URL
    }

def get_robot_parser(base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(domain + "/robots.txt")
    try:
        rp.read()
        return rp
    except Exception as e:
        logging.warning(f"Could not fetch robots.txt from {domain}: {e}")
        return None

def fetch_with_selenium(driver: webdriver.Chrome, url: str) -> Optional[str]:
    """
    Fetches the content of a given URL using Selenium WebDriver.
    This function will load the page in a real browser context, allowing JavaScript to execute.
    It returns the fully rendered HTML content as a string.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"Selenium: Attempt {attempt}/{MAX_RETRIES} to load {url}")
            driver.get(url)
            
            # Add a reasonable implicit wait for dynamic content to load
            # This is a common practice with Selenium to wait for elements/JS
            driver.implicitly_wait(10) # Wait up to 10 seconds for elements to appear

            # Check if there was a 403. Selenium might not directly report HTTP status codes
            # for the primary navigation, but if the page content indicates a block, we can act.
            if "403 Forbidden" in driver.page_source or "Access Denied" in driver.page_source:
                logging.warning(f"Selenium: Detected potential 403/Access Denied on {url}. Retrying.")
                continue

            # Add a small explicit sleep after implicit wait to be safe, if needed
            time.sleep(random.uniform(3.0, 5.0)) # Shorter sleep after implicit wait

            return driver.page_source
        except TimeoutException:
            logging.error(f"Selenium: Navigation timeout for {url} (attempt {attempt}/{MAX_RETRIES}).")
        except WebDriverException as e:
            logging.error(f"Selenium: WebDriver error loading {url} (attempt {attempt}/{MAX_RETRIES}): {e}")
        except Exception as e:
            logging.error(f"Selenium: Unexpected error loading {url} (attempt {attempt}/{MAX_RETRIES}): {e}")
        time.sleep(2 ** attempt) # Exponential backoff for retries
    return None

def extract_job_list_urls(html: str) -> List[str]:
    # This function remains the same, but it will now receive HTML rendered by Selenium
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        for entry in (data if isinstance(data, list) else [data]):
            if isinstance(entry, dict) and entry.get("@type") == "ItemList":
                items = entry.get("itemListElement", [])
                urls = [item.get("url") for item in items if item.get("url")]
                if urls:
                    logging.info(f"Found {len(urls)} URLs via standard JSON-LD.")
                    return urls

    for script in soup.find_all("script"):
        text = script.string or ""
        if '"@type":"ItemList"' not in text:
            continue
        match = _ITEMLIST_RE.search(text)
        if not match:
            continue
        raw = match.group(1)
        try:
            payload = json.loads(raw.encode("utf-8").decode("unicode_escape"))
            items = payload.get("itemListElement", [])
            urls = [item.get("url") for item in items if item.get("url")]
            logging.info(f"Found {len(urls)} URLs via Next.js payload.")
            return urls
        except json.JSONDecodeError:
            continue
    logging.error("Could not locate any ItemList JSON-LD.")
    return []

def parse_job_posting(html: str, job_url: str) -> Optional[Dict[str, Any]]:
    # This function remains the same
    soup = BeautifulSoup(html, "html.parser")
    JOBPOST_RE = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)

    job = {
        "title": None,
        "company": None,
        "location": None,
        "description": None,
        "link": job_url
    }

    for script in JOBPOST_RE.findall(html):
        try:
            data = json.loads(script)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            job["title"] = data.get("title")
            job["company"] = data.get("hiringOrganization", {}).get("name")
            loc = data.get("jobLocation")
            location = None

            if isinstance(loc, list):
                locs = []
                for entry in loc:
                    if isinstance(entry, dict):
                        address = entry.get("address", {})
                        if isinstance(address, dict):
                            locality = address.get("addressLocality")
                            if locality:
                                locs.append(locality)
                job["location"] = ", ".join(locs) if locs else None
            elif isinstance(loc, dict):
                address = loc.get("address", {})
                if isinstance(address, dict):
                    job["location"] = address.get("addressLocality")

            job["description"] = data.get("description")
            break

    if not job["title"]:
        title_el = soup.select_one("div.text-content-primary.md\\!text-2xl")
        job["title"] = title_el.get_text(strip=True) if title_el else None
    if not job["company"]:
        comp_el = soup.select_one(COMPANY_SELECTOR)
        job["company"] = comp_el.get_text(strip=True) if comp_el else None
    if not job["location"]:
        locs = soup.select(LOCATION_SELECTOR)
        if locs:
            job["location"] = ", ".join([l.get_text(strip=True) for l in locs])

    if not job["description"]:
        desc_el = soup.select_one(DESCRIPTION_SELECTOR)
        if desc_el:
            job["description"] = str(desc_el)

    if job["description"]:
        description_soup = BeautifulSoup(job["description"], "html.parser")
        job["description"] = description_soup.get_text(separator=' ', strip=True)

    return job

def main() -> None:
    setup_logging()
    all_jobs: List[Dict[str, Any]] = []

    # --- Setup Selenium WebDriver ---
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless") # Run in headless mode (no visible browser window)
    chrome_options.add_argument("--no-sandbox") # Required for some environments, good practice
    chrome_options.add_argument("--disable-dev-shm-usage") # Required for some environments
    # Optional: Set a random User-Agent for the browser via options
    # This is less critical as Selenium mimics a real browser, but can be added.
    chrome_options.add_argument(f"user-agent={random.choice(HEADERS)}")

    # Specify the path to your ChromeDriver executable
    service = ChromeService(executable_path='./chromedriver.exe') # For Windows
    # For macOS/Linux, if executable_path='./chromedriver' (ensure it's executable)

    driver: Optional[webdriver.Chrome] = None
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        # Set an implicit wait globally for the driver to wait for elements
        driver.implicitly_wait(10) # Wait up to 10 seconds for elements to appear
        logging.info("Selenium WebDriver initialized successfully (Chromium).")
    except WebDriverException as e:
        logging.error(f"Failed to initialize Selenium WebDriver: {e}. Make sure ChromeDriver is in your project folder and matches your Chrome browser version.")
        return # Exit if driver fails to launch

    rp = get_robot_parser(config.TARGET_URL) # robots.txt check remains

    # --- Phase 1: Fetch the initial entry page using Selenium ---
    logging.info(f"Selenium: Fetching initial entry page: {config.TARGET_URL}")
    initial_page_html = fetch_with_selenium(driver, config.TARGET_URL) # Use Selenium fetch

    if not initial_page_html:
        logging.error("Failed to fetch initial entry page with Selenium, exiting.")
        driver.quit() # Close browser before exiting
        return

    # In this simplified pagination, we don't need to extract search_id or child_search_id
    # as they are not part of the sequential pagination URLs.
    # We directly process the first page's HTML.
    
    logging.info(f"Processing jobs from initial page: {driver.current_url}")

    job_urls_first_page = extract_job_list_urls(initial_page_html)
    if not job_urls_first_page:
        logging.warning("No job URLs found on the initial page (Selenium). This might indicate a problem with CSS selectors or dynamic content.")
    else:
        logging.info(f"Found {len(job_urls_first_page)} URLs on initial page.")
        for idx, url in enumerate(job_urls_first_page, start=1):
            full_url = url if url.startswith("http") else urljoin(driver.current_url, url) # Use current driver.current_url for base
            logging.info(f"[Page {config.PAGINATION_START_PAGE} - Job {idx}/{len(job_urls_first_page)}] Scraping {full_url}")

            job_page_html = fetch_with_selenium(driver, full_url)
            if not job_page_html:
                logging.warning(f"Failed to fetch job page {full_url} with Selenium. Skipping.")
                continue
            job_data = parse_job_posting(job_page_html, full_url)
            if job_data and job_data.get("title"):
                all_jobs.append(job_data)
                if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
                    logging.info(f"Reached MAX_JOBS limit of {config.MAX_JOBS}. Stopping scraping after initial page jobs.")
                    break
            else:
                logging.warning(f"Skipping job due to missing title: {full_url}")

    if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
        logging.info("MAX_JOBS limit reached after initial page processing. Skipping further pagination.")
        if driver: driver.quit() # Close browser before exiting
        db_manager = SupabaseManager()
        if db_manager.connect():
            logging.info(f"Attempting to insert {len(all_jobs)} scraped jobs into Supabase...")
            inserted_count = db_manager.insert_jobs(all_jobs)
            logging.info(f"Successfully inserted {inserted_count} jobs into Supabase.")
            db_manager.close()
        else:
            logging.error("Could not connect to Supabase. Jobs will not be saved to DB.")
        return

    # --- Phase 2: Loop through subsequent pages using Selenium ---
    # Loop from PAGINATION_START_PAGE + 1 (e.g., page 2) up to MAX_PAGES
    # The max value for range is exclusive, so it's (start_page + max_pages).
    end_page_range = (config.MAX_PAGES + config.PAGINATION_START_PAGE) if config.MAX_PAGES is not None else 1000000
    for page_num in range(config.PAGINATION_START_PAGE + 1, end_page_range):
        # Construct the URL for the current page: /search/job-2, /search/job-3 etc.
        # No dynamic IDs needed here, just simple path construction
        current_page_url = f"{urlparse(config.TARGET_URL).scheme}://{urlparse(config.TARGET_URL).netloc}{config.PAGINATION_BASE_PATH}-{page_num}"

        logging.info(f"Selenium: Fetching listings page: {current_page_url}")
        page_html = fetch_with_selenium(driver, current_page_url)

        if not page_html:
            logging.warning(f"Failed to fetch page {page_num} with Selenium. Stopping pagination (likely end of results or block).")
            break

        job_urls = extract_job_list_urls(page_html)
        if not job_urls:
            logging.info(f"No more job URLs found on page {page_num}. Stopping pagination.")
            break

        logging.info(f"Found {len(job_urls)} URLs on page {page_num}.")

        for idx, url in enumerate(job_urls, start=1):
            full_url = url if url.startswith("http") else urljoin(driver.current_url, url) # Use current driver.current_url for base
            logging.info(f"[Page {page_num} - Job {idx}/{len(job_urls)}] Scraping {full_url}")

            job_page_html = fetch_with_selenium(driver, full_url)
            if not job_page_html:
                logging.warning(f"Failed to fetch job page {full_url} with Selenium. Skipping.")
                continue

            job_data = parse_job_posting(job_page_html, full_url)
            if job_data and job_data.get("title"):
                all_jobs.append(job_data)
                if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
                    logging.info(f"Reached MAX_JOBS limit of {config.MAX_JOBS}. Stopping scraping.")
                    break
            else:
                logging.warning(f"Skipping job due to missing title: {full_url}")

        if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
            logging.info("MAX_JOBS reached. Stopping further pagination.")
            break
        
    if driver: driver.quit() # Ensure browser is closed after all scraping is done

    logging.info(f"Finished scraping. Total jobs collected: {len(all_jobs)}.")

    db_manager = SupabaseManager()
    if db_manager.connect():
        logging.info(f"Attempting to insert {len(all_jobs)} scraped jobs into Supabase...")
        inserted_count = db_manager.insert_jobs(all_jobs)
        logging.info(f"Successfully inserted {inserted_count} jobs into Supabase.")
        db_manager.close()
    else:
        logging.error("Could not connect to Supabase. Jobs will not be saved to DB.")

if __name__ == "__main__":
    main()
