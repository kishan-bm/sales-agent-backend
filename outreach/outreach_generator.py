import json
from sqlalchemy.ext.asyncio import AsyncSession
from ..database.repository import get_evidence, get_primary_contact, save_campaign
from ..llm.manager import LLMManager
from ..utils.logger import get_logger
import uuid

logger = get_logger(__name__)


async def generate_outreach(db: AsyncSession, app_uuid: uuid.UUID, app: dict) -> dict | None:
    evidence_list = await get_evidence(db, app_uuid)
    contact       = await get_primary_contact(db, app_uuid)

    if not contact:
        logger.warning("outreach.no_contact", app_id=str(app_uuid))
        return None

    ev_map = {e.collector: e.data or {} for e in evidence_list}
    score_ev = next((e for e in evidence_list if e.collector == "opportunity_score"), None)

    context = _build_context(app, ev_map, contact)
    llm = LLMManager(db)

    prompt = f"""You are a B2B sales expert writing hyper-personalized cold emails for a mobile app development agency.
We help Indian D2C companies modernize outdated mobile apps.

CONTEXT:
{context}

Write a 3-email sequence (initial + 2 follow-ups). Return ONLY valid JSON:
{{
  "email_1": {{
    "subject": "string (max 60 chars, personalized)",
    "body": "string (max 150 words, 1 specific pain point, 1 social proof, 1 CTA)"
  }},
  "email_2": {{
    "subject": "string",
    "body": "string (max 120 words, different angle, reference email 1)"
  }},
  "email_3": {{
    "subject": "string",
    "body": "string (max 100 words, last attempt, value-first)"
  }}
}}

Rules:
- Use the contact's first name
- Reference 1 specific fact from the evidence (e.g. actual rating, specific complaint type)
- Never mention "outdated" directly — say "modernize" or "level up"
- End each email with ONE clear question as CTA
- No buzzwords: no "synergy", "leverage", "best-in-class"
"""

    raw = await llm.generate(prompt, model="claude-haiku-4-5-20251001",
                              max_tokens=1500, app_id=app_uuid, collector="outreach")

    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        emails = json.loads(raw[start:end])
    except Exception:
        logger.error("outreach.parse_failed", app_id=str(app_uuid))
        return None

    campaign = await save_campaign(db, {
        "app_id":          app_uuid,
        "contact_id":      contact.id,
        "email_subject":   emails["email_1"]["subject"],
        "email_body":      emails["email_1"]["body"],
        "followup_1_body": emails["email_2"]["body"],
        "followup_2_body": emails["email_3"]["body"],
        "status":          "draft",
    })

    logger.info("outreach.generated", app_id=str(app_uuid), contact=contact.name)
    return {"campaign_id": str(campaign.id), "emails": emails, "contact": contact.name}


def _build_context(app: dict, ev_map: dict, contact) -> str:
    health  = ev_map.get("app_health", {})
    company = ev_map.get("company_intel", {})
    social  = ev_map.get("social", {})

    days_stale  = health.get("last_updated_days_ago", 0)
    rating      = health.get("rating", "unknown")
    clusters    = health.get("review_clusters", {})
    top_complaint = max(clusters, key=clusters.get) if clusters else "general issues"

    return f"""
App: {app.get('app_name')} ({app.get('store')})
Category: {app.get('category')}
Last updated: {days_stale} days ago
Current rating: {rating}★
Top complaint type: {top_complaint} ({clusters.get(top_complaint, 0)} mentions)

Company: {company.get('company_name') or app.get('developer')}
Size: {company.get('employee_count_range', 'unknown')} employees
Funding: {company.get('funding_stage', 'unknown')}

Contact: {contact.name}, {contact.title}
Best signal: {social.get('best_signal_quote') or 'App has not been updated in 2+ years'}
""".strip()
