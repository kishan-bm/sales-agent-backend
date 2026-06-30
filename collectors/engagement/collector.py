import asyncio
from datetime import datetime, timezone
from google_play_scraper import reviews as gplay_reviews, Sort
from ..base import BaseCollector


class EngagementCollector(BaseCollector):
    name = "engagement"

    async def collect(self) -> dict:
        store = self.app.get("store")
        if store == "google_play":
            return await self._collect_play(self.app.get("app_id"))
        return await self._collect_apple(self.app.get("app_id"))

    async def _collect_play(self, app_id: str) -> dict:
        (review_list, _) = await asyncio.to_thread(
            gplay_reviews, app_id, lang="en", country="in",
            sort=Sort.NEWEST, count=200,
        )
        return await self._analyze(review_list, date_key="at", rating_key="score",
                                   reply_key="replyContent", text_key="content")

    async def _collect_apple(self, app_id: str) -> dict:
        from app_store_scraper import AppStore
        app_name = self.app.get("app_name") or "app"
        a = AppStore(country="in", app_name=app_name, app_id=app_id)
        await asyncio.to_thread(a.review, how_many=200)
        return await self._analyze(a.reviews or [], date_key="date", rating_key="rating",
                                   reply_key=None, text_key="review")

    async def _analyze(self, reviews: list, date_key: str, rating_key: str,
                       reply_key: str | None, text_key: str) -> dict:
        now = datetime.now(timezone.utc)

        def days_ago(r):
            d = r.get(date_key)
            if not d:
                return 9999
            if isinstance(d, str):
                d = datetime.fromisoformat(d)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return (now - d).days

        buckets = {"30": [], "90": [], "180": []}
        for r in reviews:
            age = days_ago(r)
            if age <= 30:  buckets["30"].append(r)
            if age <= 90:  buckets["90"].append(r)
            if age <= 180: buckets["180"].append(r)

        def avg_rating(bucket):
            if not bucket:
                return 0.0
            return round(sum(r.get(rating_key, 5) for r in bucket) / len(bucket), 2)

        r30, r90, r180 = len(buckets["30"]), len(buckets["90"]), len(buckets["180"])
        avg30 = avg_rating(buckets["30"])
        avg90 = avg_rating(buckets["90"])

        if r30 == 0 and r90 < 5:
            velocity = "dead"
        elif r30 < r90 * 0.3:
            velocity = "declining"
        elif r30 > r90 * 0.5:
            velocity = "growing"
        else:
            velocity = "stable"

        replies = sum(1 for r in reviews if reply_key and r.get(reply_key)) if reply_key else 0
        reply_rate = round(replies / len(reviews), 3) if reviews else 0.0

        last_reply_days = None
        if reply_key:
            replied = [r for r in reviews if r.get(reply_key)]
            if replied:
                last_reply_days = days_ago(replied[0])

        churn_words = ["uninstall", "deleted", "switching", "worst", "never again"]
        feature_words = ["please add", "would be great", "missing", "need", "wish"]
        churn_count   = sum(1 for r in reviews if any(w in (r.get(text_key) or "").lower() for w in churn_words))
        feature_count = sum(1 for r in reviews if any(w in (r.get(text_key) or "").lower() for w in feature_words))

        signals = []
        if velocity in ("declining", "dead"):
            signals.append(f"Review velocity is {velocity}")
        if reply_rate < 0.05 and len(reviews) > 20:
            signals.append(f"Developer reply rate only {reply_rate * 100:.0f}%")
        if churn_count > 5:
            signals.append(f"{churn_count} churn signals in recent reviews")

        # LLM: synthesize what the engagement pattern means for sales pitch
        sample_reviews = [r.get(text_key, "")[:100] for r in (buckets["30"] or buckets["90"])[:5]]
        llm_insight = await self._llm_insight(velocity, avg30, r30, churn_count, feature_count, sample_reviews)
        if llm_insight:
            signals.append(llm_insight)

        return {
            "data": {
                "reviews_last_30_days":    r30,
                "reviews_last_90_days":    r90,
                "reviews_last_180_days":   r180,
                "velocity_trend":          velocity,
                "avg_rating_last_30_days": avg30,
                "avg_rating_90_days_ago":  avg90,
                "rating_trend":            "improving" if avg30 > avg90 else "declining" if avg30 < avg90 else "stable",
                "developer_reply_rate":    reply_rate,
                "last_reply_days_ago":     last_reply_days,
                "feature_requests_count":  feature_count,
                "churn_signal_count":      churn_count,
                "llm_engagement_summary":  llm_insight,
            },
            "confidence": 0.85,
            "signals": signals,
            "error": None,
        }

    async def _llm_insight(self, velocity: str, avg_rating: float, recent_count: int,
                           churn_count: int, feature_count: int, samples: list) -> str:
        if not samples and recent_count == 0:
            return ""
        reviews_text = "\n".join(f"- {r}" for r in samples if r.strip()) or "No recent reviews"
        prompt = (
            f"App engagement data:\n"
            f"- Review velocity: {velocity} ({recent_count} reviews in last 30 days)\n"
            f"- Avg rating last 30 days: {avg_rating}\n"
            f"- Churn signals: {churn_count}, Feature requests: {feature_count}\n"
            f"- Sample recent reviews:\n{reviews_text}\n\n"
            f"In ONE sentence (max 25 words), summarize the user engagement situation "
            f"and why this is a good (or bad) sales opportunity."
        )
        try:
            return await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
        except Exception:
            return ""
