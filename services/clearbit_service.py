from ..utils.http_client import get as http_get
from ..utils.config import CLEARBIT_API_KEY
from ..utils import cache
import httpx


async def enrich_domain(domain: str) -> dict | None:
    if not domain or not CLEARBIT_API_KEY:
        return None

    cache_key = f"clearbit:{domain}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        resp = await http_get(
            f"https://company.clearbit.com/v2/companies/find",
            params={"domain": domain},
            headers={"Authorization": f"Bearer {CLEARBIT_API_KEY}"},
        )
        data = resp.json()
        cache.set(cache_key, data)
        return data
    except httpx.HTTPStatusError as e:
        # 401 = no/wrong key, 404/422 = domain not found — all non-fatal
        if e.response.status_code in (401, 403, 404, 422):
            return None
        raise
