from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update
from .models import App, Evidence, OpportunityScore, Contact, OutreachCampaign, LLMAuditLog
from ..utils.config import DATABASE_URL
import uuid

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ── Apps ──────────────────────────────────────────────────────────────────────

async def upsert_app(db: AsyncSession, app_data: dict) -> App:
    result = await db.execute(
        select(App).where(App.app_id == app_data["app_id"], App.store == app_data["store"])
    )
    app = result.scalar_one_or_none()
    if app:
        for k, v in app_data.items():
            setattr(app, k, v)
    else:
        app = App(**app_data)
        db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def get_app(db: AsyncSession, app_uuid: uuid.UUID) -> App | None:
    result = await db.execute(select(App).where(App.id == app_uuid))
    return result.scalar_one_or_none()


async def list_apps(db: AsyncSession, status: str | None = None) -> list[App]:
    q = select(App)
    if status:
        q = q.where(App.status == status)
    result = await db.execute(q)
    return result.scalars().all()


async def update_app_status(db: AsyncSession, app_uuid: uuid.UUID, status: str):
    await db.execute(update(App).where(App.id == app_uuid).values(status=status))
    await db.commit()


# ── Evidence ──────────────────────────────────────────────────────────────────

async def upsert_evidence(db: AsyncSession, app_uuid: uuid.UUID, collector: str, result: dict):
    existing = await db.execute(
        select(Evidence).where(Evidence.app_id == app_uuid, Evidence.collector == collector)
    )
    ev = existing.scalar_one_or_none()
    if ev:
        ev.data       = result.get("data")
        ev.confidence = result.get("confidence", 0.0)
        ev.signals    = result.get("signals", [])
        ev.error      = result.get("error")
    else:
        ev = Evidence(
            app_id    = app_uuid,
            collector = collector,
            data      = result.get("data"),
            confidence= result.get("confidence", 0.0),
            signals   = result.get("signals", []),
            error     = result.get("error"),
        )
        db.add(ev)
    await db.commit()


async def get_evidence(db: AsyncSession, app_uuid: uuid.UUID) -> list[Evidence]:
    result = await db.execute(select(Evidence).where(Evidence.app_id == app_uuid))
    return result.scalars().all()


async def get_collector_evidence(db: AsyncSession, app_uuid: uuid.UUID, collector: str) -> Evidence | None:
    result = await db.execute(
        select(Evidence).where(Evidence.app_id == app_uuid, Evidence.collector == collector)
    )
    return result.scalar_one_or_none()


# ── Contacts ──────────────────────────────────────────────────────────────────

async def save_contacts(db: AsyncSession, app_uuid: uuid.UUID, contacts: list[dict]):
    for c in contacts:
        contact = Contact(app_id=app_uuid, **c)
        db.add(contact)
    await db.commit()


async def get_primary_contact(db: AsyncSession, app_uuid: uuid.UUID) -> Contact | None:
    result = await db.execute(
        select(Contact).where(Contact.app_id == app_uuid, Contact.is_primary == True)
    )
    return result.scalar_one_or_none()


# ── Opportunity Score ─────────────────────────────────────────────────────────

async def save_score(db: AsyncSession, app_uuid: uuid.UUID, score_data: dict):
    existing = await db.execute(select(OpportunityScore).where(OpportunityScore.app_id == app_uuid))
    score = existing.scalar_one_or_none()
    if score:
        for k, v in score_data.items():
            setattr(score, k, v)
    else:
        score = OpportunityScore(app_id=app_uuid, **score_data)
        db.add(score)
    await db.commit()


# ── LLM Audit ─────────────────────────────────────────────────────────────────

async def log_llm_call(db: AsyncSession, log_data: dict):
    log = LLMAuditLog(**log_data)
    db.add(log)
    await db.commit()


# ── Campaigns ─────────────────────────────────────────────────────────────────

async def save_campaign(db: AsyncSession, campaign_data: dict) -> OutreachCampaign:
    campaign = OutreachCampaign(**campaign_data)
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign
