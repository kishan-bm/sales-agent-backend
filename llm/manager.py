import uuid
from anthropic import RateLimitError, APIStatusError
from . import claude, gemini
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LLMManager:
    def __init__(self, db=None):
        self._db = db  # optional AsyncSession for audit logging

    async def generate(
        self,
        prompt: str,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 1024,
        app_id: uuid.UUID | None = None,
        collector: str | None = None,
    ) -> str:
        result = None
        used_model = model

        try:
            result = await claude.generate(prompt, model=model, max_tokens=max_tokens)
        except (RateLimitError, APIStatusError) as e:
            logger.warning("llm.claude_fallback", error=str(e), collector=collector)
            result = await gemini.generate(prompt, max_tokens=max_tokens)
            used_model = result["model"]

        await self._audit(result, app_id, collector)
        return result["text"]

    async def _audit(self, result: dict, app_id, collector):
        if self._db is None:
            return
        from ..database.repository import log_llm_call
        await log_llm_call(self._db, {
            "app_id":            app_id,
            "collector":         collector,
            "model":             result["model"],
            "prompt_tokens":     result["prompt_tokens"],
            "completion_tokens": result["completion_tokens"],
            "cost_usd":          result["cost_usd"],
            "latency_ms":        result["latency_ms"],
        })
        logger.info(
            "llm.call",
            model=result["model"],
            cost_usd=result["cost_usd"],
            latency_ms=result["latency_ms"],
            collector=collector,
        )
