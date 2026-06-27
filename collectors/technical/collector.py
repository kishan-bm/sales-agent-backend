import asyncio
from google_play_scraper import app as gplay_app
from ..base import BaseCollector


class TechnicalCollector(BaseCollector):
    name = "technical"

    async def collect(self) -> dict:
        store = self.app.get("store")
        if store == "google_play":
            return await self._collect_play(self.app.get("app_id"))
        return self._collect_apple()

    async def _collect_play(self, app_id: str) -> dict:
        detail = await asyncio.to_thread(gplay_app, app_id, lang="en", country="in")

        target_sdk    = detail.get("targetSdkVersion")
        min_sdk       = detail.get("minSdkVersion")
        permissions   = detail.get("permissions") or []
        release_notes = (detail.get("recentChanges") or "").lower()

        framework = self._infer_framework(permissions or [], detail.get("description", ""))
        has_ai    = any(w in (detail.get("description") or "").lower()
                        for w in ["ai", "artificial intelligence", "machine learning", "chatgpt"])

        tech_debt = 0
        if target_sdk and target_sdk < 31:
            tech_debt += 3
        if framework in ("cordova", "ionic", "xamarin"):
            tech_debt += 4
        if any(w in release_notes for w in ["bug fix", "minor fix", "stability"]):
            tech_debt += 3

        ui_era = self._estimate_ui_era(target_sdk)

        signals = []
        if target_sdk and target_sdk < 31:
            signals.append(f"Target SDK {target_sdk} (Android 12 = 31) — outdated")
        if framework in ("cordova", "ionic", "xamarin"):
            signals.append(f"Framework: {framework} — legacy web wrapper")
        if tech_debt >= 7:
            signals.append("High technical debt score — strong rebuild signal")

        data = {
            "target_sdk_version":    target_sdk,
            "min_sdk_version":       min_sdk,
            "ios_minimum_version":   None,
            "framework_inferred":    framework,
            "has_dark_mode":         None,
            "has_ai_features":       has_ai,
            "has_accessibility":     None,
            "permissions_count":     len(permissions),
            "release_notes_pattern": self._release_pattern(release_notes),
            "ui_era_estimate":       ui_era,
            "tech_debt_score_raw":   tech_debt,
        }

        # LLM: translate technical findings into a business-level pitch angle
        llm_insight = await self._llm_insight(data, framework, release_notes[:300])
        if llm_insight:
            signals.append(llm_insight)
            data["llm_tech_summary"] = llm_insight

        return {"data": data, "confidence": 0.75, "signals": signals, "error": None}

    def _collect_apple(self) -> dict:
        min_os = self.app.get("minimumOsVersion")
        signals = []
        if min_os:
            try:
                if float(min_os) < 14.0:
                    signals.append(f"Minimum iOS {min_os} — outdated requirement")
            except ValueError:
                pass
        return {
            "data": {
                "target_sdk_version": None, "min_sdk_version": None,
                "ios_minimum_version": min_os, "framework_inferred": None,
                "has_dark_mode": None, "has_ai_features": None,
                "has_accessibility": None, "permissions_count": None,
                "release_notes_pattern": "unknown", "ui_era_estimate": None,
                "tech_debt_score_raw": 3 if signals else 0,
            },
            "confidence": 0.4, "signals": signals, "error": None,
        }

    async def _llm_insight(self, data: dict, framework: str, release_notes: str) -> str:
        sdk = data.get("target_sdk_version")
        debt = data.get("tech_debt_score_raw", 0)
        if debt == 0 and not sdk:
            return ""
        prompt = (
            f"App technical profile:\n"
            f"- Target SDK: {sdk} (modern = 33+, Android 13)\n"
            f"- Framework: {framework}\n"
            f"- Tech debt score: {debt}/10\n"
            f"- UI era: {data.get('ui_era_estimate')}\n"
            f"- Release pattern: {data.get('release_notes_pattern')}\n"
            f"- Recent changes: {release_notes or 'none'}\n\n"
            f"In ONE sentence (max 25 words), explain what this means for a company "
            f"selling mobile app modernization services."
        )
        try:
            return await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
        except Exception:
            return ""

    def _infer_framework(self, _permissions: list, description: str) -> str:
        desc = description.lower()
        if "flutter" in desc:      return "flutter"
        if "react native" in desc: return "react_native"
        if "cordova" in desc or "phonegap" in desc: return "cordova"
        if "ionic" in desc:        return "ionic"
        if "xamarin" in desc:      return "xamarin"
        return "native"

    def _release_pattern(self, notes: str) -> str:
        if any(w in notes for w in ["new feature", "added", "introducing"]):
            return "feature_updates"
        if any(w in notes for w in ["bug fix", "minor fix", "performance", "stability"]):
            return "bug_fixes_only"
        return "mixed"

    def _estimate_ui_era(self, sdk: int | None) -> str | None:
        if sdk is None: return None
        if sdk < 26:   return "pre-2020"
        if sdk < 31:   return "2020-2022"
        return "2023+"
