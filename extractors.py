"""
Pure business logic functions for detail-parser.
No external connections required — safe to import in tests.
"""

import re
import hashlib
import datetime
import logging
from urllib.parse import urlparse
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

ALLOWED_DOMAINS = [
    'www.amazon.com.tr',
    'www.hepsiburada.com',
    'www.teknosa.com',
    'www.trendyol.com',
    'www.vatanbilgisayar.com',
    'www.migros.com.tr',
    'www.n11.com',
    'www.mediamarkt.com.tr',
]

ALLOWED_QUERY_CLEANUP_DOMAINS = ['www.teknosa.com']

_PRICE_STOPWORDS = {'tl', 'try', '₺'}


def clearPrice(price_text):
    """
    Convert a Turkish-locale price string into a float.
    Example: "1.234,56 TL" -> 1234.56
    Returns -1 on failure.
    """
    price_text = re.sub("[^0-9.,]", "", str(price_text))
    try:
        price_text = price_text.lower().replace('tl', ' tl')
        tokens = [w for w in price_text.split() if w.lower() not in _PRICE_STOPWORDS]
        cleaned = ' '.join(tokens).replace('.', '').replace(',', '.')
        return float(cleaned)
    except (ValueError, AttributeError):
        return -1


def priceExtractor(soup):
    """
    Extract price from a BeautifulSoup object.
    Tries selectors for each supported site in priority order.
    Returns 0.0 if no price found.
    """
    price = 0.0
    price_tag = None

    # AMAZON - classic
    price_tag = soup.find('span', attrs={'id': 'priceblock_ourprice'})
    # AMAZON - new layout whole part
    if not price_tag:
        price_tag = soup.find('span', attrs={'class': 'a-price-whole'})
    # AMAZON - range / off-screen
    if not price_tag:
        price_tag = soup.find('span', attrs={'class': 'a-offscreen'})
    # HEPSIBURADA
    if not price_tag:
        _hb = soup.find('div', attrs={'data-test-id': 'default-price'})
        if _hb:
            price_tag = _hb.find('div')
    # TEKNOSA
    if not price_tag:
        price_tag = soup.find('span', attrs={'class': re.compile(r'prc prc-last.*')})
    # TRENDYOL - discounted
    if not price_tag:
        price_tag = soup.find('span', attrs={'class': 'discounted'})
    # TRENDYOL - original
    if not price_tag:
        price_tag = soup.find('span', attrs={'class': 'ty-plus-price-original-price'})
    # VATAN
    if not price_tag:
        price_tag = soup.find('span', attrs={'class': 'product-list__price'})
    # MIGROS — fe-product-price Angular bileşenini önce doğrudan ara,
    # yoksa outer div.price-container'a bak
    if not price_tag:
        _migros_container = (
            soup.find('fe-product-price')
            or soup.find('div', attrs={'class': 'price-container'})
        )
        if _migros_container:
            price_tag = _migros_container.find('span', attrs={'class': 'single-price-amount'})
            if not price_tag:
                _currency = _migros_container.find('span', attrs={'class': 'currency'})
                if _currency:
                    price_tag = _currency.parent
            if not price_tag:
                price_tag = _migros_container.find('div', attrs={'class': 'sale-price'})
    # N11 — SSR HTML içine gömülü JSON'dan çek (Vue render beklenmez, çok satıcılı sayfalarda min fiyat)
    if not price_tag:
        _n11_prices = re.findall(r'"finalPrice":"([^"]+)"', str(soup))
        if _n11_prices:
            _candidates = [clearPrice(p) for p in _n11_prices]
            _valid = [p for p in _candidates if p > 0]
            if _valid:
                return min(_valid)
        # Fallback: Vue.js render ettiyse HTML selektör
        price_tag = soup.find('div', attrs={'class': 'newPrice'})
    # MEDIAMARKT
    if not price_tag:
        price_tag = soup.find('span', attrs={'data-test': 'branded-price-whole-value'})

    if price_tag:
        content = price_tag.get('content')
        if content:
            try:
                # meta content attributes use international float format (e.g. MediaMarkt: "1299.00")
                price = float(content)
            except ValueError:
                price = clearPrice(content)
        elif price_tag.text:
            price = clearPrice(price_tag.text)

    return price


