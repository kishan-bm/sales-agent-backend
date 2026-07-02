import asyncio
from datetime import date
from google_play_scraper import search, app as get_app
from .icp_filter import apply_icp_filter, extract_signals

QUERIES = [
    "yoga app india", "protein supplement india", "ayurvedic wellness india",
    "skincare india brand", "baby products india", "organic food india",
    "home decor india", "fitness membership india", "diet nutrition india",
    "kids learning india", "furniture brand india", "healthy snacks india",
    "hair care india brand", "face wash india brand", "health supplement india",
    "D2C brand india", "beauty brand india", "wellness india brand",
    "clothing brand india app", "jewellery india brand", "pet care india",
    "personal care india", "natural products india", "herbal india brand",
    "sports nutrition india", "ethnic wear india", "artisan india brand",
    "grocery delivery india brand", "sustainable india brand", "tea india brand",
]

_sem = asyncio.Semaphore(8)


async def _search_one(query: str, limit: int) -> list[str]:
    async with _sem:
        try:
            results = await asyncio.to_thread(
                search, query, lang="en", country="in", n_hits=limit
            )
            return [r["appId"] for r in results]
        except Exception:
            return []


async def _fetch_detail(app_id: str) -> dict | None:
    async with _sem:
        try:
            detail = await asyncio.wait_for(
                asyncio.to_thread(get_app, app_id, lang="en", country="in"),
                timeout=10.0,
            )
            if apply_icp_filter(detail, "play"):
                return detail
        except Exception:
            pass
        return None


async def discover(search_limit: int = 30) -> list[dict]:
    search_tasks = [_search_one(q, search_limit) for q in QUERIES]
    all_id_lists = await asyncio.gather(*search_tasks)
    unique_ids = list({aid for sublist in all_id_lists for aid in sublist})[:250]

    detail_tasks = [_fetch_detail(app_id) for app_id in unique_ids]
    results = await asyncio.gather(*detail_tasks)
    return [r for r in results if r is not None]


def normalize_app(detail: dict) -> dict:
    d2c, pos = extract_signals(detail)
    updated = detail.get("updated")
    if isinstance(updated, (int, float)):
        try:
            updated = date.fromtimestamp(updated)
        except (OSError, OverflowError):
            updated = None
    return {
        "app_id":            detail.get("appId"),
        "store":             "google_play",
        "app_name":          detail.get("title"),
        "category":          detail.get("genre"),
        "developer":         detail.get("developer"),
        "developer_email":   detail.get("developerEmail"),
        "developer_website": detail.get("developerWebsite"),
        "last_updated":      updated,
        "rating":            detail.get("score"),
        "installs":          detail.get("installs"),
        "price":             str(detail.get("price", 0)),
        "d2c_signals":       ", ".join(d2c),
        "positive_keywords": ", ".join(pos),
    }
