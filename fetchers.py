"""
Page fetchers for detail-parser.
Routing logic: which sites use Selenium vs plain HTTP.
Importable without side effects — safe for use in tests.
"""

import os
import logging
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sites that require JavaScript rendering
SELENIUM_DOMAINS = {
    "www.migros.com.tr",
    "www.n11.com",
    "www.hepsiburada.com",
    "www.teknosa.com",
    "www.trendyol.com",
}

_HEADERS = {
    "pragma": "no-cache",
    "cache-control": "no-cache",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.9"
    ),
    "sec-gpc": "1",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "navigate",
    "sec-fetch-user": "?1",
    "sec-fetch-dest": "document",
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate",
}


def _build_driver():
    """
    Her ortamda Firefox + geckodriver kullanır.
      - development → ./bin/win64/geckodriver.exe (Windows) veya ./bin/geckodriver (Unix)
      - production  → /app/bin/geckodriver
    running_mode env var'ı yoksa production varsayılır.
    """
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service

    running_mode = os.environ.get("running_mode", "production")

    if running_mode == "development":
        _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if os.name == "nt":
            driver_path = os.path.join(_project_root, "bin", "win64", "geckodriver.exe")
        else:
            driver_path = os.path.join(_project_root, "bin", "geckodriver")
    else:
        driver_path = "/app/bin/geckodriver"

    options = FirefoxOptions()
    options.add_argument("-headless")
    options.page_load_strategy = "eager"
    options.set_preference("browser.tabs.remote.autostart", False)
    options.set_preference("browser.tabs.remote.autostart.2", False)
    options.set_preference("toolkit.startup.max_resumed_crashes", -1)
    s = Service(driver_path)
    return webdriver.Firefox(service=s, options=options)


def selenium_fetch(url):
    """Fetch page source and title using headless browser (Firefox dev / Chrome prod)."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import TimeoutException

    source = ""
    title = ""

    o = urlparse(url)
    _wait_selector = {
        "www.n11.com":         (By.ID, "app"),
        "www.hepsiburada.com": (By.CSS_SELECTOR, "[data-test-id='default-price']"),
        "www.migros.com.tr":   (By.CSS_SELECTOR, "fe-product-price"),
        "www.teknosa.com":     (By.ID, "main"),
        "www.trendyol.com":    (By.CSS_SELECTOR, "span.discounted, span.ty-plus-price-original-price"),
    }.get(o.hostname, (By.TAG_NAME, "body"))

    try:
        driver = _build_driver()
        driver.set_page_load_timeout(30)
        driver.get(url)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(_wait_selector)
            )
        except TimeoutException:
            pass
        source = driver.page_source
        title = driver.title
        final_url = driver.current_url
        driver.close()
    except Exception as e:
        logger.error("Could not fetch detail on %s (%s)", url, e)
        return "", "", url
    return source, title, final_url


def request_fetch(url):
    """Fetch page source using plain HTTP requests.
    Returns (content: bytes, status_code: int, final_url: str).
    """
    o = urlparse(url)
    headers = {**_HEADERS, "authority": o.hostname, "referer": f"https://{o.hostname}/"}
    try:
        r = requests.get(url, headers=headers)
        return r.content, r.status_code, r.url
    except Exception:
        logger.error("could not fetch url %s", url)
        return b"", 0, url


def fetch_page(url):
    """
    Route URL to the appropriate fetcher based on domain.
    - Selenium domains  → (source, title, 0, final_url)   via headless browser
    - Other domains     → (source, '', status, final_url)  via HTTP request
    - Amazon            → not handled here, use getAmazonPriceFromApi
    Returns (source: bytes|str, title: str, status_code: int, final_url: str)
    """
    o = urlparse(url)
    if o.hostname in SELENIUM_DOMAINS:
        source, title, final_url = selenium_fetch(url)
        return source, title, 0, final_url
    source, status_code, final_url = request_fetch(url)
    return source, "", status_code, final_url
