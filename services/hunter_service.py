from ..utils.http_client import get as http_get
from ..utils.config import HUNTER_API_KEY
from ..utils import cache


async def find_email(domain: str, first_name: str = "", last_name: str = "") -> dict | None:
    if not domain or not HUNTER_API_KEY:
        return None

    cache_key = f"hunter:{domain}:{first_name}:{last_name}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    params = {"domain": domain, "api_key": HUNTER_API_KEY}
    if first_name:
        params["first_name"] = first_name
    if last_name:
        params["last_name"] = last_name

    endpoint = "email-finder" if first_name else "domain-search"
    resp = await http_get(f"https://api.hunter.io/v2/{endpoint}", params=params)
    data = resp.json().get("data", {})
    cache.set(cache_key, data)
    return data


async def domain_search(domain: str) -> list[dict]:
    data = await find_email(domain)
    if not data:
        return []
    return data.get("emails", [])
