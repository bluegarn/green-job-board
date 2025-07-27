# Import necessary libraries
import config # Imports a configuration file, likely containing sensitive information like API keys, target URLs, and scraping parameters. This separates configuration from code, making it easier to manage and update.
import re # Regular expression module, used for pattern matching in text, specifically for extracting data from HTML.
import json # JavaScript Object Notation module, used for parsing and generating JSON data. Many websites embed data as JSON, which is easier to parse than HTML.
import time # Provides time-related functions, primarily used here for introducing delays to mimic human Browse behavior and avoid overwhelming the server.
import random # Used to introduce randomness, such as choosing a random User-Agent and generating random delays, further mimicking human-like traffic.
import logging # A flexible event-logging system for applications. Used to output informational, warning, and error messages during the scraping process, aiding in debugging and monitoring.
# requests and urllib.robotparser are still imported but less used for primary fetching
import requests # A popular library for making HTTP requests. While still imported, its primary role for fetching has been replaced by Selenium to handle dynamic content.
import urllib.robotparser # Parses robots.txt files. This is an ethical web scraping practice to check if a website allows scraping and which parts of the site are disallowed.
from urllib.parse import urlparse, urljoin # Removed urlencode, parse_qs. urlparse is used to break down URLs into components (scheme, netloc, path, etc.). urljoin is used to construct absolute URLs from relative ones, ensuring all links are fully qualified.
from bs4 import BeautifulSoup # Beautiful Soup is a library for pulling data out of HTML and XML files. It creates a parse tree for parsed pages that can be used to extract data.
# Removed requests.adapters.HTTPAdapter, requests.exceptions.RequestException
from typing import List, Optional, Dict, Any # Type hints for better code readability and maintainability, helping to define expected data types for variables and function arguments/returns.

# NEW: Import Selenium modules
from selenium import webdriver # The core Selenium WebDriver module, which provides the API for controlling web browsers.
from selenium.webdriver.chrome.service import Service as ChromeService # Used to specify the path to the ChromeDriver executable, which allows Selenium to control Chrome.
from selenium.webdriver.chrome.options import Options as ChromeOptions # Allows setting various options for the Chrome browser, such as running in headless mode.
from selenium.common.exceptions import WebDriverException, TimeoutException # Exceptions specific to Selenium, used for error handling during browser interactions (e.g., if the WebDriver fails to initialize or a page load times out).

from database_manager import SupabaseManager # Imports a custom module for interacting with a Supabase database. This is used to store the scraped job data persistently.

# --- Configuration (loaded from config.py) ---
TARGET_URL = config.TARGET_URL # The initial URL to start scraping from.
HEADERS = config.HEADERS # A list of User-Agent strings. Using multiple User-Agents helps to rotate them, making the scraper appear as different browsers and reducing the chances of being blocked.
COMPANY_SELECTOR = config.COMPANY_SELECTOR # CSS selector for extracting the company name from a job posting.
LOCATION_SELECTOR = config.LOCATION_SELECTOR # CSS selector for extracting the job location.
DESCRIPTION_SELECTOR = config.DESCRIPTION_SELECTOR # CSS selector for extracting the job description.
MAX_JOBS = config.MAX_JOBS # The maximum number of jobs to scrape. This limits the scope of the scraping operation.
MAX_PAGES = config.MAX_PAGES # The maximum number of pagination pages to scrape. This helps control the depth of the scrape.
PAGINATION_BASE_PATH = config.PAGINATION_BASE_PATH # The base path used to construct pagination URLs.
PAGINATION_START_PAGE = config.PAGINATION_START_PAGE # The starting page number for pagination.
MAX_RETRIES = config.MAX_RETRIES # The maximum number of retries for fetching a page in case of a failure, improving robustness.

# A regular expression to find a specific JSON-LD 'ItemList' structure embedded in script tags.
_ITEMLIST_RE = re.compile(r'\[1,"(\{.*?\"itemListElement\".*?\})"\]\)', re.DOTALL) # This regex is designed to find and extract a specific JSON-LD (JSON for Linking Data) structure that often contains lists of items, such as job postings, embedded within script tags. It's an advanced method to directly get structured data.

