import config
import re
import json
import time
import random
import logging
import requests
import urllib.robotparser
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from typing import List, Optional, Dict, Any

# --- Configuration ---
TARGET_URL = config.TARGET_URL
HEADERS = config.HEADERS
COMPANY_SELECTOR = config.COMPANY_SELECTOR
LOCATION_SELECTOR = config.LOCATION_SELECTOR
DESCRIPTION_SELECTOR = config.DESCRIPTION_SELECTOR
_ITEMLIST_RE = re.compile(r'\[1,"(\{.*?\"itemListElement\".*?\})"\]\)', re.DOTALL)

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

def get_random_headers() -> Dict[str, str]:
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

def fetch(session: requests.Session, url: str, rp: Optional[urllib.robotparser.RobotFileParser]) -> Optional[str]:
    if rp and not rp.can_fetch(session.headers.get("User-Agent", ""), url):
        logging.warning(f"Disallowed by robots.txt: {url}")
        return None
    for attempt in range(1, 4):
        try:
            time.sleep(random.uniform(1.5, 4.0))
            resp = session.get(url, timeout=15, allow_redirects=True)
            if resp.status_code == 403:
                logging.warning(f"403 Forbidden at {url}, rotating UA (attempt {attempt}/3)")
                session.headers.update(get_random_headers())
                continue
            resp.raise_for_status()
            return resp.text
        except RequestException as e:
            logging.error(f"Error fetching {url} (attempt {attempt}/3): {e}")
            time.sleep(2 ** attempt)
    return None

def extract_job_list_urls(html: str) -> List[str]:
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
    soup = BeautifulSoup(html, "html.parser")
    JOBPOST_RE = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
    for script in JOBPOST_RE.findall(html):
        try:
            data = json.loads(script)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            title = data.get("title")
            company = data.get("hiringOrganization", {}).get("name")
            loc = data.get("jobLocation")
            location = None
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
                location = ", ".join(locs) if locs else None
            elif isinstance(loc, dict):
                address = loc.get("address", {})
                if isinstance(address, dict):
                    location = address.get("addressLocality")
            description = None
            job = {
                "title": title,
                "company": company,
                "location": location,
                "description": description,
                "link": job_url
            }
            break
    else:
        job = {
            "title": None,
            "company": None,
            "location": None,
            "description": None,
            "link": job_url
        }
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
    desc_el = soup.select_one(DESCRIPTION_SELECTOR)
    if desc_el:
        job["description"] = str(desc_el)
    return job

def main() -> None:
    setup_logging()
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=1))
    session.headers.update(get_random_headers())

    rp = get_robot_parser(TARGET_URL)
    logging.info("Fetching main listings page...")
    search_html = fetch(session, TARGET_URL, rp)
    if not search_html:
        logging.error("Failed to fetch main page, exiting.")
        return

    job_urls = extract_job_list_urls(search_html)
    if not job_urls:
        logging.error("No job URLs found; exiting.")
        return

    all_jobs: List[Dict[str, Any]] = []
    for idx, url in enumerate(job_urls[:config.MAX_JOBS] if config.MAX_JOBS else job_urls, start=1):
        full_url = url if url.startswith("http") else urljoin(TARGET_URL, url)
        logging.info(f"[{idx}/{len(job_urls)}] Scraping {full_url}")
        session.headers.update(get_random_headers())
        page_html = fetch(session, full_url, rp)
        if not page_html:
            continue
        job_data = parse_job_posting(page_html, full_url)
        if job_data and job_data.get("title"):
            all_jobs.append(job_data)
        else:
            logging.warning(f"Skipping job due to missing title: {full_url}")

    logging.info(f"Scraped {len(all_jobs)} jobs successfully.")
    print(json.dumps(all_jobs, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
