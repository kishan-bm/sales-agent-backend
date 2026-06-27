from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime
from ...database.repository import get_db, get_app
from ...database.models import OutreachCampaign
from ...outreach.outreach_generator import generate_outreach
from ...services.email_service import send_email
from ...utils.config import SMTP_USER
import uuid

router = APIRouter()


@router.get("/{app_uuid}/outreach")
async def get_outreach(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OutreachCampaign).where(OutreachCampaign.app_id == app_uuid)
    )
    campaigns = result.scalars().all()
    return [
        {
            "id":             str(c.id),
            "email_subject":  c.email_subject,
            "email_body":     c.email_body,
            "followup_1":     c.followup_1_body,
            "followup_2":     c.followup_2_body,
            "status":         c.status,
            "created_at":     str(c.created_at),
        }
        for c in campaigns
    ]


@router.post("/{app_uuid}/outreach/generate")
async def generate(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    app = await get_app(db, app_uuid)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    result = await generate_outreach(db, app_uuid, app.__dict__)
    if not result:
        raise HTTPException(status_code=422, detail="Could not generate outreach — no contact found")
    return result


@router.post("/{app_uuid}/outreach/{campaign_id}/approve")
async def approve(app_uuid: uuid.UUID, campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(OutreachCampaign)
        .where(OutreachCampaign.id == campaign_id)
        .values(status="approved", approved_at=datetime.utcnow())
    )
    await db.commit()
    return {"status": "approved"}


@router.post("/{app_uuid}/outreach/{campaign_id}/send-test")
async def send_test(
    app_uuid: uuid.UUID,
    campaign_id: uuid.UUID,
    to: str = Query(default=None, description="Send to this email (defaults to SMTP_USER)"),
    db: AsyncSession = Depends(get_db),
):
    """Send the first email in the sequence to your own inbox for testing."""
    result = await db.execute(
        select(OutreachCampaign).where(
            OutreachCampaign.id == campaign_id,
            OutreachCampaign.app_id == app_uuid,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    recipient = to or SMTP_USER
    if not recipient:
        raise HTTPException(status_code=422, detail="No recipient: pass ?to=your@email.com or set SMTP_USER in .env")

    sent = await send_email(recipient, campaign.email_subject, campaign.email_body)
    if not sent:
        raise HTTPException(
            status_code=503,
            detail="Email not sent. Set SMTP_USER and SMTP_PASSWORD in .env (Gmail app password).",
        )
    return {"status": "sent", "to": recipient, "subject": campaign.email_subject}
