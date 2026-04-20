from ast import Try
import requests
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import re
import time

import locale
locale.setlocale(locale.LC_ALL, '')
import os
import logging
import sys
import datetime
import pika
import random
import hashlib
from decimal import *

from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.wait import WebDriverWait
import selenium
from selenium import webdriver

from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from pymongo.common import RETRY_WRITES

from pymongo import MongoClient

from retry import retry

import pymssql

from extractors import (
    clearPrice, priceExtractor, titleExtractor, categoryExtractor,
    uidExtractor, urlClean, urlQSClean, buildDoc, computePriceTag,
    ALLOWED_DOMAINS, ALLOWED_QUERY_CLEANUP_DOMAINS,
)
from fetchers import fetch_page, SELENIUM_DOMAINS


sql_host = os.environ['sql_host']
sql_user = os.environ['sql_user']
sql_pass = os.environ['sql_pass']
sql_db = os.environ['sql_db']


mongo_host = os.environ['mongo_host']

running_mode = os.environ['running_mode']

rabbit_host = os.environ['rabbit_host']
rabbit_port = os.environ['rabbit_port']
rabbit_user = os.environ['rabbit_user']
rabbit_pass = os.environ['rabbit_pass']

product_api_update_endpoint = os.environ['product_api_update_endpoint']

allowed_domains = ALLOWED_DOMAINS
allowed_query_cleanup_domains = ALLOWED_QUERY_CLEANUP_DOMAINS




root = logging.getLogger()
root.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
# root.addHandler(handler)
root.handlers = [handler]



queue_name = os.environ['queue_name']


if running_mode == 'development':


    queue_name = 'fiyatlar_crawl_detail_debug'

    # ### FIREFOX
    caps = DesiredCapabilities().FIREFOX
    # caps["pageLoadStrategy"] = "normal"  #  complete
    caps["pageLoadStrategy"] = "eager"  #  interactive
    # caps["pageLoadStrategy"] = "none"   #  undefined
    options = Options()
    options.headless = True
    options.add_argument("--host-resolver-rules=MAP www.google-analytics.com 127.0.0.1")
    options.add_argument("--host-resolver-rules=MAP analytics.google.com 127.0.0.1")


    from selenium import webdriver
    from selenium.webdriver.firefox.service import Service

    s=Service(os.path.abspath(os.getcwd()) + '/bin/geckodriver')#_'+ platform.system())
    #driver = webdriver.Firefox(service=s, options=options)
    #wait = WebDriverWait(driver, timeout=10)
    # using webdriver's install_addon API to install the downloaded Firefox extension
    # for file in glob.glob("*.xpi"):
    #     driver.install_addon(os.getcwd() + '/' + file, temporary=True)
    # ### FIREFOX

else:

    options=webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    #options.add_argument("window-size=1400,2100")
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')

    from selenium.webdriver.chrome.service import Service

    #driver=webdriver.Chrome(options=chrome_options, executable_path=os.path.abspath(os.getcwd()) + '/bin/chromedriver')
    s=Service(os.path.abspath(os.getcwd()) + '/bin/chromedriver-linux64/chromedriver')#_''+ platform.system())
    #driver = webdriver.Chrome(service=s, options=options)

    

client = MongoClient(mongo_host)
db = client.test_database
collection = db.test_collection

col_price_history = db.price_history
col_products = db.products
col_links = db.links

db_forum = client.dh_forum
collection_topicmeta = db_forum.TopicMeta

def upsert_link(url, domain, uid, price=0):
    now = datetime.datetime.utcnow()
    set_fields = {'uid': uid, 'domain': domain, 'last_checked_at': now, 'is_active': True}
    if price > 0:
        set_fields['last_successful_price_at'] = now
    try:
        col_links.update_one(
            {'url': url},
            {
                '$set': set_fields,
                '$setOnInsert': {'added_at': now, 'failure_count': 0}
            },
            upsert=True
        )
    except Exception as e:
        logging.error("links upsert error: %s", e)


