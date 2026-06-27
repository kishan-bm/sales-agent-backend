import time
import anthropic
from ..utils.config import ANTHROPIC_API_KEY

_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

COST_PER_1K = {
    "claude-haiku-4-5-20251001":  {"input": 0.00025, "output": 0.00125},
    "claude-sonnet-4-6":          {"input": 0.003,   "output": 0.015},
}


async def generate(prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 1024) -> dict:
    start = time.monotonic()
    message = await _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    input_t  = message.usage.input_tokens
    output_t = message.usage.output_tokens
    rates    = COST_PER_1K.get(model, {"input": 0.003, "output": 0.015})
    cost     = (input_t / 1000 * rates["input"]) + (output_t / 1000 * rates["output"])

    return {
        "text":             message.content[0].text,
        "model":            model,
        "prompt_tokens":    input_t,
        "completion_tokens": output_t,
        "cost_usd":         round(cost, 6),
        "latency_ms":       latency_ms,
    }
