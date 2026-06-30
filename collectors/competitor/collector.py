import asyncio
import json
from google_play_scraper import search as gplay_search
from ..base import BaseCollector
from ...services import serp_service

# These dominate any broad "shopping app India" search — exclude them
MARKETPLACE_NAMES = {
    "amazon", "flipkart", "myntra", "ajio", "meesho", "snapdeal",
    "tatacliq", "nykaa", "bigbasket", "blinkit", "swiggy", "zomato",
    "paytm", "phonepe", "zepto",
}


def _is_marketplace(name: str) -> bool:
    n = name.lower()
    return any(m in n for m in MARKETPLACE_NAMES)


class CompetitorCollector(BaseCollector):
    name = "competitor"

    async def collect(self) -> dict:
        category  = self.app.get("category", "")
        app_name  = self.app.get("app_name", "")
        rating    = self.app.get("rating") or 0.0

        # Search using app name + category for more specific competitors
        query = f"apps like {app_name} {category} India alternative"
        serp = await serp_service.search(query, num=10)
        competitors = [{"name": r.get("title", ""), "rating": 0, "installs": ""}
                       for r in serp if not _is_marketplace(r.get("title", ""))]

        # Play Store search for same niche with real ratings
        if self.app.get("store") == "google_play":
            try:
                play_results = await asyncio.to_thread(
                    gplay_search, f"{app_name} {category} india", lang="en", country="in", n_hits=8
                )
                # Exclude the target app itself and marketplaces
                own_id = self.app.get("app_id", "")
                filtered = [
                    {"name": a["title"], "rating": a.get("score", 0), "installs": a.get("installs", "")}
                    for a in play_results
                    if a.get("appId") != own_id and not _is_marketplace(a.get("title", ""))
                ]
                if filtered:
                    competitors = filtered
            except Exception:
                pass

        rated = [c for c in competitors if c.get("rating")]
        cat_avg = sum(c["rating"] for c in rated) / len(rated) if rated else 0.0
        # Only compute gap when we actually have competitor ratings; negative = app is better
        rating_gap = round(cat_avg - rating, 2) if cat_avg > 0 else 0.0
        pressure = "high" if rating_gap > 1.5 else "medium" if rating_gap > 0.5 else "low"

        missing = await self._find_missing_features(app_name, category, competitors)

        signals = []
        if rating_gap > 1.0:
            signals.append(f"Rating gap: {rating_gap:.1f}★ behind direct competitors")
        if missing:
            signals.append(f"Missing features vs competitors: {', '.join(missing[:3])}")

        return {
            "data": {
                "top_competitors":                 competitors[:5],
                "category_avg_rating":             round(cat_avg, 2),
                "target_rating":                   rating,
                "rating_gap":                      rating_gap,
                "missing_features_vs_competitors": missing,
                "competitive_pressure":            pressure,
            },
            "confidence": 0.65,
            "signals": signals,
            "error": None,
        }

    async def _find_missing_features(self, app_name: str, category: str, competitors: list) -> list[str]:
        if not competitors:
            return []
        prompt = (
            f"The app '{app_name}' is in the {category} category in India.\n"
            f"Direct competitors: {json.dumps([c['name'] for c in competitors[:4]])}\n\n"
            f"List 3-5 specific features that these competitors have but '{app_name}' is likely missing "
            f"based on its low rating. Return as JSON array of short strings (max 15 words each)."
        )
        try:
            raw   = await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                            app_id=self._app_uuid, collector=self.name)
            start = raw.find("[")
            end   = raw.rfind("]") + 1
            return json.loads(raw[start:end]) if start >= 0 else []
        except Exception:
            return []
