"""
Smoke report — her siteden fiyat çekip özet tablo basar.
Production ile aynı fetch_page() fonksiyonunu kullanır (Selenium veya HTTP).
Çalıştır: python smoke_report.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bs4 import BeautifulSoup
from extractors import priceExtractor
from fetchers import fetch_page

SMOKE_URLS = [
    ("teknosa",     "https://www.teknosa.com/apple-iphone-17-pro-256gb-kozmik-turuncu-akilli-telefon-p-100000058785"),
    ("hepsiburada", "https://www.hepsiburada.com/apple-iphone-17-pro-256-gb-kozmik-turuncu-p-HBCV00009Z3XL5"),
    ("trendyol",    "https://www.trendyol.com/apple/iphone-17-pro-256gb-kozmik-turuncu-p-985256852"),
    ("vatan",       "https://www.vatanbilgisayar.com/iphone-17-pro-max-256-gb-akilli-telefon-gumus.html"),
    ("mediamarkt",  "https://www.mediamarkt.com.tr/tr/product/_apple-iphone-17-pro-256gb-akilli-telefon-gumus-1249236.html"),
]

COL = {"site": 14, "price": 12, "status": 8, "url": 60}


def fetch_price(url):
    source, _ = fetch_page(url)
    if not source:
        raise RuntimeError("Boş yanıt")
    soup = BeautifulSoup(source, "html.parser")
    return priceExtractor(soup)


def fmt_row(site, price, status, url):
    return (
        f"  {site:<{COL['site']}}  "
        f"{str(price):<{COL['price']}}  "
        f"{status:<{COL['status']}}  "
        f"{url[:COL['url']]}"
    )


def main():
    header = fmt_row("SİTE", "FİYAT (TL)", "DURUM", "URL")
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    results = []
    for site, url in SMOKE_URLS:
        try:
            price = fetch_price(url)
            status = "✓ OK" if price > 0 else "✗ 0"
            results.append((site, price, status))
            print(fmt_row(site, f"{price:,.2f}", status, url))
        except Exception as e:
            results.append((site, None, "ERR"))
            print(fmt_row(site, "-", "ERR", str(e)))

    print(sep)
    ok = sum(1 for r in results if r[2] == "✓ OK")
    fail = len(results) - ok
    print(f"  Toplam: {len(results)}  |  Başarılı: {ok}  |  Başarısız: {fail}")
    print(sep)


if __name__ == "__main__":
    main()