def upsert_product(doc, price_history_7d, price_history_30d, price_history_90d, tag):
    now = datetime.datetime.utcnow()
    try:
        col_products.update_one(
            {'uid': doc['uid']},
            {
                '$set': {
                    'domain': doc['domain'],
                    'url': doc['url'],
                    'title': doc['title'],
                    'categories': doc['categories'],
                    'current_price': doc['price'],
                    'in_stock': doc['price'] > 0,
                    'last_checked_at': now,
                    'min_price_7d': min(price_history_7d) if price_history_7d else None,
                    'min_price_30d': min(price_history_30d) if price_history_30d else None,
                    'min_price_90d': min(price_history_90d) if price_history_90d else None,
                    'price_tag': tag,
                },
                '$setOnInsert': {'first_seen': now}
            },
            upsert=True
        )
    except Exception as e:
        logging.error("products upsert error: %s", e)


def insert_price_history(doc):
    try:
        col_price_history.insert_one({
            'uid': doc['uid'],
            'url': doc['url'],
            'price': doc['price'],
            'in_stock': doc['price'] > 0,
            'checked_at': datetime.datetime.utcnow(),
        })
    except Exception as e:
        logging.error("price_history insert error: %s", e)


def updateDB(doc):
    # try:
    #     replaceResult = collection.replace_one({'url': doc['url']}, doc, upsert=True)
    #     if replaceResult.matched_count == 1 or replaceResult.modified_count == 1 or replaceResult.upserted_id:
    #         logging.info('mongo upserted')
    #         return True
    #     else:
    #         logging.error('mongo error')
    # except Exception as e:
    #     logging.error("mongo error")
    #     logging.error(e)
    # return False
    return insertDB(doc)

def getPriceHistory(uid, day_limit):
    start = datetime.datetime.utcnow() + datetime.timedelta(days=-1*day_limit)
    price_history = []
    try:
        cursor = col_price_history.find(
            {"uid": uid, "checked_at": {"$gte": start}, "in_stock": True},
            {'price': 1}, no_cursor_timeout=True
        )
        for row in cursor:
            price_history.append(row['price'])
    except Exception as e:
        logging.error("mongo error")
        logging.error(e)
    return price_history

def updatePrice(url, price, tag, min_price, max_price):
    try:
        doc = {'Price': price, 'MaxPrice': max_price, 'MinPrice' : min_price, 'PriceTag' : tag, 'LastModified': datetime.datetime.utcnow().isoformat()}
        update_result = collection_topicmeta.update_many({"Url":url, "Type":"og"}, {"$set": {"PriceContent": doc, "Price": price}}, False)
        if update_result:
            logging.info(str(update_result.modified_count) + ' docs modified url=' + url)
            return True
        else:
            logging.error('mongo error')
    except Exception as e:
        logging.error("mongo error")
        logging.error(e)
    return False

def hasRecentRecord(uid):
    start = datetime.datetime.utcnow() + datetime.timedelta(days=-1)
    try:
        return col_price_history.count_documents(
            {"uid": uid, "checked_at": {"$gte": start}, "price": {"$gt": 0}}, limit=1
        ) > 0
    except Exception as e:
        logging.error("mongo error")
        logging.error(e)
    return False


def insertDB(doc):
    try:
        insertResult = collection.insert_one(doc)
        if insertResult:
            logging.info('mongo inserted' + str(insertResult.inserted_id))
            return True
        else:
            logging.error('mongo error')
    except Exception as e:
        logging.error("mongo error")
        logging.error(e)
    return False


