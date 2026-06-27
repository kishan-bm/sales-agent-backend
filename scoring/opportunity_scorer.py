from ..database.repository import get_evidence, save_score
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

WEIGHTS = {
    "app_health":    25,
    "company_intel": 15,
    "hiring":        15,
    "social":        15,
    "competitor":    10,
    "commercial":    10,
    "engagement":    10,
    "technical":     10,
}
MAX_RAW = 110


def _score_app_health(data: dict) -> int:
    pts = 0
    days = data.get("last_updated_days_ago")
    if days is None:
        pts += 10   # unknown update date — treat as moderately stale
    elif days > 730:
        pts += 20
        if days > 1080: pts += 5
    rating = data.get("rating") or 5
    if rating < 3.5: pts += 5
    clusters = data.get("review_clusters") or {}
    complaints = clusters.get("crash", 0) + clusters.get("login", 0) + clusters.get("otp", 0)
    if complaints > 10: pts += 5
    return min(pts, WEIGHTS["app_health"])


def _score_company_intel(data: dict) -> int:
    pts = 0
    emp = data.get("employee_count_range") or ""
    if any(r in emp for r in ["11-50", "51-200", "11–50", "51–200"]): pts += 5
    if data.get("funding_stage") and data["funding_stage"] not in ("bootstrapped", None): pts += 5
    news = data.get("recent_news_headlines") or []
    if any("mobile" in h.lower() or "product" in h.lower() or "app" in h.lower() for h in news): pts += 5
    return min(pts, WEIGHTS["company_intel"])


def _score_hiring(data: dict) -> int:
    pts = 0
    if data.get("is_hiring_mobile"): pts += 10
    titles = " ".join(data.get("job_titles") or []).lower()
    if "senior" in titles or "lead" in titles: pts += 5
    frameworks = data.get("frameworks_sought") or []
    if "flutter" in frameworks or "react native" in frameworks: pts += 3
    return min(pts, WEIGHTS["hiring"])


def _score_social(data: dict) -> int:
    pts = 0
    days = data.get("linkedin_last_post_days_ago")
    if days is not None and days < 30: pts += 5
    if data.get("buying_signals"): pts += 5
    flags = data.get("signal_flags") or {}
    if flags.get("mobile_rewrite") or flags.get("ai_adoption"): pts += 5
    return min(pts, WEIGHTS["social"])


def _score_competitor(data: dict) -> int:
    pts = 0
    gap = data.get("rating_gap") or 0
    if gap > 1.0: pts += 5
    if gap > 1.5: pts += 5
    missing = data.get("missing_features_vs_competitors") or []
    if len(missing) >= 3: pts += 3
    return min(pts, WEIGHTS["competitor"])


def _score_commercial(data: dict) -> int:
    pts = 0
    model = data.get("monetization_model") or "free"
    if model in ("paid", "subscription"): pts += 5
    mrr = data.get("estimated_mrr_usd") or 0
    if mrr > 5000: pts += 5
    return min(pts, WEIGHTS["commercial"])


def _score_engagement(data: dict) -> int:
    pts = 0
    if data.get("velocity_trend") in ("declining", "dead"): pts += 5
    if (data.get("developer_reply_rate") or 1) < 0.05: pts += 3
    if (data.get("churn_signal_count") or 0) > 5: pts += 2
    return min(pts, WEIGHTS["engagement"])


def _score_technical(data: dict) -> int:
    pts = 0
    sdk = data.get("target_sdk_version")
    if sdk and sdk < 31: pts += 3
    framework = (data.get("framework_inferred") or "").lower()
    if framework in ("cordova", "ionic", "xamarin"): pts += 4
    if data.get("release_notes_pattern") == "bug_fixes_only": pts += 3
    return min(pts, WEIGHTS["technical"])


SCORERS = {
    "app_health":    _score_app_health,
    "company_intel": _score_company_intel,
    "hiring":        _score_hiring,
    "social":        _score_social,
    "competitor":    _score_competitor,
    "commercial":    _score_commercial,
    "engagement":    _score_engagement,
    "technical":     _score_technical,
}


async def score_app(db: AsyncSession, app_uuid: uuid.UUID) -> dict:
    evidence_list = await get_evidence(db, app_uuid)
    ev_by_collector = {e.collector: e.data or {} for e in evidence_list}

    collector_scores = {}
    all_signals      = []

    for collector, scorer in SCORERS.items():
        data = ev_by_collector.get(collector, {})
        pts  = scorer(data)
        collector_scores[collector] = pts
        ev = next((e for e in evidence_list if e.collector == collector), None)
        if ev and ev.signals:
            all_signals.extend(ev.signals)

    raw_total   = sum(collector_scores.values())
    total_score = round(raw_total / MAX_RAW * 100)
    grade       = "A" if total_score >= 80 else "B" if total_score >= 60 else "C" if total_score >= 40 else "D"

    top_signals = all_signals[:5]

    # Best outreach angle: pick highest-scoring collector as hook
    top_collector = max(collector_scores, key=collector_scores.get)
    angle_map = {
        "app_health":    "App stability & crash issues are costing you users",
        "hiring":        "You're hiring mobile talent — the right partner accelerates this",
        "social":        "Your recent product moves signal it's time to modernize",
        "competitor":    "Competitors are pulling ahead in ratings and features",
        "commercial":    "Your monetization model deserves a better mobile experience",
        "engagement":    "Declining engagement is a fixable technical problem",
        "technical":     "Technical debt in your app is blocking growth",
        "company_intel": "Your company size and stage is the right fit for our solution",
    }
    outreach_angle = angle_map.get(top_collector, "")

    score_data = {
        "total_score":      total_score,
        "grade":            grade,
        "collector_scores": collector_scores,
        "top_signals":      top_signals,
        "outreach_angle":   outreach_angle,
    }
    await save_score(db, app_uuid, score_data)
    return {"app_id": str(app_uuid), **score_data}