def setup_logging() -> None:
    # Configures the logging system.
    # Sets the logging level to INFO, meaning all messages with INFO, WARNING, ERROR, and CRITICAL severity will be logged.
    # Defines the format of the log messages to include timestamp, log level, and the message itself.
    # This helps in tracking the scraper's activity and identifying issues.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def get_random_headers() -> Dict[str, str]:
    # This function is mostly for cosmetic use with Selenium options now.
    # Generates a set of HTTP headers with a randomly chosen User-Agent.
    # While Selenium handles most of the browser headers automatically, providing a User-Agent via options can add an extra layer of mimicking a real browser and can be useful for some websites.
    # Other headers like Accept, Accept-Language, Accept-Encoding, Connection, and Referer are included to make the requests appear more legitimate and less like a bot.
    return {
        "User-Agent": random.choice(HEADERS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": TARGET_URL
    }

def get_robot_parser(base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
    # Fetches and parses the robots.txt file for a given base URL.
    # This is a crucial step for ethical web scraping. By checking robots.txt, the scraper can determine which parts of the website it's allowed to access, respecting the website's policies.
    # If the robots.txt file cannot be fetched or parsed, a warning is logged, and None is returned.
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
    # This function uses Selenium to open a real browser (headless, meaning without a visible UI) and navigate to the specified URL.
    # It's designed to handle dynamically loaded content (JavaScript) that traditional HTTP requests (like with 'requests' library) cannot.
    # It includes a retry mechanism with exponential backoff to handle transient network issues or temporary server unresponsiveness.
    # Implicit waits are used to give dynamic content time to load before attempting to retrieve the page source.
    # Small random sleeps are added to further mimic human Browse patterns and avoid being detected as a bot by making requests too quickly.
    # It also checks for "403 Forbidden" or "Access Denied" messages in the page source, indicating potential blocking, and attempts a retry.
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
    # Parses the HTML content to extract URLs of individual job postings.
    # It first attempts to find job URLs from standard JSON-LD schema (Structured Data) embedded in script tags, which is an efficient and reliable way to get structured data.
    # If standard JSON-LD is not found, it then looks for a specific pattern (Next.js payload) within script tags using a regular expression, indicating dynamic content generated by JavaScript frameworks.
    # This dual approach ensures that the scraper can extract job links from various website structures, including those with dynamic content.
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
    # Parses the HTML of a single job posting page to extract specific details like title, company, location, and description.
    # It first attempts to extract this information from structured JSON-LD data of type "JobPosting", which is the most reliable method when available.
    # If JSON-LD is not present or incomplete, it falls back to using CSS selectors (defined in the config) to extract data directly from the HTML elements.
    # This robust parsing logic ensures that job details are extracted even if the website uses different methods for presenting information.
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
    # The main function orchestrates the entire scraping process.
    setup_logging() # Initializes the logging system.
    all_jobs: List[Dict[str, Any]] = [] # An empty list to store all scraped job dictionaries.

    # --- Setup Selenium WebDriver ---
    chrome_options = ChromeOptions() # Creates an instance of ChromeOptions to configure the Chrome browser.
    chrome_options.add_argument("--headless") # Runs Chrome in headless mode, meaning the browser UI won't be visible. This is efficient for scraping as it doesn't require a graphical environment.
    chrome_options.add_argument("--no-sandbox") # A necessary flag for running Chrome in certain environments, especially Docker containers, as it disables the sandbox security feature.
    chrome_options.add_argument("--disable-dev-shm-usage") # Another flag for environments with limited shared memory, preventing crashes in such scenarios.
    # Optional: Set a random User-Agent for the browser via options
    # This is less critical as Selenium mimics a real browser, but can be added.
    chrome_options.add_argument(f"user-agent={random.choice(HEADERS)}") # Sets a random User-Agent for the browser. While Selenium naturally spoofs a browser, this adds another layer of realism.

    # Specify the path to your ChromeDriver executable
    service = ChromeService(executable_path='./chromedriver.exe') # For Windows. Specifies the path to the ChromeDriver executable. This driver acts as a bridge between Selenium and the Chrome browser.
    # For macOS/Linux, if executable_path='./chromedriver' (ensure it's executable)

    driver: Optional[webdriver.Chrome] = None # Initializes the WebDriver variable as None.
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options) # Attempts to initialize the Chrome WebDriver with the specified service and options.
        # Set an implicit wait globally for the driver to wait for elements
        driver.implicitly_wait(10) # Wait up to 10 seconds for elements to appear. This global setting tells the driver to wait for a certain amount of time for elements to become present before throwing an exception, useful for dynamic content.
        logging.info("Selenium WebDriver initialized successfully (Chromium).") # Logs a success message if the WebDriver initializes.
    except WebDriverException as e:
        logging.error(f"Failed to initialize Selenium WebDriver: {e}. Make sure ChromeDriver is in your project folder and matches your Chrome browser version.") # Logs an error if WebDriver initialization fails, providing helpful debugging information.
        return # Exit if driver fails to launch

    rp = get_robot_parser(config.TARGET_URL) # robots.txt check remains. Fetches and parses the robots.txt file for the target website. This is an ethical check to ensure compliance with the website's scraping policies.

    # --- Phase 1: Fetch the initial entry page using Selenium ---
    logging.info(f"Selenium: Fetching initial entry page: {config.TARGET_URL}") # Logs the action of fetching the initial page.
    initial_page_html = fetch_with_selenium(driver, config.TARGET_URL) # Uses Selenium to fetch the HTML content of the initial target URL. This ensures all dynamic content is rendered.

    if not initial_page_html:
        logging.error("Failed to fetch initial entry page with Selenium, exiting.") # If the initial page cannot be fetched, logs an error and exits.
        driver.quit() # Close browser before exiting. Ensures the browser is closed even if an error occurs.
        return

    # In this simplified pagination, we don't need to extract search_id or child_search_id
    # as they are not part of the sequential pagination URLs.
    # We directly process the first page's HTML.
    
    logging.info(f"Processing jobs from initial page: {driver.current_url}") # Logs that the scraper is processing the initial page.

    job_urls_first_page = extract_job_list_urls(initial_page_html) # Extracts all job URLs from the HTML of the initial page.
    if not job_urls_first_page:
        logging.warning("No job URLs found on the initial page (Selenium). This might indicate a problem with CSS selectors or dynamic content.") # Logs a warning if no job URLs are found on the first page.
    else:
        logging.info(f"Found {len(job_urls_first_page)} URLs on initial page.") # Logs the number of job URLs found.
        for idx, url in enumerate(job_urls_first_page, start=1):
            full_url = url if url.startswith("http") else urljoin(driver.current_url, url) # Use current driver.current_url for base. Constructs the full URL for each job posting, handling both absolute and relative URLs.
            logging.info(f"[Page {config.PAGINATION_START_PAGE} - Job {idx}/{len(job_urls_first_page)}] Scraping {full_url}") # Logs the URL of the job being scraped.

            job_page_html = fetch_with_selenium(driver, full_url) # Fetches the HTML content of the individual job posting page using Selenium.
            if not job_page_html:
                logging.warning(f"Failed to fetch job page {full_url} with Selenium. Skipping.") # Logs a warning if a job page cannot be fetched.
                continue
            job_data = parse_job_posting(job_page_html, full_url) # Parses the job posting HTML to extract detailed information.
            if job_data and job_data.get("title"): # Checks if job data was successfully extracted and has a title.
                all_jobs.append(job_data) # Adds the extracted job data to the list of all jobs.
                if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
                    logging.info(f"Reached MAX_JOBS limit of {config.MAX_JOBS}. Stopping scraping after initial page jobs.") # If the maximum number of jobs is reached, stops scraping.
                    break
            else:
                logging.warning(f"Skipping job due to missing title: {full_url}") # Logs a warning if a job is skipped due to a missing title.

    if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
        logging.info("MAX_JOBS limit reached after initial page processing. Skipping further pagination.") # Logs if the MAX_JOBS limit was hit.
        if driver: driver.quit() # Close browser before exiting. Ensures the browser is closed.
        db_manager = SupabaseManager() # Creates an instance of the SupabaseManager to interact with the database.
        if db_manager.connect(): # Attempts to connect to the Supabase database.
            logging.info(f"Attempting to insert {len(all_jobs)} scraped jobs into Supabase...") # Logs the attempt to insert jobs.
            inserted_count = db_manager.insert_jobs(all_jobs) # Inserts the collected job data into the Supabase database.
            logging.info(f"Successfully inserted {inserted_count} jobs into Supabase.") # Logs the number of successfully inserted jobs.
            db_manager.close() # Closes the database connection.
        else:
            logging.error("Could not connect to Supabase. Jobs will not be saved to DB.") # Logs an error if the database connection fails.
        return

    # --- Phase 2: Loop through subsequent pages using Selenium ---
    # Loop from PAGINATION_START_PAGE + 1 (e.g., page 2) up to MAX_PAGES
    # The max value for range is exclusive, so it's (start_page + max_pages).
    end_page_range = (config.MAX_PAGES + config.PAGINATION_START_PAGE) if config.MAX_PAGES is not None else 1000000 # Calculates the end page number for pagination. If MAX_PAGES is not set, it defaults to a very large number, implying no page limit.
    for page_num in range(config.PAGINATION_START_PAGE + 1, end_page_range): # Iterates through subsequent pagination pages.
        # Construct the URL for the current page: /search/job-2, /search/job-3 etc.
        # No dynamic IDs needed here, just simple path construction
        current_page_url = f"{urlparse(config.TARGET_URL).scheme}://{urlparse(config.TARGET_URL).netloc}{config.PAGINATION_BASE_PATH}-{page_num}" # Constructs the URL for the current pagination page based on the base path and page number.

        logging.info(f"Selenium: Fetching listings page: {current_page_url}") # Logs the fetching of the current listings page.
        page_html = fetch_with_selenium(driver, current_page_url) # Fetches the HTML content of the current pagination page using Selenium.

        if not page_html:
            logging.warning(f"Failed to fetch page {page_num} with Selenium. Stopping pagination (likely end of results or block).") # If a page cannot be fetched, logs a warning and stops pagination, assuming end of results or a block.
            break

        job_urls = extract_job_list_urls(page_html) # Extracts job URLs from the current page's HTML.
        if not job_urls:
            logging.info(f"No more job URLs found on page {page_num}. Stopping pagination.") # If no job URLs are found on a page, stops pagination, assuming no more jobs.
            break

        logging.info(f"Found {len(job_urls)} URLs on page {page_num}.") # Logs the number of job URLs found on the current page.

        for idx, url in enumerate(job_urls, start=1):
            full_url = url if url.startswith("http") else urljoin(driver.current_url, url) # Use current driver.current_url for base. Constructs the full URL for each job on the current page.
            logging.info(f"[Page {page_num} - Job {idx}/{len(job_urls)}] Scraping {full_url}") # Logs the URL of the job being scraped.

            job_page_html = fetch_with_selenium(driver, full_url) # Fetches the HTML for the individual job posting.
            if not job_page_html:
                logging.warning(f"Failed to fetch job page {full_url} with Selenium. Skipping.") # Logs a warning if a job page cannot be fetched.
                continue

            job_data = parse_job_posting(job_page_html, full_url) # Parses the job posting details.
            if job_data and job_data.get("title"):
                all_jobs.append(job_data) # Adds valid job data to the list.
                if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
                    logging.info(f"Reached MAX_JOBS limit of {config.MAX_JOBS}. Stopping scraping.") # Stops if MAX_JOBS limit is reached.
                    break
            else:
                logging.warning(f"Skipping job due to missing title: {full_url}") # Logs a warning if a job is skipped due to a missing title.

        if config.MAX_JOBS is not None and len(all_jobs) >= config.MAX_JOBS:
            logging.info("MAX_JOBS reached. Stopping further pagination.") # Confirms that the MAX_JOBS limit was reached.
            break
        
    if driver: driver.quit() # Ensure browser is closed after all scraping is done. Gracefully closes the Selenium WebDriver and the Chrome browser instance.

    logging.info(f"Finished scraping. Total jobs collected: {len(all_jobs)}.") # Logs the total number of jobs collected.

    db_manager = SupabaseManager() # Creates an instance of the SupabaseManager.
    if db_manager.connect(): # Attempts to connect to Supabase.
        logging.info(f"Attempting to insert {len(all_jobs)} scraped jobs into Supabase...") # Logs the intention to insert jobs.
        inserted_count = db_manager.insert_jobs(all_jobs) # Inserts all collected jobs into the database.
        logging.info(f"Successfully inserted {inserted_count} jobs into Supabase.") # Logs the success of the database insertion.
        db_manager.close() # Closes the database connection.
    else:
        logging.error("Could not connect to Supabase. Jobs will not be saved to DB.") # Logs an error if the database connection failed, indicating jobs won't be saved.

if __name__ == "__main__":
    # Standard Python idiom that ensures `main()` is called only when the script is executed directly (not when imported as a module).
    main()