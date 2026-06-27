from ..base import BaseCollector
from ...database.repository import get_collector_evidence
import uuid


class CommercialCollector(BaseCollector):
    name = "commercial"

    async def collect(self) -> dict:
        price    = str(self.app.get("price") or "0")
        installs = self.app.get("installs") or ""
        app_id   = self.app.get("id")

        # Reuse EC2 funding data — no duplicate API call
        funding_usd = None
        if app_id:
            ev = await get_collector_evidence(self.db, uuid.UUID(str(app_id)), "company_intel")
            if ev and ev.data:
                funding_usd = ev.data.get("funding_amount_usd")

        is_paid          = price not in ("0", "0.0", "Free", "", None)
        has_iap          = "in-app" in (self.app.get("d2c_signals") or "").lower()
        has_subscription = any(w in (self.app.get("positive_keywords") or "").lower()
                               for w in ["subscription", "membership"])

        installs_int = self._parse_installs(installs)
        mrr = self._estimate_mrr(is_paid, has_subscription, installs_int, price)

        if funding_usd and funding_usd > 1_000_000:
            tier = "high"
        elif mrr and mrr > 5000:
            tier = "high"
        elif mrr and mrr > 1000:
            tier = "medium"
        else:
            tier = "low"

        model = ("paid" if is_paid else
                 "subscription" if has_subscription else
                 "freemium" if has_iap else "free")

        signals = []
        if is_paid or has_subscription:
            signals.append(f"Monetization: {model} — users are paying")
        if mrr and mrr > 5000:
            signals.append(f"Estimated MRR ~${mrr:,} — can afford solution")
        if funding_usd:
            signals.append(f"Raised ${funding_usd:,} — budget confirmed")

        data = {
            "monetization_model":    model,
            "has_in_app_purchases":  has_iap,
            "has_subscription":      has_subscription,
            "estimated_mrr_usd":     mrr,
            "funding_usd":           funding_usd,
            "affordability_tier":    tier,
            "budget_signal_reason":  f"Model: {model}, installs: {installs}",
        }

        # LLM: assess whether this company can realistically afford mobile dev services
        llm_insight = await self._llm_insight(data, self.app.get("app_name", ""), installs)
        if llm_insight:
            signals.append(llm_insight)
            data["llm_budget_assessment"] = llm_insight

        return {"data": data, "confidence": 0.6, "signals": signals, "error": None}

    async def _llm_insight(self, data: dict, app_name: str, installs: str) -> str:
        tier = data.get("affordability_tier", "unknown")
        if tier == "low" and not data.get("funding_usd"):
            return ""  # nothing interesting to say
        prompt = (
            f"App: {app_name}\n"
            f"Installs: {installs}\n"
            f"Monetization: {data['monetization_model']}\n"
            f"Estimated MRR: ${data.get('estimated_mrr_usd') or 0:,}\n"
            f"Funding raised: ${data.get('funding_usd') or 0:,}\n"
            f"Affordability tier: {tier}\n\n"
            f"In ONE sentence (max 20 words), assess whether this company can afford "
            f"a $10K-$50K mobile app modernization project."
        )
        try:
            return await self.llm.generate(prompt, model="claude-haiku-4-5-20251001",
                                           app_id=self._app_uuid, collector=self.name)
        except Exception:
            return ""

    def _parse_installs(self, installs: str) -> int:
        installs = installs.replace(",", "").replace("+", "").strip()
        multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
        if installs and installs[-1].lower() in multipliers:
            try:
                return int(float(installs[:-1]) * multipliers[installs[-1].lower()])
            except ValueError:
                pass
        try:
            return int(installs)
        except (ValueError, TypeError):
            return 0

    def _estimate_mrr(self, is_paid: bool, has_sub: bool, installs: int, price: str) -> int | None:
        try:
            price_val = float(str(price).replace("$", "").replace("₹", ""))
        except (ValueError, TypeError):
            price_val = 0

        if is_paid and price_val > 0:
            return int(installs * price_val * 0.01)
        if has_sub:
            return int(installs * 0.005 * 299)
        return None
