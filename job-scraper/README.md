
# Green Job Board Scraper

This project contains a Python-based web scraper designed to extract green job postings from `foundit.in`. The extracted data is intended to populate a "Green Job Board" database.

## Features

- **Dynamic Content Scraping:** Utilises Selenium to automate a Chrome browser, ensuring all JavaScript-rendered content is captured.
- **Structured Data Extraction:** Prioritises fetching job details from JSON-LD (`schema.org/JobPosting` and `ItemList`) embedded within the page HTML.
- **Robust Data Parsing:** Employs Beautiful Soup for efficient HTML parsing and CSS selectors as a fallback when structured data is incomplete.
- **Pagination Handling:** Navigates through multiple pages of search results to gather a comprehensive set of job postings.
- **Error Handling & Retries:** Implements robust `try-except` blocks and an exponential backoff retry mechanism to manage network issues and website anti-bot measures.
- **Ethical Scraping Practices:** Includes considerations for `robots.txt` and random delays to mimic human browse behaviour.
- **Modular Configuration:** Externalises key settings (URLs, selectors, limits) in a dedicated `config.py` file for easy updates.
- **Supabase Integration:** Designed to connect to and insert scraped job data directly into a Supabase database.
- **Detailed Logging:** Provides comprehensive console logs for monitoring script progress and diagnosing issues.

## Prerequisites

Before running the scraper, ensure you have the following installed:

- **Python 3.8+**: [Download Python](https://www.python.org/downloads/)
- **Google Chrome Browser**: Ensure Chrome is installed and up to date on your system.
- **ChromeDriver Executable**: A compatible ChromeDriver executable must be placed in the root of the `job-scraper` directory. You can download the correct version matching your Chrome browser from the [Chrome for Testing availability dashboard](https://googlechromelabs.github.io/chrome-for-testing/).

## Installation

Follow these steps to set up the project locally:

1. **Clone the Repository (if not already done):**
    ```bash
    git clone https://github.com/your-username/your-repository-name.git
    ```
2. **Navigate to the Project Directory:**
    ```bash
    cd green-job-board/job-scraper
    ```
3. **Create a Virtual Environment:**
    ```bash
    python -m venv .venv
    ```
4. **Activate the Virtual Environment:**
    - On Windows (PowerShell):
        ```bash
        .venv\Scripts\activate
        ```
    - On macOS/Linux (Bash/Zsh):
        ```bash
        source .venv/bin/activate
        ```
5. **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
6. **Place ChromeDriver:**
    - Download the `chromedriver.exe` (for Windows) or `chromedriver` (for macOS/Linux) that precisely matches your Google Chrome browser version from the [Chrome for Testing availability dashboard](https://googlechromelabs.github.io/chrome-for-testing/).
    - Place this executable file directly into your `job-scraper` directory (alongside `foundit_scraper.py`).

## Configuration (`config.py`)

The scraper's behaviour is controlled via the `config.py` file.

1. **Create `config.py`:** If it doesn't exist, create it in the `job-scraper` directory.
2. **Add/Update Settings:** Populate it with variables like the following:

    ```python
    # config.py

    TARGET_URL = "https://www.foundit.in/search/job"
    HEADERS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        # Add more User-Agent strings here
    ]
    TITLE_SELECTOR = "div.text-content-primary.md\!text-2xl"
    COMPANY_SELECTOR = "div.text-content-secondary.md\!text-content-primary span"
    LOCATION_SELECTOR = "div.text-content-primary.flex.gap-4 a"
    DESCRIPTION_SELECTOR = "#jobDescription"
    MAX_JOBS = None  # Set to an integer to limit jobs (e.g., 100), or None for no limit
    MAX_PAGES = 5  # Set to an integer to limit pages (e.g., 5), or None for no limit
    PAGINATION_BASE_PATH = "/search/job"
    PAGINATION_START_PAGE = 1
    MAX_RETRIES = 10  # Number of retries for fetching pages

    # Supabase credentials
    SUPABASE_URL = "YOUR_SUPABASE_PROJECT_URL"
    SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY"
    ```

> **Note:** Replace `"YOUR_SUPABASE_PROJECT_URL"` and `"YOUR_SUPABASE_ANON_KEY"` with actual values. Ideally, use a `.env` file for better security in production.

## Usage

Once configured, run the scraper from the `job-scraper` directory with your virtual environment activated:

```bash
(venv) $ python foundit_scraper.py
```

The script will log its progress to your console, including pages fetched and jobs found. Upon completion, it will insert the scraped data into your Supabase database.

## Project Structure

```
foundit_scraper.py        # Main scraping logic
config.py                 # Configurable parameters and selectors
database_manager.py       # Supabase connection and insert logic
requirements.txt          # Python dependencies
.venv/                    # Virtual environment directory
chromedriver.exe          # Chrome WebDriver (or chromedriver)
.gitignore                # Git ignore file
```

## Troubleshooting

### ❗ WebDriverException: `'chromedriver' executable needs to be in PATH` or version mismatch

- Ensure `chromedriver.exe` is in the `job-scraper` directory.
- Make sure it matches the version of your installed Chrome browser.
- Re-download if necessary.

### ❗ Selenium: Detected potential 403/Access Denied... Retrying

**Cause:** Website’s anti-bot system is triggered.

**Solutions:**
- Increase `MAX_RETRIES` and adjust `time.sleep` in `fetch_with_selenium`.
- Run Chrome in non-headless mode (remove `--headless` from options) to visually inspect for CAPTCHA or Cloudflare blocks.
- Consider using proxy rotation or switching to `undetected-chromedriver`.

### ❗ Could not locate any `ItemList` JSON-LD

**Cause:** Website structure has changed.

**Solution:**
- Manually inspect the site's HTML.
- Update `_ITEMLIST_RE` regex or the relevant CSS selectors in `config.py` and `foundit_scraper.py`.

### ❗ Database Connection Errors

**Cause:** Incorrect credentials or connectivity issues.

**Solution:**
- Verify `SUPABASE_URL` and `SUPABASE_KEY`.
- Check your Supabase project’s status and permissions.

## Contributing

This project is developed as part of a university assignment. Contributions or pull requests are not expected. Please refer to course guidelines for collaboration.

## License

This project is for educational purposes as part of a university course. No open-source license is implied or granted for external use beyond this context.
