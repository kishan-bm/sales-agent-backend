import re
import httpx
from ..utils.http_client import get as http_get
from ..utils.config import SERPAPI_KEY
from ..utils import cache
from ..utils.logger import get_logger

logger = get_logger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/"
_DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def _ddg_search(query: str, num: int) -> list[dict]:
    """Free DuckDuckGo web search — used when SERPAPI_KEY is absent."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(
                _DDG_URL,
                data={"q": query, "b": "", "kl": "in-en"},
                headers=_DDG_HEADERS,
            )
        html = resp.text

        # Pull result links + titles
        titles   = re.findall(r'class="result__a"[^>]*>([^<]+)</a>', html)
        links    = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html)
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)</', html)

        results = []
        for i in range(min(num, len(links))):
            link = links[i].strip()
            # DDG wraps URLs in a redirect — unwrap if needed
            if "uddg=" in link:
                from urllib.parse import unquote, parse_qs, urlparse
                qs = parse_qs(urlparse(link).query)
                link = unquote(qs.get("uddg", [link])[0])
            results.append({
                "title":   titles[i].strip() if i < len(titles) else "",
                "link":    link,
                "snippet": snippets[i].strip() if i < len(snippets) else "",
            })
        logger.info("ddg.search.ok", query=query[:60], results=len(results))
        return results
    except Exception as e:
        logger.warning("ddg.search.failed", query=query[:60], error=str(e))
        return []


async def search(query: str, num: int = 10) -> list[dict]:
    cache_key = f"serp:{query}:{num}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if SERPAPI_KEY and not SERPAPI_KEY.startswith("your_"):
        try:
            resp = await http_get(
                "https://serpapi.com/search",
                params={"q": query, "api_key": SERPAPI_KEY, "num": num, "engine": "google"},
            )
            results = resp.json().get("organic_results", [])
            cache.set(cache_key, results)
            return results
        except Exception as e:
            logger.warning("serpapi.failed.fallback_ddg", error=str(e)[:80])

    # Fallback: DuckDuckGo (no key required)
    results = await _ddg_search(query, num)
    cache.set(cache_key, results)
    return results


async def search_play_store(query: str, country: str = "in", num: int = 20) -> list[dict]:
    """Play Store search — uses SerpAPI engine if key available, else google-play-scraper."""
    cache_key = f"serp_play:{query}:{country}:{num}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if SERPAPI_KEY and not SERPAPI_KEY.startswith("your_"):
        try:
            resp = await http_get(
                "https://serpapi.com/search",
                params={"engine": "google_play", "q": query, "gl": country,
                        "api_key": SERPAPI_KEY, "num": num},
            )
            results = resp.json().get("organic_results", [])
            cache.set(cache_key, results)
            return results
        except Exception:
            pass

    # Fallback: direct google-play-scraper (no key)
    try:
        from google_play_scraper import search as gplay_search
        import asyncio
        raw = await asyncio.to_thread(gplay_search, query, lang="en", country=country, n_hits=num)
        results = [{"title": r.get("title"), "link": f"https://play.google.com/store/apps/details?id={r.get('appId')}", "snippet": r.get("description", "")[:200]} for r in raw]
        cache.set(cache_key, results)
        return results
    except Exception as e:
        logger.warning("gplay_search.failed", error=str(e)[:80])
        return []
