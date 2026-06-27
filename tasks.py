import asyncio
import uuid
from .worker import celery_app
from .utils.logger import get_logger
from .utils.config import OUTREACH_SCORE_THRESHOLD

logger = get_logger(__name__)


@celery_app.task(bind=True, name="tasks.run_evidence_collection")
def run_evidence_collection(self, app_uuid_str: str):
    """Celery entry point — bridges sync Celery into async orchestrator."""
    # Always create a fresh event loop — avoids "Future attached to different loop"
    # when a prior run left a dirty loop in the worker process
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_orchestrate(uuid.UUID(app_uuid_str)))
    finally:
        loop.close()


async def _orchestrate(app_uuid: uuid.UUID):
    """
    Dependency-aware two-stage evidence collection:

    Stage 1 (parallel, no deps):
        App Health, Company Intel, Hiring, Social,
        Competitor, Engagement, Technical

    Stage 2 (parallel, depends on Stage 1 results in DB):
        Commercial  ← reads Company Intel funding from DB
        Contact     ← reads Social founder name from DB

    Then: Score → threshold check → outreach or archive
    """
    from .database.repository import AsyncSessionLocal, update_app_status, get_app
    from .collectors.app_health.collector    import AppHealthCollector
    from .collectors.company_intel.collector import CompanyIntelCollector
    from .collectors.hiring.collector        import HiringCollector
    from .collectors.social.collector        import SocialCollector
    from .collectors.competitor.collector    import CompetitorCollector
    from .collectors.engagement.collector    import EngagementCollector
    from .collectors.technical.collector     import TechnicalCollector
    from .collectors.commercial.collector    import CommercialCollector
    from .collectors.contact.collector       import ContactCollector
    from .scoring.opportunity_scorer         import score_app
    from .outreach.outreach_generator        import generate_outreach

    STAGE_1 = [
        AppHealthCollector,
        CompanyIntelCollector,
        HiringCollector,
        SocialCollector,
        CompetitorCollector,
        EngagementCollector,
        TechnicalCollector,
    ]

    # Stage 2 collectors depend on Stage 1 data already written to DB:
    # Commercial reads company_intel.funding_amount_usd
    # Contact    reads social.founder_name + social.founder_linkedin_url
    STAGE_2 = [
        CommercialCollector,
        ContactCollector,
    ]

    # Each collector needs its own DB session — asyncpg does not allow
    # concurrent queries on a single connection.
    async def make_session():
        return AsyncSessionLocal()

    async with AsyncSessionLocal() as db:
        await update_app_status(db, app_uuid, "evidence_collecting")
        app = await get_app(db, app_uuid)
        app_data = {c.key: getattr(app, c.key) for c in app.__table__.columns}

    # ── Stage 1: independent collectors (each with own session) ──────────
    logger.info("orchestrator.stage1.start", app_id=str(app_uuid),
                collectors=[c.name for c in STAGE_1])

    stage1_results = await asyncio.gather(
        *[_run_collector_with_session(cls, app_data) for cls in STAGE_1],
        return_exceptions=True,
    )

    _log_stage_results("stage1", STAGE_1, stage1_results, app_uuid)

    # ── Stage 2: dependency collectors ────────────────────────────────────
    logger.info("orchestrator.stage2.start", app_id=str(app_uuid),
                collectors=[c.name for c in STAGE_2])

    stage2_results = await asyncio.gather(
        *[_run_collector_with_session(cls, app_data) for cls in STAGE_2],
        return_exceptions=True,
    )

    _log_stage_results("stage2", STAGE_2, stage2_results, app_uuid)

    # ── Score ──────────────────────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        logger.info("orchestrator.scoring", app_id=str(app_uuid))
        score = await score_app(db, app_uuid)
        total = score["total_score"]

        logger.info("orchestrator.scored", app_id=str(app_uuid),
                    score=total, grade=score["grade"],
                    threshold=OUTREACH_SCORE_THRESHOLD)

        # ── Threshold gate ────────────────────────────────────────────────
        if total < OUTREACH_SCORE_THRESHOLD:
            from sqlalchemy import update as sa_update
            from .database.models import App
            await db.execute(
                sa_update(App).where(App.id == app_uuid)
                .values(status="archived", score_at_archive=total)
            )
            await db.commit()
            logger.info("orchestrator.archived",
                        app_id=str(app_uuid), score=total,
                        reason=f"score {total} < threshold {OUTREACH_SCORE_THRESHOLD}")
            return

        # ── Outreach generation (only for qualified leads) ────────────────
        logger.info("orchestrator.outreach.start", app_id=str(app_uuid), score=total)
        outreach = await generate_outreach(db, app_uuid, app_data)
        if outreach:
            await update_app_status(db, app_uuid, "waiting_approval")
            logger.info("orchestrator.outreach.done",
                        app_id=str(app_uuid), campaign_id=outreach.get("campaign_id"))
        else:
            # Contact not found — score is good but can't email yet
            await update_app_status(db, app_uuid, "scored")
            logger.warning("orchestrator.outreach.no_contact", app_id=str(app_uuid))


async def _run_collector_with_session(cls, app_data: dict) -> dict:
    """Run a single collector with its own DB session (asyncpg needs one connection per coroutine)."""
    from .database.repository import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            return await cls(app_data, db).run()
    except Exception as e:
        logger.error("collector.exception", collector=cls.name, error=str(e))
        return {"collector": cls.name, "error": str(e)}


def _log_stage_results(stage: str, classes: list, results: list, app_uuid: uuid.UUID):
    for cls, result in zip(classes, results):
        if isinstance(result, Exception):
            logger.error(f"orchestrator.{stage}.failed",
                         collector=cls.name, app_id=str(app_uuid), error=str(result))
        else:
            logger.info(f"orchestrator.{stage}.ok",
                        collector=cls.name, app_id=str(app_uuid),
                        confidence=result.get("confidence", 0))
