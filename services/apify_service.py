import asyncio
from ..utils.http_client import get as http_get, post as http_post
from ..utils.config import APIFY_API_KEY
from ..utils import cache


PLAY_STORE_ACTOR = "vacancy.apify-google-play-scraper"


async def scrape_play_store(query: str, country: str = "in", limit: int = 50) -> list[dict]:
    if not APIFY_API_KEY:
        return []

    cache_key = f"apify_play:{query}:{country}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Start actor run
    run_resp = await http_post(
        f"https://api.apify.com/v2/acts/{PLAY_STORE_ACTOR}/runs",
        params={"token": APIFY_API_KEY},
        json={"search": query, "country": country, "maxResults": limit},
    )
    run_id = run_resp.json()["data"]["id"]

    # Poll until finished (max 2 minutes)
    for _ in range(24):
        await asyncio.sleep(5)
        status_resp = await http_get(
            f"https://api.apify.com/v2/acts/{PLAY_STORE_ACTOR}/runs/{run_id}",
            params={"token": APIFY_API_KEY},
        )
        if status_resp.json()["data"]["status"] == "SUCCEEDED":
            break

    dataset_id = status_resp.json()["data"]["defaultDatasetId"]
    items_resp = await http_get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_API_KEY},
    )
    results = items_resp.json()
    cache.set(cache_key, results)
    return results
