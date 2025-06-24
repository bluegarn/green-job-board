# foundit_scraper.py

# Import necessary libraries
import config  # Imports a custom configuration module (e.g., config.py) for settings like TARGET_URL, HEADERS, etc.
import re  # Regular expression module for pattern matching in text.
import json  # JSON module for parsing and handling JSON data.
import time  # Time module for introducing delays (e.g., for polite scraping).
import random  # Random module for generating random numbers (e.g., for user-agent rotation, sleep times).
import logging  # Logging module for recording events, warnings, and errors.
import requests  # Third-party library for making HTTP requests (e.g., GET requests to web pages).
import urllib.robotparser  # Module for parsing robots.txt files to check crawling permissions.
from urllib.parse import urlparse, urljoin  # Utilities for parsing and joining URLs.
from bs4 import BeautifulSoup  # Beautiful Soup library for parsing HTML and XML documents.
from requests.adapters import HTTPAdapter  # Used for customizing HTTP session behavior (e.g., retries).
from requests.exceptions import RequestException  # Base exception class for requests errors.
from typing import List, Optional, Dict, Any  # Type hints for better code readability and maintainability.
from database_manager import SupabaseManager # Import the new SupabaseManager for database interaction

# --- Configuration ---
# These variables are loaded from the 'config' module.
TARGET_URL = config.TARGET_URL  # The initial URL to start scraping from.
HEADERS = config.HEADERS  # A list of user-agent strings for rotating headers to mimic different browsers.
COMPANY_SELECTOR = config.COMPANY_SELECTOR  # CSS selector to find the company name on a job posting page.
LOCATION_SELECTOR = config.LOCATION_SELECTOR  # CSS selector to find the location on a job posting page.
DESCRIPTION_SELECTOR = config.DESCRIPTION_SELECTOR  # CSS selector to find the job description content.
# A regular expression to find a specific JSON-LD 'ItemList' structure embedded in script tags,
# particularly useful for sites built with frameworks like Next.js that might encapsulate data differently.
_ITEMLIST_RE = re.compile(r'\[1,"(\{.*?\"itemListElement\".*?\})"\]\)', re.DOTALL)

def setup_logging() -> None:
    """
    Sets up the basic configuration for logging messages.
    Logs will be output to the console with a specific format including timestamp, log level, and message.
    """
    logging.basicConfig(
        level=logging.INFO,  # Sets the minimum logging level to INFO, meaning INFO, WARNING, ERROR, CRITICAL messages will be processed.
        format="%(asctime)s [%(levelname)s] %(message)s",  # Defines the format of the log messages.
        datefmt="%Y-%m-%d %H:%M:%S"  # Defines the format of the timestamp in log messages.
    )

def get_random_headers() -> Dict[str, str]:
    """
    Generates a dictionary of HTTP headers with a randomly selected User-Agent.
    This helps in mimicking different browsers and potentially avoiding detection by anti-scraping mechanisms.
    Returns:
        Dict[str, str]: A dictionary of HTTP headers.
    """
    return {
        "User-Agent": random.choice(HEADERS),  # Selects a random User-Agent string from the predefined list.
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",  # Specifies acceptable content types.
        "Accept-Language": "en-US,en;q=0.9",  # Specifies preferred languages for the response.
        "Accept-Encoding": "gzip, deflate, br",  # Specifies acceptable encoding methods for the response.
        "Connection": "keep-alive",  # Requests to keep the connection alive for multiple requests.
        "Referer": TARGET_URL  # Sets the Referer header to the initial target URL, mimicking a natural browsing flow.
    }

def get_robot_parser(base_url: str) -> Optional[urllib.robotparser.RobotFileParser]:
    """
    Initializes and reads the robots.txt file for a given base URL.
    This helps in respecting website crawling policies.
    Args:
        base_url (str): The base URL of the website (e.g., "https://example.com").
    Returns:
        Optional[urllib.robotparser.RobotFileParser]: An initialized RobotFileParser object, or None if robots.txt
                                                     could not be fetched or parsed.
    """
    parsed = urlparse(base_url)  # Parses the base URL into components.
    domain = f"{parsed.scheme}://{parsed.netloc}"  # Constructs the domain (scheme + netloc).
    rp = urllib.robotparser.RobotFileParser()  # Creates a RobotFileParser instance.
    rp.set_url(domain + "/robots.txt")  # Sets the URL of the robots.txt file.
    try:
        rp.read()  # Attempts to read and parse the robots.txt file.
        return rp  # Returns the parser if successful.
    except Exception as e:
        # Logs a warning if robots.txt cannot be fetched or parsed.
        logging.warning(f"Could not fetch robots.txt from {domain}: {e}")
        return None

