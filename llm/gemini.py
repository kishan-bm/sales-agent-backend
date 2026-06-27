import time
import google.generativeai as genai
from ..utils.config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel("gemini-1.5-flash")

GEMINI_COST_PER_1K = {"input": 0.000075, "output": 0.0003}


async def generate(prompt: str, model: str = "gemini-1.5-flash", max_tokens: int = 1024) -> dict:
    start = time.monotonic()
    # google-generativeai is sync — run in thread to avoid blocking event loop
    import asyncio
    response = await asyncio.to_thread(_model.generate_content, prompt)
    latency_ms = int((time.monotonic() - start) * 1000)

    text = response.text
    # Gemini doesn't expose token counts on the free tier reliably; estimate
    prompt_tokens = len(prompt) // 4
    output_tokens = len(text) // 4
    cost = (prompt_tokens / 1000 * GEMINI_COST_PER_1K["input"]) + \
           (output_tokens / 1000 * GEMINI_COST_PER_1K["output"])

    return {
        "text":             text,
        "model":            "gemini-1.5-flash",
        "prompt_tokens":    prompt_tokens,
        "completion_tokens": output_tokens,
        "cost_usd":         round(cost, 6),
        "latency_ms":       latency_ms,
    }
