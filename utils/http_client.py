import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
async def get(url: str, **kwargs) -> httpx.Response:
    client = get_client()
    response = await client.get(url, **kwargs)
    response.raise_for_status()
    return response


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
async def post(url: str, **kwargs) -> httpx.Response:
    client = get_client()
    response = await client.post(url, **kwargs)
    response.raise_for_status()
    return response
