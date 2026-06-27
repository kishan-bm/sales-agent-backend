import asyncio
from . import play_store, apple_store
from ...database.repository import AsyncSessionLocal, upsert_app
from ...utils.logger import get_logger

logger = get_logger(__name__)


async def run_discovery(play_search_limit: int = 50, apple_search_limit: int = 50) -> int:
    logger.info("discovery.start")

    play_apps, apple_apps = await asyncio.gather(
        play_store.discover(play_search_limit),
        apple_store.discover(apple_search_limit),
    )

    logger.info("discovery.raw", play=len(play_apps), apple=len(apple_apps))

    async with AsyncSessionLocal() as db:
        saved = 0
        for detail in play_apps:
            app_data = play_store.normalize_app(detail)
            await upsert_app(db, app_data)
            saved += 1
        for detail in apple_apps:
            app_data = apple_store.normalize_app(detail)
            await upsert_app(db, app_data)
            saved += 1

    logger.info("discovery.done", saved=saved)
    return saved


if __name__ == "__main__":
    count = asyncio.run(run_discovery())
    print(f"\nDiscovered and saved {count} ICP-matching apps to DB.")
