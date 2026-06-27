import json
from ..base import BaseCollector
from ...services import clearbit_service, serp_service
from ...utils import http_client


class CompanyIntelCollector(BaseCollector):
    name = "company_intel"

    async def collect(self) -> dict:
        website = self.app.get("developer_website") or ""
        domain  = self._extract_domain(website)
        company = self.app.get("developer") or self.app.get("app_name", "")

        clearbit_data = {}
        if domain:
            raw = await clearbit_service.enrich_domain(domain)
            if raw:
                clearbit_data = raw

        website_text = await self._scrape_website(website)
        serp_results = await serp_service.search(f'"{company}" site:crunchbase.com', num=3)
        crunchbase_url = serp_results[0]["link"] if serp_results else None

        structured = await self._extract_structured(company, website_text, clearbit_data)

        signals = []
        emp = clearbit_data.get("metrics", {}).get("employeesRange") or structured.get("employee_count_range")
        if emp and emp not in ("1-10", "unknown"):
            signals.append(f"Company size: {emp} employees")
        if structured.get("funding_stage"):
            signals.append(f"Funding: {structured['funding_stage']}")
        if structured.get("recent_news_headlines"):
            signals.append(f"Recent news: {structured['recent_news_headlines'][0]}")

        confidence = 0.8 if clearbit_data else (0.5 if website_text else 0.2)

        return {
            "data": {
                "company_name":          clearbit_data.get("name") or company,
                "website":               website,
                "industry":              clearbit_data.get("category", {}).get("industry") or structured.get("industry"),
                "headquarters":          clearbit_data.get("geo", {}).get("city") or structured.get("headquarters"),
                "employee_count_range":  emp or "unknown",
                "founded_year":          clearbit_data.get("foundedYear") or structured.get("founded_year"),
                "funding_stage":         structured.get("funding_stage"),
                "funding_amount_usd":    structured.get("funding_amount_usd"),
                "technologies":          clearbit_data.get("tech") or [],
                "recent_news_headlines": structured.get("recent_news_headlines", []),
                "linkedin_company_url":  clearbit_data.get("linkedin", {}).get("handle"),
                "crunchbase_url":        crunchbase_url,
            },
            "confidence": confidence,
            "signals":    signals,
            "error":      None,
        }

    def _extract_domain(self, url: str) -> str:
        if not url:
            return ""
        url = url.replace("https://", "").replace("http://", "").split("/")[0]
        return url.lstrip("www.")

    async def _scrape_website(self, url: str) -> str:
        if not url:
            return ""
        try:
            resp = await http_client.get(url)
            text = resp.text
            # crude HTML strip
            import re
            return re.sub(r"<[^>]+>", " ", text)[:3000]
        except Exception:
            return ""

    async def _extract_structured(self, company: str, website_text: str, clearbit: dict) -> dict:
        if not website_text and not clearbit:
            return {}
        prompt = f"""Extract company information as JSON from the text below.
Company name: {company}

Website text (first 2000 chars):
{website_text[:2000]}

Return ONLY valid JSON with these fields:
{{
  "industry": string or null,
  "headquarters": string or null,
  "founded_year": integer or null,
  "funding_stage": "seed"|"series_a"|"series_b"|"series_c+"|"bootstrapped"|"public"|null,
  "funding_amount_usd": integer or null,
  "recent_news_headlines": [list of up to 3 strings],
  "employee_count_range": string or null
}}"""
        try:
            text = await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
            start = text.find("{")
            end   = text.rfind("}") + 1
            return json.loads(text[start:end]) if start >= 0 else {}
        except Exception:
            return {}
