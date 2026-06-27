from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ...database.repository import get_db, get_evidence
import uuid

router = APIRouter()


@router.get("/{app_uuid}/evidence")
async def get_app_evidence(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    evidence = await get_evidence(db, app_uuid)
    if not evidence:
        raise HTTPException(status_code=404, detail="No evidence found")
    return [
        {
            "collector":    e.collector,
            "data":         e.data,
            "confidence":   e.confidence,
            "signals":      e.signals,
            "collected_at": str(e.collected_at),
            "error":        e.error,
        }
        for e in evidence
    ]