def getAmazonPriceFromApi(asin):
    title = ''
    price = 0.0
    categories = []
    try:
        r = requests.get('https://forum.donanimhaber.com/paapi/?keywords='+asin)
        product = r.json()
        title = product['itemInfo']['title']['displayValue']
        price = product['offersV2']['listings'][0]['price']['money']['amount']
        for node in product['browseNodeInfo']['browseNodes']:
            display_name = node.get('contextFreeName') or node.get('displayName', '')
            if display_name and display_name != 'Kategoriler':
                categories.append(display_name)

        return title, price, categories
    except Exception as e:
        logging.error('amazon api error, %s', e)
        return '','', []
    

def seleniumFetcher(url):
    source = ''
    title = ''
    try:
        if running_mode == 'development':
            driver = webdriver.Firefox(service=s, options=options)
            wait = WebDriverWait(driver, timeout=10)
        else:
            driver = webdriver.Chrome(service=s, options=options)
        driver.set_page_load_timeout(10)
        logging.info('browser loaded')
        driver.get(url)
        timeout = 5
        try:
            element_present = EC.presence_of_element_located((By.ID, 'main'))
            WebDriverWait(driver, timeout).until(element_present)
        except TimeoutException:
            print("Timed out waiting for page to load")
        finally:
            print("Page loaded")
        
        source = driver.page_source
        title = driver.title
        driver.close()
    except Exception as e:
        logging.error("Could not fetch detail on {} ({})".format(url, e))
        return '', ''
    return source, title

def requestFetcher(o):
    headers = {
        "authority": o.hostname,
        "pragma":"no-cache",
        "cache-control":"no-cache",
        "upgrade-insecure-requests": "1",
        "user-agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "sec-gpc":"1",
        "sec-fetch-site":"same-origin",
        "sec-fetch-mode":"navigate",
        "sec-fetch-user":"?1",
        "sec-fetch-dest":"document",
        "referer":"https://"+ o.hostname +"/",     
        "accept-language":"en-US,en;q=0.9",
        "accept-encoding": "gzip, deflate"
    }
    source = ''
    try:
        r = requests.get(o.geturl(), headers=headers)
        source = r.content
    except:
        logging.error('could not fetch url ', o.geturl())
        return ''
    return source

