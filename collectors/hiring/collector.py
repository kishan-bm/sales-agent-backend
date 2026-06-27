from ..base import BaseCollector
from ...services import serp_service

JOB_TITLES = ["android", "ios", "flutter", "react native", "mobile developer",
               "mobile engineer", "app developer", "kotlin", "swift"]


class HiringCollector(BaseCollector):
    name = "hiring"

    async def collect(self) -> dict:
        company = self.app.get("developer") or self.app.get("app_name", "")
        query   = f'"{company}" android OR iOS OR flutter OR "mobile developer" site:linkedin.com/jobs'
        serp_results = await serp_service.search(query, num=10)
        jobs = [{"title": r.get("title", ""), "url": r.get("link", "")}
                for r in serp_results
                if any(kw in r.get("title", "").lower() for kw in JOB_TITLES)]

        frameworks = [f for f in ["flutter", "react native", "kotlin", "swift"]
                      if any(f in j["title"].lower() for j in jobs)]
        has_senior = any("senior" in j["title"].lower() or "lead" in j["title"].lower()
                         for j in jobs)
        strength = "strong" if len(jobs) >= 3 else "moderate" if len(jobs) >= 1 else "none"

        signals = []
        if jobs:
            signals.append(f"Hiring {len(jobs)} mobile role(s): {', '.join(j['title'] for j in jobs[:3])}")
        if "flutter" in frameworks or "react native" in frameworks:
            signals.append("Hiring Flutter/RN — possible full app rebuild")
        if has_senior:
            signals.append("Senior/lead mobile roles open — investing in engineering")

        # LLM: interpret what the hiring pattern means for a sales opportunity
        llm_insight = await self._llm_insight(company, jobs, frameworks, has_senior)
        if llm_insight:
            signals.append(llm_insight)

        return {
            "data": {
                "is_hiring_mobile":       len(jobs) > 0,
                "mobile_job_count":       len(jobs),
                "job_titles":             [j["title"] for j in jobs],
                "frameworks_sought":      frameworks,
                "hiring_signal_strength": strength,
                "signal_interpretation":  llm_insight or f"{len(jobs)} active mobile job postings found",
                "job_urls":               [j["url"] for j in jobs],
            },
            "confidence": 0.7,
            "signals": signals,
            "error": None,
        }

    async def _llm_insight(self, company: str, jobs: list, frameworks: list, has_senior: bool) -> str:
        if not jobs:
            return ""
        titles_str = ", ".join(j["title"] for j in jobs[:5])
        prompt = (
            f"Company: {company}\n"
            f"Open mobile job postings: {titles_str}\n"
            f"Frameworks sought: {', '.join(frameworks) if frameworks else 'not specified'}\n"
            f"Has senior/lead roles: {has_senior}\n\n"
            f"In ONE sentence (max 20 words), what does this hiring pattern tell us about "
            f"their mobile app investment plans? Focus on sales opportunity."
        )
        try:
            return await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
        except Exception:
            return ""
