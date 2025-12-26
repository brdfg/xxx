import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import time
import re
import json
from fastapi import FastAPI, Query
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(title="XHAccess HLS Extractor API")

# ---------------- HEADERS ----------------
def get_xhaccess_headers():
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": "https://www.google.com/"
    }

# ---------------- TPL FIX ----------------
def process_tpl_link(hls_link):
    if "_TPL_" not in hls_link:
        return hls_link

    decoded = unquote(hls_link)
    match = re.search(r'multi=([^/]+)', decoded)

    if match:
        res = re.findall(r'(\d+p)', match.group(1))
        if res:
            best = sorted(set(res), key=lambda x: int(x[:-1]))[-1]
            return hls_link.replace("_TPL_", best)

    return hls_link.replace("_TPL_", "720p")

# ---------------- VIDEO PAGE ----------------
def extract_hls(video_url, session):
    res = session.get(video_url, timeout=30, verify=False)
    soup = BeautifulSoup(res.text, "html.parser")

    title = soup.title.string if soup.title else "Unknown"

    hls = None

    preload = soup.find("link", rel="preload", attrs={"as": "fetch"})
    if preload and ".m3u8" in preload.get("href", ""):
        hls = preload["href"]

    if not hls:
        script = soup.find("script", id="initials-script")
        if script and script.string:
            try:
                data = json.loads(
                    script.string
                    .replace("window.initials=", "")
                    .rstrip(";")
                )
                hls = data["xplayerSettings"]["hls"]["h264"]["url"]
            except:
                pass

    if not hls:
        regex = r'(https.*?\.m3u8[^"\s]*)'
        for s in soup.find_all("script"):
            if s.string:
                m = re.search(regex, s.string)
                if m:
                    hls = m.group(1).replace("\\/", "/")
                    break

    if hls:
        return {
            "title": title,
            "hls": process_tpl_link(hls)
        }

    return None

# ---------------- API ENDPOINT ----------------
@app.get("/url")
def scrape(url: str = Query(..., description="xhaccess page or video url"),
           pages: int = 1):

    session = requests.Session()
    session.headers.update(get_xhaccess_headers())
    adapter = HTTPAdapter(max_retries=Retry(connect=3, backoff_factor=1))
    session.mount("https://", adapter)

    results = []

    # direct video
    if "/videos/" in url:
        data = extract_hls(url, session)
        return {"count": 1 if data else 0, "data": [data] if data else []}

    base = "https://xhaccess.com"
    current = url

    for _ in range(pages):
        r = session.get(current, timeout=30, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")

        links = soup.select("a.video-thumb__image-container")
        video_urls = list({
            urljoin(base, a.get("href"))
            for a in links if "/videos/" in a.get("href", "")
        })

        for v in video_urls:
            data = extract_hls(v, session)
            if data:
                results.append(data)
            time.sleep(0.5)

        next_btn = soup.select_one('a[rel="next"]')
        if not next_btn:
            break
        current = urljoin(base, next_btn.get("href"))

    return {
        "count": len(results),
        "data": results
    }