def detail_parser(url, channel):
    url = urlClean(url)
    logging.info(url)
    o = urlparse(url)
    if o.hostname not in allowed_domains:
        return
    o = urlQSClean(o)

    source = None
    title = None
    price = None
    soup = None
    uid = ""
    categories = None
    status_code = 0
    #headers = {'User-Agent': 'Googlebot', 'referer': '://'.join([o.scheme, o.netloc])}
    #r = requests.get(url, headers=headers)
    #soup = BeautifulSoup(r.content, 'html.parser')
    soup = None
    uid = uidExtractor(o.path)

    # MD5 fallback (32 hex chars) means no known product pattern matched → not a product page
    if re.match(r'^[0-9a-f]{32}$', uid):
        logging.info('skipping non-product url: %s', url)
        return

    if o.hostname == "www.amazon.com.tr":
        title, price, categories = getAmazonPriceFromApi(uid)
    else:
        source, title, status_code, final_url = fetch_page(url)
        if status_code in (404, 410):
            logging.warning('no price (HTTP %d), will retry for 365 days: %s', status_code, url)
            col_links.update_one(
                {'url': url},
                {'$set': {'last_checked_at': datetime.datetime.utcnow()},
                 '$setOnInsert': {'added_at': datetime.datetime.utcnow(), 'is_active': True, 'failure_count': 0}},
                upsert=True
            )
            return
        if final_url != url:
            final_uid = uidExtractor(urlparse(final_url).path)
            if re.match(r'^[0-9a-f]{32}$', final_uid):
                logging.warning('no price (redirected to non-product %s), will retry for 365 days: %s', final_url, url)
                col_links.update_one(
                    {'url': url},
                    {'$set': {'last_checked_at': datetime.datetime.utcnow()},
                     '$setOnInsert': {'added_at': datetime.datetime.utcnow(), 'is_active': True, 'failure_count': 0}},
                    upsert=True
                )
                return

    if source:
        soup = BeautifulSoup(source, 'html.parser')
        logging.warning('source snippet [%s] (status=%d): %s', url, status_code, str(source)[:2000])
    else:
        logging.warning('empty source for %s', url)
    if not price and soup:
        price = priceExtractor(soup)
    if not title and soup:
        title = titleExtractor(soup)
    if not categories:
        categories = categoryExtractor(soup)

    if not price:
        price = 0.0
    logging.info('price=%.2f uid=%s url=%s', price, uid, url)
    full_uid = o.hostname + '-' + uid
    doc = buildDoc(url, o.hostname, o.path, title, price, full_uid, categories)

    recent = hasRecentRecord(full_uid)
    logging.info('hasRecentRecord=%s url=%s', recent, url)
    if not recent:
        updateDB(doc)
        if doc['price'] > 0:
            insert_price_history(doc)

    upsert_link(url, o.hostname, full_uid, price)

    price_history_7d = []
    price_history_30d = []
    price_history_90d = []
    tag = 0

    if price > 0:
        price_history_7d = getPriceHistory(full_uid, 7)
        price_history_30d = getPriceHistory(full_uid, 30)
        price_history_90d = getPriceHistory(full_uid, 90)

        conn = pymssql.connect(sql_host, sql_user, sql_pass, sql_db, tds_version='7.2')
        cursor = conn.cursor()
        cursor.execute("exec spPopularExternalLinks_Get_Order @link=%s", (url))
        row = cursor.fetchone()

        order_7d = 0
        order_30d = 0
        order_24h = 0
        while row:
            if row[0] == 0:
                order_24h = row[1]
            elif row[0] == 7:
                order_7d = row[1]
            elif row[0] == 30:
                order_30d = row[1]
            row = cursor.fetchone()
        conn.close()

        all_min = min(price_history_90d) if price_history_90d else price
        all_max = max(price_history_90d) if price_history_90d else price

        tag = computePriceTag(price, price_history_7d, price_history_30d, price_history_90d)

        # URUN FIYATI DUSTUYSE KUYRUGA YAZ
        if tag != 0:
            channel.basic_publish(exchange='', routing_key='fiyatlar_crawl_discount', body=url)

        # EN DUSUK FIYAT ETIKETI ALAMADIYSA, EN COK TIKLANANLAR ARASINDA MI KONTROLU
        if tag == 0 and order_24h == 1:
            tag = 5
        elif tag == 0 and order_7d == 1:
            tag = 6
        elif tag == 0 and order_30d == 1:
            tag = 7

        updatePrice(url, price, tag, all_min, all_max)

    upsert_product(doc, price_history_7d, price_history_30d, price_history_90d, tag)



def on_message(channel, method_frame, header_frame, body):
    detail_parser(body.decode(), channel)
    channel.basic_ack(delivery_tag=method_frame.delivery_tag)


all_endpoints = []

for endpoint in rabbit_host.split(','):
    all_endpoints.append(pika.URLParameters('amqp://{}:{}@{}'.format(rabbit_user, rabbit_pass, endpoint)))


@retry(pika.exceptions.AMQPConnectionError, delay=5, jitter=(1, 3))
def consume():
    random.shuffle(all_endpoints)
    connection = pika.BlockingConnection(all_endpoints)
    channel = connection.channel()
    channel.basic_qos(prefetch_count=1)

    ## This queue is intentionally non-durable. See http://www.rabbitmq.com/ha.html#non-mirrored-queue-behavior-on-node-failure
    ## to learn more.
    
    channel.basic_consume(queue_name, on_message)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
        connection.close()
    except pika.exceptions.ConnectionClosedByBroker:
        # Uncomment this to make the example not attempt recovery
        # from server-initiated connection closure, including
        # when the node is stopped cleanly
        # except pika.exceptions.ConnectionClosedByBroker:
        #     pass
        logging.info('continue')

consume()