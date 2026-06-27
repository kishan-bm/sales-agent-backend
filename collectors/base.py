from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from ..database.repository import upsert_evidence
from ..llm.manager import LLMManager
from ..utils.logger import get_logger
import time
import uuid


class BaseCollector(ABC):
    name: str = "base"

    def __init__(self, app: dict, db: AsyncSession):
        self.app  = app
        self.db   = db
        self.llm  = LLMManager(db)
        self.log  = get_logger(self.__class__.__name__)
        self._app_uuid = uuid.UUID(str(app["id"])) if app.get("id") else None

    async def run(self) -> dict:
        start = time.monotonic()
        self.log.info("collector.start", collector=self.name, app_id=str(self._app_uuid))
        try:
            result = await self.collect()
            result["collector"] = self.name
            duration = int((time.monotonic() - start) * 1000)
            self.log.info("collector.done", collector=self.name, duration_ms=duration,
                          confidence=result.get("confidence", 0))
            if self._app_uuid:
                await upsert_evidence(self.db, self._app_uuid, self.name, result)
            return result
        except Exception as e:
            self.log.error("collector.error", collector=self.name, error=str(e))
            err = {"collector": self.name, "data": {}, "confidence": 0.0,
                   "signals": [], "error": str(e)}
            if self._app_uuid:
                await upsert_evidence(self.db, self._app_uuid, self.name, err)
            return err

    @abstractmethod
    async def collect(self) -> dict:
        """Return: {data: dict, confidence: float, signals: list[str], error: str|None}"""
