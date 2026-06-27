import asyncio
from datetime import date
from app_store_scraper import AppStore
from .icp_filter import apply_icp_filter, extract_signals
from ...utils import cache
from ...utils.http_client import get as http_get


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        return None

QUERIES = [
    "yoga india", "ayurvedic wellness india", "skincare brand india",
    "baby products india", "organic food india", "home decor india",
    "diet nutrition india", "furniture india brand", "healthy snacks india",
    "D2C brand india",
]

_sem = asyncio.Semaphore(8)  # Allow more concurrency for speed


async def _itunes_search(query: str, limit: int) -> list[dict]:
    async with _sem:
        cache_key = f"itunes:{query}:{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        try:
            resp = await http_get(
                "https://itunes.apple.com/search",
                params={"term": query, "country": "in", "entity": "software",
                        "limit": limit, "lang": "en_us"},
            )
            results = resp.json().get("results", [])
            cache.set(cache_key, results)
            return results
        except Exception:
            return []


async def _fetch_detail(track_id: int) -> dict | None:
    async with _sem:
        try:
            resp = await asyncio.wait_for(
                http_get("https://itunes.apple.com/lookup",
                         params={"id": track_id, "country": "in"}),
                timeout=8.0,
            )
            items = resp.json().get("results", [])
            if not items:
                return None
            detail = items[0]
            if apply_icp_filter(detail, "apple"):
                return detail
        except Exception:
            pass
        return None


async def discover(search_limit: int = 30) -> list[dict]:
    search_tasks = [_itunes_search(q, search_limit) for q in QUERIES]
    all_results  = await asyncio.gather(*search_tasks)
    seen = set()
    unique = []
    for batch in all_results:
        for item in batch:
            tid = item.get("trackId")
            if tid and tid not in seen:
                seen.add(tid)
                unique.append(item)

    # Pre-filter before expensive detail fetch — cap at 60 candidates
    candidates = [item for item in unique if apply_icp_filter(item, "apple")][:60]
    detail_tasks = [_fetch_detail(item["trackId"]) for item in candidates]
    results = await asyncio.gather(*detail_tasks)
    return [r for r in results if r is not None]


def normalize_app(detail: dict) -> dict:
    d2c, pos = extract_signals(detail)
    return {
        "app_id":            str(detail.get("trackId")),
        "store":             "apple",
        "app_name":          detail.get("trackName"),
        "category":          detail.get("primaryGenreName"),
        "developer":         detail.get("sellerName"),
        "developer_email":   None,
        "developer_website": detail.get("sellerUrl"),
        "last_updated":      _parse_date(detail.get("currentVersionReleaseDate")),
        "rating":            detail.get("averageUserRating"),
        "installs":          str(detail.get("userRatingCount", 0)),
        "price":             str(detail.get("price", 0)),
        "d2c_signals":       ", ".join(d2c),
        "positive_keywords": ", ".join(pos),
    }
