import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import time
import re
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

from fastapi import FastAPI, Query

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="XHAccess API")

# ------------------------------------------------

def get_xhaccess_headers():
    return {
        "Host": "xhaccess.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

# ------------------------------------------------

def process_tpl_link(hls_link):
    try:
        if "_TPL_" not in hls_link:
            return hls_link

        decoded_link = unquote(hls_link)
        multi_match = re.search(r'multi=([^/]+)', decoded_link)

        if multi_match:
            res_labels = re.findall(r'(\d+p)', multi_match.group(1))
            if res_labels:
                best_res = sorted(
                    set(res_labels),
                    key=lambda x: int(x.replace('p', ''))
                )[-1]
                return hls_link.replace('_TPL_', best_res)

        return hls_link.replace('_TPL_', '720p')

    except:
        return hls_link

# ------------------------------------------------

def extract_hls_from_video(video_url, session, results):
    try:
        response = session.get(video_url, timeout=30, verify=False)
        if response.status_code != 200:
            return

        soup = BeautifulSoup(response.text, 'html.parser')

        title = "Unknown Title"
        if soup.select_one('h1'):
            title = soup.select_one('h1').get_text(strip=True)
        elif soup.title:
            title = soup.title.string.replace(" - xHamster.com", "").replace(" - xhaccess.com", "").strip()

        hls_link = None

        preload = soup.find('link', rel='preload', attrs={'as': 'fetch'})
        if preload and preload.get('href') and '.m3u8' in preload.get('href'):
            hls_link = preload.get('href')

        if not hls_link:
            script = soup.find('script', id='initials-script')
            if script and script.string:
                try:
                    data = json.loads(
                        script.string
                        .replace('window.initials=', '')
                        .rstrip(';')
                    )
                    hls = data.get('xplayerSettings', {}).get('hls', {})
                    if 'h264' in hls:
                        hls_link = hls['h264'].get('url')
                    elif 'av1' in hls:
                        hls_link = hls['av1'].get('url')
                except:
                    pass

        if not hls_link:
            regex = r'(https.*?\.m3u8[^"\s]*)'
            for s in soup.find_all('script'):
                if s.string:
                    m = re.search(regex, s.string)
                    if m:
                        hls_link = m.group(1).replace('\\/', '/')
                        break

        if hls_link:
            results.append({
                "title": title,
                "hls": process_tpl_link(hls_link)
            })

    except:
        pass

# ------------------------------------------------

def scrape_xhaccess(start_url, max_pages=1):
    base_domain = "https://xhaccess.com"

    session = requests.Session()
    session.headers.update(get_xhaccess_headers())

    adapter = HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=1))
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    results = []

    if "/videos/" in start_url:
        extract_hls_from_video(start_url, session, results)
        return results

    current_url = start_url
    visited = set()
    pages = 0

    while current_url and pages < max_pages:
        if current_url in visited:
            break

        visited.add(current_url)
        pages += 1

        response = session.get(current_url, timeout=30, verify=False)
        soup = BeautifulSoup(response.text, 'html.parser')

        video_links = soup.select('a.video-thumb__image-container')
        urls = list({
            urljoin(base_domain, a.get('href'))
            for a in video_links if "/videos/" in a.get('href', '')
        })

        for v in urls:
            extract_hls_from_video(v, session, results)

        next_btn = soup.select_one('a[rel="next"]')
        if next_btn:
            current_url = urljoin(base_domain, next_btn.get('href'))
        else:
            break

    return results

# ------------------------------------------------
# 🔥 API ENDPOINT (BAS YE ADD HUA HAI)
# ------------------------------------------------

@app.get("/url")
def api(url: str = Query(...), pages: int = 1):
    data = scrape_xhaccess(url, pages)
    return {
        "count": len(data),
        "data": data
    }