def fetch(session: requests.Session, url: str, rp: Optional[urllib.robotparser.RobotFileParser]) -> Optional[str]:
    """
    Fetches the content of a given URL using a requests session.
    It includes checks for robots.txt, retries on failure, and handles 403 Forbidden errors by rotating user agents.
    Args:
        session (requests.Session): The requests session object to use for making the HTTP request.
        url (str): The URL to fetch.
        rp (Optional[urllib.robotparser.RobotFileParser]): The robots.txt parser object to check crawl permissions.
    Returns:
        Optional[str]: The text content of the response if successful, otherwise None.
    """
    # Checks if crawling is allowed by robots.txt before making the request.
    if rp and not rp.can_fetch(session.headers.get("User-Agent", ""), url):
        logging.warning(f"Disallowed by robots.txt: {url}")  # Logs a warning if disallowed.
        return None  # Returns None as per robots.txt policy.

    for attempt in range(1, 4):  # Tries to fetch the URL up to 3 times.
        try:
            time.sleep(random.uniform(1.5, 4.0))  # Introduces a random delay to be polite and avoid detection.
            resp = session.get(url, timeout=15, allow_redirects=True)  # Makes a GET request with a timeout and allows redirects.
            if resp.status_code == 403:  # If a 403 Forbidden error occurs.
                logging.warning(f"403 Forbidden at {url}, rotating UA (attempt {attempt}/3)")  # Logs the error.
                session.headers.update(get_random_headers())  # Updates the session headers with a new random User-Agent.
                continue  # Continues to the next attempt with the new header.
            resp.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx).
            return resp.text  # Returns the content of the response if successful.
        except RequestException as e:  # Catches any request-related exceptions.
            logging.error(f"Error fetching {url} (attempt {attempt}/3): {e}")  # Logs the error.
            time.sleep(2 ** attempt)  # Implements exponential backoff for retries.
    return None  # Returns None if all attempts fail.

def extract_job_list_urls(html: str) -> List[str]:
    """
    Extracts job listing URLs from the provided HTML content.
    It looks for URLs embedded in JSON-LD structured data (type "ItemList") in script tags,
    handling both standard JSON-LD and a specific Next.js-like payload format.
    Args:
        html (str): The HTML content of the page.
    Returns:
        List[str]: A list of extracted job URLs.
    """
    soup = BeautifulSoup(html, "html.parser")  # Parses the HTML content using Beautiful Soup.

    # First, try to find standard JSON-LD script tags with type "application/ld+json".
    for script in soup.find_all("script", type="application/ld+json"):
        text = script.string  # Gets the content of the script tag.
        if not text:
            continue  # Skips if the script tag is empty.
        try:
            data = json.loads(text)  # Parses the script content as JSON.
        except json.JSONDecodeError:
            continue  # Skips if JSON parsing fails.

        # Handles cases where 'data' might be a list of JSON-LD objects or a single object.
        for entry in (data if isinstance(data, list) else [data]):
            # Checks if the entry is a dictionary and its '@type' is "ItemList".
            if isinstance(entry, dict) and entry.get("@type") == "ItemList":
                items = entry.get("itemListElement", [])  # Gets the 'itemListElement' which contains the items.
                # Extracts URLs from each item, ensuring they are not None.
                urls = [item.get("url") for item in items if item.get("url")]
                if urls:
                    logging.info(f"Found {len(urls)} URLs via standard JSON-LD.")  # Logs success.
                    return urls  # Returns the URLs found.

    # If standard JSON-LD fails, try to find a specific pattern often used in Next.js applications
    # where JSON data is embedded differently in script tags.
    for script in soup.find_all("script"):
        text = script.string or ""  # Gets the script content.
        if '"@type":"ItemList"' not in text:  # Quickly checks if "ItemList" string is present.
            continue  # Skips if not found.

        match = _ITEMLIST_RE.search(text)  # Attempts to match the specific regex pattern.
        if not match:
            continue  # Skips if no match.

        raw = match.group(1)  # Extracts the raw JSON string from the regex match.
        try:
            # Decodes unicode escape sequences and parses the raw string as JSON.
            payload = json.loads(raw.encode("utf-8").decode("unicode_escape"))
            items = payload.get("itemListElement", [])  # Gets the 'itemListElement'.
            urls = [item.get("url") for item in items if item.get("url")]  # Extracts URLs.
            logging.info(f"Found {len(urls)} URLs via Next.js payload.")  # Logs success.
            return urls  # Returns the URLs found.
        except json.JSONDecodeError:
            continue  # Skips if JSON parsing fails.

    logging.error("Could not locate any ItemList JSON-LD.")  # Logs an error if no URLs are found.
    return []  # Returns an empty list if no URLs are found after all attempts.

