import json
from ..base import BaseCollector
from ...services import serp_service


class SocialCollector(BaseCollector):
    name = "social"

    async def collect(self) -> dict:
        company = self.app.get("developer") or self.app.get("app_name", "")

        li_results  = await serp_service.search(f'"{company}" site:linkedin.com/company', num=3)
        post_results = await serp_service.search(f'"{company}" mobile app news OR launch OR update 2024 2025', num=5)

        linkedin_url = li_results[0]["link"] if li_results else None
        posts_text   = "\n".join(r.get("snippet", "") for r in post_results)

        classified = await self._classify_signals(company, posts_text)

        signals = []
        if classified.get("buying_signals"):
            signals += classified["buying_signals"][:3]
        flags = classified.get("signal_flags", {})
        if flags.get("mobile_rewrite"):
            signals.append("Signal: company discussing mobile app rewrite/rebuild")
        if flags.get("ai_adoption"):
            signals.append("Signal: company exploring AI/tech adoption")

        return {
            "data": {
                "linkedin_company_url":        linkedin_url,
                "linkedin_last_post_days_ago": None,
                "linkedin_topics":             classified.get("topics", []),
                "founder_name":                classified.get("founder_name"),
                "founder_linkedin_url":        classified.get("founder_linkedin_url"),
                "founder_last_active_days_ago": None,
                "buying_signals":              classified.get("buying_signals", []),
                "signal_flags":                flags,
                "best_signal_quote":           classified.get("best_signal_quote"),
            },
            "confidence": 0.6,
            "signals": signals,
            "error": None,
        }

    async def _classify_signals(self, company: str, text: str) -> dict:
        if not text.strip():
            return {}
        prompt = f"""Analyze this news/social content about "{company}" and return JSON:
{{
  "buying_signals": [list of strings — reasons they might need our help],
  "signal_flags": {{
    "product_launch": bool, "funding": bool, "mobile_rewrite": bool,
    "hiring": bool, "ai_adoption": bool, "acquisition": bool
  }},
  "topics": [list of 3-5 topic strings],
  "founder_name": string or null,
  "founder_linkedin_url": string or null,
  "best_signal_quote": string or null
}}

Content:
{text[:2000]}"""
        try:
            raw = await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                          app_id=self._app_uuid, collector=self.name)
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            return json.loads(raw[start:end]) if start >= 0 else {}
        except Exception:
            return {}
