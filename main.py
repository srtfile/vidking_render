"""
vidking.net m3u8 / stream URL extractor
Render-deployable FastAPI web service.

Endpoints:
  GET /extract?tmdb=76479&type=tv&season=5&episode=8
  GET /extract?tmdb=550&type=movie
  GET /extract?url=https://www.vidking.net/embed/tv/76479/5/8/
"""

import asyncio
import re
import time

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="VidKing Stream Extractor")

DEFAULT_URL = "https://www.vidking.net/embed/tv/76479/5/8/"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://www.vidking.net",
    "referer": "https://www.vidking.net/",
    "user-agent": UA,
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "sec-fetch-site": "cross-site",
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def parse_embed_url(url: str):
    m = re.search(r"/embed/(tv|movie)/(\d+)(?:/(\d+)/(\d+))?", url)
    if not m:
        raise ValueError(f"Cannot parse embed URL: {url}")
    return m.group(1), m.group(2), m.group(3), m.group(4)


# ─────────────────────────────────────────────
# Metadata
# ─────────────────────────────────────────────

def get_show_meta(tmdb_id: str, media_type: str = "tv"):
    url = f"https://db.videasy.to/3/{media_type}/{tmdb_id}"
    r = requests.get(
        url,
        params={"append_to_response": "external_ids"},
        headers=BASE_HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    title = data.get("name") or data.get("title", "")
    year = (data.get("first_air_date") or data.get("release_date") or "")[:4]
    imdb_id = (data.get("external_ids") or {}).get("imdb_id", "")
    return title, year, imdb_id


# ─────────────────────────────────────────────
# Direct API extraction
# ─────────────────────────────────────────────

def try_direct_api(media_type: str, tmdb_id: str, season: str, episode: str) -> list:
    try:
        title, year, imdb_id = get_show_meta(tmdb_id, media_type)
    except Exception:
        title, year, imdb_id = "", "", ""

    params = {
        "title": title,
        "mediaType": media_type,
        "year": year,
        "tmdbId": tmdb_id,
        "imdbId": imdb_id,
        "_t": str(int(time.time() * 1000)),
    }
    if media_type == "tv" and season and episode:
        params["episodeId"] = episode
        params["seasonId"] = season

    r = requests.get(
        "https://api.videasy.net/mb-flix/sources-with-title",
        params=params,
        headers=BASE_HEADERS,
        timeout=20,
    )

    if r.status_code != 200:
        return []

    text = r.text
    urls = re.findall(r'https?://[^\s"\'\\<>]+\.m3u8[^\s"\'\\<>]*', text)
    if not urls:
        urls = re.findall(r'https?://[^\s"\'\\<>]+\.mpd[^\s"\'\\<>]*', text)
    return list(dict.fromkeys(urls))


# ─────────────────────────────────────────────
# Playwright fallback
# ─────────────────────────────────────────────

async def extract_with_playwright(embed_url: str, timeout: int = 45) -> list:
    from playwright.async_api import async_playwright

    found = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA,
            extra_http_headers={"accept-language": "en-US,en;q=0.9"},
        )
        page = await ctx.new_page()

        async def on_response(response):
            url = response.url
            if re.search(r'\.(m3u8|mpd)(\?|$)', url):
                if url not in found:
                    found.append(url)
            if "sources-with-title" in url and response.status == 200:
                try:
                    body = await response.body()
                    text = body.decode("utf-8", errors="ignore")
                    for u in re.findall(r'https?://[^\s"\'\\<>]+\.m3u8[^\s"\'\\<>]*', text):
                        if u not in found:
                            found.append(u)
                    for u in re.findall(r'https?://[^\s"\'\\<>]+\.mpd[^\s"\'\\<>]*', text):
                        if u not in found:
                            found.append(u)
                except Exception:
                    pass

        page.on("response", on_response)
        await page.goto(embed_url, wait_until="networkidle", timeout=timeout * 1000)

        deadline = time.time() + 15
        while not found and time.time() < deadline:
            await page.wait_for_timeout(1000)

        await browser.close()

    return found


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "VidKing Stream Extractor is running."}


@app.get("/extract")
async def extract(
    tmdb: str = Query(None, description="TMDB ID"),
    type: str = Query("tv", description="tv or movie"),
    season: str = Query("1"),
    episode: str = Query("1"),
    url: str = Query(None, description="Full embed URL (overrides tmdb)"),
    playwright_only: bool = Query(False),
    timeout: int = Query(45),
):
    # Build embed URL
    if url:
        embed_url = url
        media_type, tmdb_id, season, episode = parse_embed_url(url)
    elif tmdb:
        media_type = type
        tmdb_id = tmdb
        embed_url = (
            f"https://www.vidking.net/embed/{media_type}/{tmdb_id}"
            + (f"/{season}/{episode}/" if media_type == "tv" else "/")
        )
    else:
        raise HTTPException(status_code=400, detail="Provide either 'tmdb' or 'url' query param.")

    urls = []

    # Step 1: direct API
    if not playwright_only:
        urls = try_direct_api(media_type, tmdb_id, season, episode)

    # Step 2: Playwright fallback
    if not urls:
        try:
            urls = await extract_with_playwright(embed_url, timeout=timeout)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Playwright error: {e}")

    if not urls:
        raise HTTPException(status_code=404, detail="No stream URLs found.")

    return JSONResponse({"embed_url": embed_url, "count": len(urls), "urls": urls})