def parse_job_posting(html: str, job_url: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single job posting HTML page to extract job details.
    It primarily looks for "JobPosting" schema.org JSON-LD data. If not found or incomplete,
    it falls back to using CSS selectors to extract information.
    Args:
        html (str): The HTML content of the job posting page.
        job_url (str): The URL of the job posting.
    Returns:
        Optional[Dict[str, Any]]: A dictionary containing job details (title, company, location, description, link),
                                 or None if parsing fails significantly.
    """
    soup = BeautifulSoup(html, "html.parser")  # Parses the HTML content.
    # Regex to find script tags containing JSON-LD.
    JOBPOST_RE = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)

    job = {
        "title": None,
        "company": None,
        "location": None,
        "description": None, # Initialize description to None
        "link": job_url
    }

    # First, attempt to extract data from "JobPosting" JSON-LD.
    for script in JOBPOST_RE.findall(html):  # Finds all JSON-LD script blocks.
        try:
            data = json.loads(script)  # Parses the script content as JSON.
        except json.JSONDecodeError:
            continue  # Skips if JSON parsing fails.

        # Checks if the parsed data is a dictionary and its '@type' is "JobPosting".
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            job["title"] = data.get("title")  # Extracts the job title.
            job["company"] = data.get("hiringOrganization", {}).get("name")  # Extracts company name from hiringOrganization.
            loc = data.get("jobLocation")  # Gets the job location data.
            location = None # Initialize location to None

            # Handles 'jobLocation' if it's a list of locations (e.g., multiple offices).
            if isinstance(loc, list):
                locs = []
                for entry in loc:
                    if isinstance(entry, dict):
                        address = entry.get("address", {})
                        if isinstance(address, dict):
                            locality = address.get("addressLocality") # Get city/locality
                            if locality:
                                locs.append(locality)
                job["location"] = ", ".join(locs) if locs else None # Joins multiple locations with a comma.
            # Handles 'jobLocation' if it's a single location dictionary.
            elif isinstance(loc, dict):
                address = loc.get("address", {})
                if isinstance(address, dict):
                    job["location"] = address.get("addressLocality")

            job["description"] = data.get("description") # Assign description from JSON-LD
            break  # Stops after finding and parsing the first valid JobPosting JSON-LD.

    # Fallback to CSS selectors if JSON-LD parsing didn't provide a title, company, or location.
    if not job["title"]:
        title_el = soup.select_one("div.text-content-primary.md\\!text-2xl")  # Uses CSS selector for title.
        job["title"] = title_el.get_text(strip=True) if title_el else None  # Extracts text, stripping whitespace.
    if not job["company"]:
        comp_el = soup.select_one(COMPANY_SELECTOR)  # Uses CSS selector for company.
        job["company"] = comp_el.get_text(strip=True) if comp_el else None
    if not job["location"]:
        locs = soup.select(LOCATION_SELECTOR)  # Uses CSS selector for location (can be multiple elements).
        if locs:
            job["location"] = ", ".join([l.get_text(strip=True) for l in locs])  # Joins multiple location elements.

    # Assign description from CSS selector only if it hasn't been set by JSON-LD
    if not job["description"]: # Check if description is still None after JSON-LD attempt
        desc_el = soup.select_one(DESCRIPTION_SELECTOR)
        if desc_el:
            job["description"] = str(desc_el) # Assignment from CSS selector (this will be raw HTML)

    # --- NEW ADDITION: Strip HTML from description to ensure plain text ---
    if job["description"]: # Only process if a description was found
        # Create a new BeautifulSoup object from the description string.
        # This is necessary because the description might be a raw HTML string from `str(desc_el)`
        # or it could be text with embedded HTML from the JSON-LD.
        description_soup = BeautifulSoup(job["description"], "html.parser")
        # Get the plain text from the parsed description, using a space as a separator
        # between elements (e.g., ensuring "Paragraph1Paragraph2" becomes "Paragraph1 Paragraph2")
        # and stripping leading/trailing whitespace.
        job["description"] = description_soup.get_text(separator=' ', strip=True)

    return job # Returns the dictionary of job data.

def main() -> None:
    """
    Main function to run the web scraping process.
    Initializes the session, fetches the main page, extracts job listing URLs,
    then iterates through each job URL to parse individual job postings.
    Finally, it prints the collected job data in JSON format.
    """
    setup_logging()  # Initializes logging.
    session = requests.Session()  # Creates a persistent requests session for efficient connection reuse.
    # Mounts an HTTPAdapter to retry failed connections for HTTPS.
    session.mount("https://", HTTPAdapter(max_retries=1))
    session.headers.update(get_random_headers())  # Sets initial random headers for the session.

    rp = get_robot_parser(TARGET_URL)  # Gets the robots.txt parser for the target URL.
    logging.info("Fetching main listings page...")  # Logs the start of fetching the main page.
    search_html = fetch(session, TARGET_URL, rp)  # Fetches the HTML content of the main page.
    if not search_html:
        logging.error("Failed to fetch main page, exiting.")  # Logs an error if fetching fails.
        return  # Exits the function.

    job_urls = extract_job_list_urls(search_html)  # Extracts job listing URLs from the main page.
    if not job_urls:
        logging.error("No job URLs found; exiting.")  # Logs an error if no URLs are found.
        return  # Exits the function.

    all_jobs: List[Dict[str, Any]] = []  # Initializes an empty list to store all scraped job data.
    # Iterates through the extracted job URLs. It can be limited by config.MAX_JOBS if defined.
    for idx, url in enumerate(job_urls[:config.MAX_JOBS] if config.MAX_JOBS else job_urls, start=1):
        # Constructs the full URL, handling relative URLs.
        full_url = url if url.startswith("http") else urljoin(TARGET_URL, url)
        logging.info(f"[{idx}/{len(job_urls)}] Scraping {full_url}")  # Logs the current URL being scraped.
        session.headers.update(get_random_headers())  # Rotates user-agent for each individual job page request.
        page_html = fetch(session, full_url, rp)  # Fetches the HTML content of the individual job page.
        if not page_html:
            continue  # Skips to the next URL if fetching fails.

        job_data = parse_job_posting(page_html, full_url)  # Parses the job posting details from the page HTML.
        # Checks if job_data was successfully parsed and has a title.
        if job_data and job_data.get("title"):
            all_jobs.append(job_data)  # Adds the parsed job data to the list.
        else:
            logging.warning(f"Skipping job due to missing title: {full_url}")  # Logs a warning if title is missing.

    logging.info(f"Scraped {len(all_jobs)} jobs successfully.")  # Logs the total number of jobs scraped.

    # --- Database Insertion ---
    db_manager = SupabaseManager()
    if db_manager.connect(): # Attempt to connect to the database
        logging.info(f"Attempting to insert {len(all_jobs)} scraped jobs into Supabase...")
        inserted_count = db_manager.insert_jobs(all_jobs) # Insert the jobs
        logging.info(f"Successfully inserted {inserted_count} jobs into Supabase.")
        db_manager.close() # Always close the connection
    else:
        logging.error("Could not connect to Supabase. Jobs will not be saved to DB.")
        # Optionally, you could print to console here if DB connection fails
        print(json.dumps(all_jobs, indent=2, ensure_ascii=False)) # This line was commented out in previous update

if __name__ == "__main__":
    # Ensures that the main() function is called only when the script is executed directly (not imported as a module).
    main()
