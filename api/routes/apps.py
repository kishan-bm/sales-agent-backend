from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from ...database.repository import get_db, list_apps, get_app, update_app_status
from ...tasks import run_evidence_collection
from ...agents.app_discovery.agent import run_discovery
import uuid

router = APIRouter()


@router.get("")
async def get_apps(status: str | None = None, db: AsyncSession = Depends(get_db)):
    apps = await list_apps(db, status=status)
    return [_serialize(a) for a in apps]


@router.get("/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    all_apps = await list_apps(db)
    return {
        "total":          len(all_apps),
        "scored":         sum(1 for a in all_apps if a.status == "scored"),
        "outreach_ready": sum(1 for a in all_apps if a.status == "waiting_approval"),
        "email_sent":     sum(1 for a in all_apps if a.status == "email_sent"),
    }


@router.post("/discover")
async def trigger_discovery(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_discovery)
    return {"status": "discovery_started"}


@router.get("/{app_uuid}")
async def get_app_detail(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    app = await get_app(db, app_uuid)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return _serialize(app)


@router.post("/{app_uuid}/run-evidence")
async def run_evidence(app_uuid: uuid.UUID, db: AsyncSession = Depends(get_db)):
    app = await get_app(db, app_uuid)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    run_evidence_collection.delay(str(app_uuid))
    await update_app_status(db, app_uuid, "evidence_collecting")
    return {"status": "queued", "app_id": str(app_uuid)}


def _serialize(app) -> dict:
    return {
        "id":                str(app.id),
        "app_id":            app.app_id,
        "store":             app.store,
        "app_name":          app.app_name,
        "category":          app.category,
        "developer":         app.developer,
        "developer_email":   app.developer_email,
        "developer_website": app.developer_website,
        "last_updated":      str(app.last_updated) if app.last_updated else None,
        "rating":            app.rating,
        "installs":          app.installs,
        "status":            app.status,
        "discovered_at":     str(app.discovered_at) if app.discovered_at else None,
    }