def titleExtractor(soup):
    """Extract page title from soup."""
    if not soup:
        return ''
    if soup.find('title'):
        return soup.find('title').text
    if soup.find('meta', attrs={'property': 'og:title'}):
        return soup.find('meta', attrs={'property': 'og:title'}).get('content', '')
    if soup.find('meta', attrs={'name': 'twitter:title'}):
        return soup.find('meta', attrs={'name': 'twitter:title'}).get('content', '')
    return ''


def categoryExtractor(soup):
    """
    Extract breadcrumb categories from soup.
    Returns a list of category strings, or None if not found.
    """
    if not soup:
        return None

    breadcrumbs = None

    # HEPSIBURADA
    breadcrumbs = soup.find_all('a', attrs={'id': re.compile(r'breadcrumbFor.*')})
    # TEKNOSA
    if not breadcrumbs and soup.find('ol', attrs={'class': 'breadcrumb'}):
        breadcrumbs = soup.find('ol', attrs={'class': 'breadcrumb'}).find_all('li')
    # TRENDYOL
    if not breadcrumbs:
        breadcrumbs = soup.find_all('a', attrs={'class': 'product-detail-breadcrumb-item'})
    # VATAN
    if not breadcrumbs:
        breadcrumbs = soup.find_all('a', attrs={'class': 'bradcrumb-item'})
    # MIGROS
    if not breadcrumbs:
        breadcrumbs = soup.find_all('a', attrs={'class': 'breadcrumbs__link'})
    # N11
    if not breadcrumbs and soup.find('div', attrs={'id': 'breadCrumb'}):
        breadcrumbs = soup.find('div', attrs={'id': 'breadCrumb'}).find('ul')
    # MEDIAMARKT
    if not breadcrumbs:
        breadcrumbs = soup.find('ul', attrs={'class': 'breadcrumbs'})

    if not breadcrumbs:
        return None

    categories = []
    for item in breadcrumbs:
        name = item.text.strip()
        if not name or name.replace(' ', '').lower() == 'anasayfa':
            continue
        if name not in categories:
            categories.append(name)

    return categories if categories else None


def uidExtractor(path):
    """
    Extract a unique product identifier from a URL path.
    Falls back to MD5 hash of the path.
    """
    # AMAZON
    regex = r"(?:(?:dp)|(?:gp\/product))\/([^\/?]+)"
    matches = re.findall(regex, path)
    if not matches:
        # HEPSIBURADA / TEKNOSA / TRENDYOL / MIGROS
        regex = r".*-p-(\w+)\?*"
        matches = re.findall(regex, path)
    if not matches:
        # N11: /urun/product-name-{numeric-id}
        regex = r"/urun/.*-(\d+)$"
        matches = re.findall(regex, path)
    if not matches:
        # MEDIAMARKT: /tr/product/_name-{id}.html
        regex = r"/product/.*-(\d+)\.html"
        matches = re.findall(regex, path)
    if matches:
        return matches[0]
    return hashlib.md5(path.encode('utf-8')).hexdigest()


def urlClean(url):
    return url.replace('"', '')


def urlQSClean(parsed):
    """Remove tracking query params for domains that need cleanup."""
    if parsed.hostname in ALLOWED_QUERY_CLEANUP_DOMAINS:
        new_query = re.sub(r"(shopId)=([a-zA-Z0-9]+)&?", "", parsed.query)
        parsed = parsed._replace(query=new_query)
    return parsed


def buildDoc(url, domain, path, title, price, uid, categories):
    """Assemble the MongoDB document for a product price record."""
    return {
        'url': url,
        'domain': domain,
        'path': path,
        'title': title,
        'date_updated': datetime.datetime.utcnow().isoformat(),
        'price': price,
        'uid': uid,
        'categories': categories,
    }


def computePriceTag(price, history_7d, history_30d, history_90d):
    """
    Determine a price tag based on historical comparison.

    Tags:
        0 - no special tag
        2 - lowest in 7 days
        3 - lowest in 30 days
        4 - lowest in 90 days
    """
    if not price or price <= 0:
        return 0

    if history_7d and len(history_7d) >= 3:
        min_7d = min(history_7d)
        avg_7d = sum(history_7d) / len(history_7d)
        if price <= min_7d and price != avg_7d:
            return 2

    if history_30d and len(history_30d) >= 15:
        min_30d = min(history_30d)
        avg_30d = sum(history_30d) / len(history_30d)
        if price <= min_30d and price != avg_30d:
            return 3

    if history_90d and len(history_90d) >= 45:
        min_90d = min(history_90d)
        avg_90d = sum(history_90d) / len(history_90d)
        if price <= min_90d and price != avg_90d:
            return 4

    return 0
