from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database.repository import get_db, get_app
from ...database.models import OpportunityScore
from ...scoring.opportunity_scorer import score_app
import uuid

router = APIRouter()


@router.get("/{app_uuid}/score")
async def get_score(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OpportunityScore).where(OpportunityScore.app_id == app_uuid))
    score  = result.scalar_one_or_none()
    if not score:
        raise HTTPException(status_code=404, detail="Score not computed yet")
    return {
        "total_score":      score.total_score,
        "grade":            score.grade,
        "collector_scores": score.collector_scores,
        "top_signals":      score.top_signals,
        "outreach_angle":   score.outreach_angle,
        "total_llm_cost":   score.total_llm_cost,
        "scored_at":        str(score.scored_at),
    }


@router.post("/{app_uuid}/score")
async def trigger_score(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    app = await get_app(db, app_uuid)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    result = await score_app(db, app_uuid)
    return result
