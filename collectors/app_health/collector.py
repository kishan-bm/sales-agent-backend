import asyncio
from datetime import date
from google_play_scraper import app as gplay_app, reviews as gplay_reviews, Sort
from ..base import BaseCollector


class AppHealthCollector(BaseCollector):
    name = "app_health"

    async def collect(self) -> dict:
        store = self.app.get("store")
        if store == "google_play":
            return await self._collect_play(self.app.get("app_id"))
        return await self._collect_apple(self.app.get("app_id"))

    async def _collect_play(self, app_id: str) -> dict:
        try:
            detail, (review_list, _) = await asyncio.gather(
                asyncio.to_thread(gplay_app, app_id, lang="en", country="in"),
                asyncio.to_thread(gplay_reviews, app_id, lang="en", country="in",
                                  sort=Sort.NEWEST, count=200),
            )
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                from sqlalchemy import update as sa_update
                from ...database.models import App
                await self.db.execute(sa_update(App).where(App.app_id == app_id).values(status="delisted"))
                await self.db.commit()
                return {"data": {}, "confidence": 0.0, "signals": ["App delisted from Play Store"], "error": "App not found (delisted)"}
            raise

        # Prefer DB-stored date; fall back to fresh gplay_app timestamp (seconds, not ms)
        stored = self.app.get("last_updated")
        if stored and not isinstance(stored, date):
            try:
                from datetime import datetime
                stored = datetime.fromisoformat(str(stored)).date()
            except Exception:
                stored = None
        if not stored:
            updated_ts = detail.get("updated", 0)
            if updated_ts:
                try:
                    stored = date.fromtimestamp(updated_ts)  # gplay_app returns seconds
                except (OSError, OverflowError, ValueError):
                    stored = None
        last_date = stored
        days_ago = (date.today() - last_date).days if last_date else None

        clusters = self._cluster(review_list)
        sample_neg = [r["content"] for r in review_list if r.get("score", 5) <= 2][:5]
        dev_replies = any(r.get("replyContent") for r in review_list)
        release_pattern = self._release_pattern(detail.get("recentChanges", ""))

        signals = []
        if days_ago > 730:
            signals.append(f"Not updated in {days_ago // 30} months")
        if (detail.get("score") or 5) < 3.5:
            signals.append(f"Low rating: {detail.get('score', 0):.1f}★")
        complaints = clusters["crash"] + clusters["login"] + clusters["otp"]
        if complaints > 10:
            signals.append(f"{complaints} crash/login/OTP complaints in recent reviews")

        llm_summary = await self._summarize(review_list[:50])

        return {
            "data": {
                "last_updated_days_ago":     days_ago,
                "current_version":           None if detail.get("version") == "Varies with device" else detail.get("version"),
                "rating":                    detail.get("score"),
                "rating_count":              detail.get("ratings"),
                "installs_normalized":       detail.get("realInstalls", 0),
                "release_notes_pattern":     release_pattern,
                "review_clusters":           clusters,
                "sample_negative_reviews":   sample_neg,
                "developer_replies_reviews": dev_replies,
                "llm_review_summary":        llm_summary,
            },
            "confidence": 0.9,
            "signals": signals,
            "error": None,
        }

    async def _collect_apple(self, app_id: str) -> dict:
        from app_store_scraper import AppStore
        a = AppStore(country="in", app_id=app_id)
        await asyncio.to_thread(a.review, how_many=200)
        reviews = a.reviews or []
        clusters = self._cluster(reviews)
        sample_neg = [r.get("review", "") for r in reviews if r.get("rating", 5) <= 2][:5]

        # Read last_updated from the DB row (set during discovery from currentVersionReleaseDate)
        stored = self.app.get("last_updated")
        if stored and not isinstance(stored, date):
            try:
                from datetime import datetime
                stored = datetime.fromisoformat(str(stored)).date()
            except Exception:
                stored = None
        days_ago = (date.today() - stored).days if stored else None

        signals = []
        if days_ago and days_ago > 730:
            signals.append(f"Not updated in {days_ago // 30} months")
        if reviews:
            avg = sum(r.get("rating", 5) for r in reviews) / len(reviews)
            if avg < 3.5:
                signals.append(f"Average rating {avg:.1f}★ from {len(reviews)} recent reviews")

        llm_summary = await self._summarize_apple(reviews[:50])

        return {
            "data": {
                "last_updated_days_ago":     days_ago,
                "current_version":           None,
                "rating":                    self.app.get("rating"),
                "rating_count":              int(self.app.get("installs") or 0) or None,
                "installs_normalized":       int(self.app.get("installs") or 0) or None,
                "release_notes_pattern":     "unknown",
                "review_clusters":           clusters,
                "sample_negative_reviews":   sample_neg,
                "developer_replies_reviews": False,
                "llm_review_summary":        llm_summary,
            },
            "confidence": 0.75, "signals": signals, "error": None,
        }

    async def _summarize_apple(self, reviews: list) -> str | None:
        texts = [r.get("review", "") for r in reviews if r.get("rating", 5) <= 3][:20]
        if not texts:
            return None
        prompt = (
            "Summarize these negative app reviews in 2 sentences. "
            "Focus on main recurring complaint types:\n\n"
            + "\n".join(f"- {t}" for t in texts)
        )
        try:
            return await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
        except Exception:
            return None

    def _cluster(self, reviews: list) -> dict:
        c = {"crash": 0, "login": 0, "otp": 0, "performance": 0, "ui": 0, "payment": 0}
        for r in reviews:
            t = (r.get("content") or r.get("review") or "").lower()
            if any(w in t for w in ["crash", "crashing", "force close", "not opening"]):
                c["crash"] += 1
            if any(w in t for w in ["login", "sign in", "cannot log", "logout"]):
                c["login"] += 1
            if any(w in t for w in ["otp", "verification code", "sms code"]):
                c["otp"] += 1
            if any(w in t for w in ["slow", "lag", "freeze", "hang", "loading"]):
                c["performance"] += 1
            if any(w in t for w in ["ugly", "ui", "design", "interface", "outdated"]):
                c["ui"] += 1
            if any(w in t for w in ["payment", "refund", "charge", "billing"]):
                c["payment"] += 1
        return c

    def _release_pattern(self, notes: str) -> str:
        t = notes.lower()
        if any(w in t for w in ["new feature", "added", "introducing", "now you can"]):
            return "feature_updates"
        if any(w in t for w in ["bug fix", "minor fix", "performance", "stability"]):
            return "bug_fixes_only"
        return "mixed"

    async def _summarize(self, reviews: list) -> str | None:
        texts = [r.get("content", "") for r in reviews if r.get("score", 5) <= 3][:20]
        if not texts:
            return None
        prompt = (
            "Summarize these negative app reviews in 2 sentences. "
            "Focus on main recurring complaint types:\n\n"
            + "\n".join(f"- {t}" for t in texts)
        )
        try:
            return await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
        except Exception:
            return None
